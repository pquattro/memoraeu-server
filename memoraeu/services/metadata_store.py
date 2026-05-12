import aiosqlite
import json
import os
import base64
from datetime import datetime
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from api.config import get_settings
from api.models import Memory, Organization, User, CategorySuggestion

# F3 — Clé de chiffrement serveur pour les secrets TOTP
# Dérivée depuis TOTP_MASTER_KEY dans .env (32+ chars recommandé)
def _get_totp_key() -> bytes | None:
    master = os.getenv("TOTP_MASTER_KEY", "")
    if not master:
        return None
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                     salt=b"memoraeu-totp-v1", iterations=100_000)
    return kdf.derive(master.encode())

def _encrypt_totp(secret: str) -> str:
    key = _get_totp_key()
    if not key:
        return secret
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, secret.encode(), None)
    return "TOTP:" + base64.b64encode(nonce + ct).decode()

def _decrypt_totp(stored: str) -> str:
    if not stored or not stored.startswith("TOTP:"):
        return stored  # rétrocompat : secret en clair
    key = _get_totp_key()
    if not key:
        return stored
    data = base64.b64decode(stored[5:])
    return AESGCM(key).decrypt(data[:12], data[12:], None).decode()

settings = get_settings()

SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    plan TEXT DEFAULT 'free',
    created_at TEXT NOT NULL,
    settings TEXT,
    enc_secret TEXT,
    enc_salt TEXT,
    is_active INTEGER DEFAULT 1,
    deleted_at TEXT,
    billing_name TEXT,
    billing_address_line1 TEXT,
    billing_address_line2 TEXT,
    billing_city TEXT,
    billing_zip TEXT,
    billing_country TEXT,
    billing_vat TEXT,
    billing_contact_name TEXT,
    billing_contact_email TEXT,
    billing_contact_phone TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT,
    role TEXT DEFAULT 'member',
    created_at TEXT NOT NULL,
    settings TEXT,
    is_active INTEGER DEFAULT 1,
    deleted_at TEXT,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    category TEXT,
    source TEXT DEFAULT 'api',
    scope TEXT DEFAULT 'private',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS tags (
    memory_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (memory_id, tag),
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS categories (
    org_id TEXT NOT NULL,
    name TEXT NOT NULL,
    usage_count INTEGER DEFAULT 1,
    PRIMARY KEY (org_id, name)
);

CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    prefix TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    is_active INTEGER DEFAULT 1,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

CREATE TABLE IF NOT EXISTS usage_daily (
    org_id TEXT NOT NULL,
    date TEXT NOT NULL,
    memories_created INTEGER DEFAULT 0,
    recalls INTEGER DEFAULT 0,
    PRIMARY KEY (org_id, date)
);

CREATE TABLE IF NOT EXISTS plans (
    key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    max_memories INTEGER NOT NULL DEFAULT 100,
    max_recalls_per_day INTEGER NOT NULL DEFAULT -1,
    price_monthly REAL,
    price_annual REAL,
    stripe_product_id TEXT,
    stripe_price_monthly_id TEXT,
    stripe_price_annual_id TEXT,
    is_active INTEGER DEFAULT 1,
    deleted_at TEXT,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL UNIQUE,
    stripe_customer_id TEXT UNIQUE,
    stripe_subscription_id TEXT UNIQUE,
    stripe_price_id TEXT,
    plan TEXT NOT NULL DEFAULT 'free',
    period TEXT DEFAULT 'monthly',
    status TEXT DEFAULT 'active',
    current_period_start TEXT,
    current_period_end TEXT,
    cancel_at_period_end INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

CREATE TABLE IF NOT EXISTS invitations (
    token TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    email TEXT NOT NULL,
    role TEXT DEFAULT 'member',
    invited_by TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (invited_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS revoked_tokens (
    jti TEXT PRIMARY KEY,
    revoked_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_org ON memories(org_id);
CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_org ON api_keys(org_id);
CREATE INDEX IF NOT EXISTS idx_usage_org ON usage_daily(org_id);
CREATE INDEX IF NOT EXISTS idx_revoked_tokens_jti ON revoked_tokens(jti);

CREATE TABLE IF NOT EXISTS facts (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    subject     TEXT NOT NULL,
    predicate   TEXT NOT NULL,
    object      TEXT NOT NULL,
    scope       TEXT NOT NULL DEFAULT 'private',
    valid_from  TEXT NOT NULL,
    valid_to    TEXT,
    supersedes  TEXT,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_facts_org_user ON facts(org_id, user_id);
CREATE INDEX IF NOT EXISTS idx_facts_subject_predicate ON facts(org_id, user_id, subject, predicate);
"""


class MetadataStore:

    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.sqlite_path

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()
            # Migrations: add columns to existing DBs
            for migration in [
                "ALTER TABLE organizations ADD COLUMN enc_secret TEXT",
                "ALTER TABLE organizations ADD COLUMN enc_salt TEXT",
                "ALTER TABLE organizations ADD COLUMN is_active INTEGER DEFAULT 1",
                "ALTER TABLE organizations ADD COLUMN deleted_at TEXT",
                "ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1",
                "ALTER TABLE users ADD COLUMN deleted_at TEXT",
                "ALTER TABLE organizations ADD COLUMN billing_name TEXT",
                "ALTER TABLE organizations ADD COLUMN billing_address_line1 TEXT",
                "ALTER TABLE organizations ADD COLUMN billing_address_line2 TEXT",
                "ALTER TABLE organizations ADD COLUMN billing_city TEXT",
                "ALTER TABLE organizations ADD COLUMN billing_zip TEXT",
                "ALTER TABLE organizations ADD COLUMN billing_country TEXT",
                "ALTER TABLE organizations ADD COLUMN billing_vat TEXT",
                "ALTER TABLE organizations ADD COLUMN billing_contact_name TEXT",
                "ALTER TABLE organizations ADD COLUMN billing_contact_email TEXT",
                "ALTER TABLE organizations ADD COLUMN billing_contact_phone TEXT",
                "ALTER TABLE plans ADD COLUMN stripe_product_id TEXT",
                "ALTER TABLE plans ADD COLUMN stripe_price_monthly_id TEXT",
                "ALTER TABLE plans ADD COLUMN stripe_price_annual_id TEXT",
                "ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'fr'",
                "ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN default_scope TEXT DEFAULT 'private'",
                "ALTER TABLE plans ADD COLUMN max_members INTEGER",
                "ALTER TABLE subscriptions ADD COLUMN max_members INTEGER",
                "ALTER TABLE users ADD COLUMN totp_secret TEXT",
                "ALTER TABLE users ADD COLUMN mfa_enabled INTEGER DEFAULT 0",
                "ALTER TABLE organizations ADD COLUMN kdf_salt TEXT",
                "ALTER TABLE organizations ADD COLUMN enc_migrated INTEGER DEFAULT 0",
            ]:
                try:
                    await db.execute(migration)
                    await db.commit()
                except Exception:
                    pass  # Column already exists
            # Seed plans depuis plans.py si la table est vide
            await self._seed_plans(db)
            # Pré-remplir les Stripe IDs connus
            await self._seed_stripe_ids(db)
            # Seed : org et user par défaut si absents
            await self._seed_defaults(db)
            await db.commit()

    async def _seed_plans(self, db):
        from api.plans import PLANS
        for i, (key, p) in enumerate(PLANS.items()):
            await db.execute(
                """INSERT OR IGNORE INTO plans
                   (key, label, max_memories, max_recalls_per_day, price_monthly, price_annual, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (key, p["label"], p["max_memories"], p["max_recalls_per_day"],
                 p.get("price_monthly"), p.get("price_annual"), i)
            )
        # Seed max_members si NULL (après migration)
        await self._seed_plan_limits(db)

    async def _seed_plan_limits(self, db):
        """Initialise max_members si non encore défini (NULL après migration)."""
        from api.plans import PLANS
        for key, p in PLANS.items():
            await db.execute(
                "UPDATE plans SET max_members = ? WHERE key = ? AND max_members IS NULL",
                (p.get("max_members", 1), key)
            )

    async def _seed_stripe_ids(self, db):
        """Pré-renseigne les Stripe IDs connus pour les plans Pro et Team."""
        pairs = [
            ("pro",  "price_1TOKNDF5GzDoKFskVM4ijqce", "price_1TOKNDF5GzDoKFskSEyM5ybR", "prod_UN4WHj19JRFNYl"),
            ("team", "price_1TOKNpF5GzDoKFskGaOvHk24", "price_1TOKNpF5GzDoKFski0dSl5WW", "prod_UN4WlpPamhAQ9G"),
        ]
        for key, pm, pa, prod_id in pairs:
            await db.execute(
                """UPDATE plans SET
                   stripe_product_id = COALESCE(stripe_product_id, ?),
                   stripe_price_monthly_id = COALESCE(stripe_price_monthly_id, ?),
                   stripe_price_annual_id = COALESCE(stripe_price_annual_id, ?)
                   WHERE key = ?""",
                (prod_id, pm, pa, key)
            )

    async def _seed_defaults(self, db):
        # E5 — ne seed que si les valeurs sont explicitement configurées
        if not settings.default_org_id or not settings.default_user_id:
            return
        now = datetime.utcnow().isoformat()
        await db.execute(
            "INSERT OR IGNORE INTO organizations (id, name, slug, plan, created_at) VALUES (?, ?, ?, ?, ?)",
            (settings.default_org_id, settings.default_org_name, settings.default_org_slug, "free", now)
        )
        await db.execute(
            "INSERT OR IGNORE INTO users (id, org_id, name, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (settings.default_user_id, settings.default_org_id, settings.default_user_name, "owner", now)
        )

    async def revoke_token(self, jti: str, expires_at: str):
        """E3 — Révoque un JWT par son jti."""
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO revoked_tokens (jti, revoked_at, expires_at) VALUES (?, ?, ?)",
                (jti, now, expires_at)
            )
            await db.commit()

    async def is_token_revoked(self, jti: str) -> bool:
        """Retourne True si le jti a été révoqué."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM revoked_tokens WHERE jti = ?", (jti,)
            )
            return await cursor.fetchone() is not None

    async def cleanup_expired_revoked_tokens(self):
        """Purge les tokens révoqués expirés (à appeler périodiquement)."""
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM revoked_tokens WHERE expires_at < ?", (now,))
            await db.commit()

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def create_user(self, user: "User") -> "User":
        async with aiosqlite.connect(self.db_path) as db:
            now = datetime.utcnow().isoformat()
            lang = getattr(user, "lang", "fr") or "fr"
            email_verified = getattr(user, "email_verified", 0)
            await db.execute(
                """INSERT INTO users (id, org_id, name, email, password_hash, role, created_at, lang, email_verified)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user.id, user.org_id, user.name, user.email,
                 user.password_hash, user.role, now, lang, email_verified)
            )
            await db.commit()
        return user

    async def get_user_by_email(self, email: str) -> "User | None":
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE email = ? AND is_active = 1 AND deleted_at IS NULL", (email,)
            ) as cursor:
                row = await cursor.fetchone()
        if not row:
            return None
        return User(
            id=row["id"],
            org_id=row["org_id"],
            name=row["name"],
            email=row["email"],
            password_hash=row["password_hash"],
            role=row["role"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    async def set_org_enc_key(self, org_id: str, enc_secret: str, enc_salt: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE organizations SET enc_secret = ?, enc_salt = ? WHERE id = ?",
                (enc_secret, enc_salt, org_id)
            )
            await db.commit()

    async def get_org_enc_key(self, org_id: str) -> tuple[str | None, str | None]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT enc_secret, enc_salt FROM organizations WHERE id = ?", (org_id,)
            ) as cursor:
                row = await cursor.fetchone()
        if not row:
            return None, None
        return row[0], row[1]

    # ── C2 — Zero-knowledge key derivation ───────────────────────────────────

    async def get_org_kdf_info(self, org_id: str) -> dict:
        """C2 — Retourne kdf_salt, enc_secret, enc_salt, enc_migrated pour une org."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT kdf_salt, enc_secret, enc_salt, enc_migrated FROM organizations WHERE id = ?",
                (org_id,)
            ) as cursor:
                row = await cursor.fetchone()
        if not row:
            return {"kdf_salt": None, "enc_secret": None, "enc_salt": None, "enc_migrated": 0}
        return {
            "kdf_salt": row[0],
            "enc_secret": row[1],
            "enc_salt": row[2],
            "enc_migrated": row[3] if row[3] is not None else 0,
        }

    async def set_org_kdf_salt(self, org_id: str, kdf_salt: str):
        """C2 — Stocke kdf_salt pour une org. Serveur ne connaît jamais la clé dérivée."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE organizations SET kdf_salt = ? WHERE id = ?",
                (kdf_salt, org_id)
            )
            await db.commit()

    async def mark_org_migrated(self, org_id: str):
        """C2 — Marque l'org comme migrée : efface enc_secret, pose enc_migrated=1."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE organizations SET enc_migrated = 1, enc_secret = NULL, enc_salt = NULL WHERE id = ?",
                (org_id,)
            )
            await db.commit()

    async def get_user_by_id(self, user_id: str) -> "User | None":
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE id = ? AND is_active = 1 AND deleted_at IS NULL", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
        if not row:
            return None
        return User(
            id=row["id"],
            org_id=row["org_id"],
            name=row["name"],
            email=row["email"],
            password_hash=row["password_hash"],
            role=row["role"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    async def update_user_profile(self, user_id: str, name: str = None, email: str = None) -> bool:
        """Met à jour nom et/ou email de l'utilisateur."""
        async with aiosqlite.connect(self.db_path) as db:
            if name and email:
                cursor = await db.execute(
                    "UPDATE users SET name = ?, email = ? WHERE id = ?", (name, email, user_id)
                )
            elif name:
                cursor = await db.execute(
                    "UPDATE users SET name = ? WHERE id = ?", (name, user_id)
                )
            elif email:
                cursor = await db.execute(
                    "UPDATE users SET email = ? WHERE id = ?", (email, user_id)
                )
            else:
                return False
            await db.commit()
        return cursor.rowcount > 0

    async def soft_delete_user(self, user_id: str, org_id: str) -> bool:
        """Soft-delete user + org (données conservées 30j pour conformité RGPD)."""
        async with aiosqlite.connect(self.db_path) as db:
            now = datetime.utcnow().isoformat()
            await db.execute(
                "UPDATE users SET is_active = 0, deleted_at = ? WHERE id = ?", (now, user_id)
            )
            await db.execute(
                "UPDATE organizations SET is_active = 0, deleted_at = ? WHERE id = ?", (now, org_id)
            )
            await db.commit()
        return True

    async def get_org_by_id(self, org_id: str) -> dict | None:
        """Retourne une organisation complète."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM organizations WHERE id = ?", (org_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return dict(row) if row else None

    async def update_org_profile(self, org_id: str, name: str = None,
                                  billing_name: str = None, billing_address_line1: str = None,
                                  billing_address_line2: str = None, billing_city: str = None,
                                  billing_zip: str = None, billing_country: str = None,
                                  billing_vat: str = None) -> bool:
        """Met à jour le profil de l'organisation (nom + facturation)."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """UPDATE organizations SET
                   name = COALESCE(?, name),
                   billing_name = ?,
                   billing_address_line1 = ?,
                   billing_address_line2 = ?,
                   billing_city = ?,
                   billing_zip = ?,
                   billing_country = ?,
                   billing_vat = ?
                   WHERE id = ?""",
                (name, billing_name, billing_address_line1, billing_address_line2,
                 billing_city, billing_zip, billing_country, billing_vat, org_id)
            )
            await db.commit()
        return cursor.rowcount > 0

    async def get_user_lang(self, user_id: str) -> str:
        """Retourne la langue de l'utilisateur (fr par défaut)."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT lang FROM users WHERE id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return (row[0] if row and row[0] else "fr")

    async def update_user_password(self, user_id: str, password_hash: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, user_id)
            )
            await db.commit()
        return cursor.rowcount > 0

    async def get_user_mfa(self, user_id: str) -> dict:
        """Retourne le statut MFA et le secret TOTP d'un utilisateur."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT totp_secret, mfa_enabled FROM users WHERE id = ?", (user_id,)
            )
            row = await cursor.fetchone()
        if not row:
            return {"totp_secret": None, "mfa_enabled": False}
        return {"totp_secret": _decrypt_totp(row[0]), "mfa_enabled": bool(row[1])}

    async def set_totp_secret(self, user_id: str, secret: str) -> None:
        """Stocke le secret TOTP chiffré (F3 — chiffrement au repos)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET totp_secret = ? WHERE id = ?", (_encrypt_totp(secret), user_id)
            )
            await db.commit()

    async def enable_mfa(self, user_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET mfa_enabled = 1 WHERE id = ?", (user_id,)
            )
            await db.commit()

    async def disable_mfa(self, user_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET mfa_enabled = 0, totp_secret = NULL WHERE id = ?", (user_id,)
            )
            await db.commit()

    async def create_verification_token(self, user_id: str) -> str:
        """Crée un token de vérification email (valide 24h)."""
        import secrets as _secrets
        from datetime import timedelta
        token = _secrets.token_urlsafe(32)
        expires_at = (datetime.utcnow() + timedelta(hours=24)).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO email_verification_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_id, expires_at)
            )
            await db.commit()
        return token

    async def use_verification_token(self, token: str) -> str | None:
        """Valide le token, marque comme utilisé, met email_verified=1. Retourne user_id ou None."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT user_id, expires_at, used FROM email_verification_tokens WHERE token = ?",
                (token,)
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                return None
            user_id, expires_at, used = row
            if used:
                return None
            if datetime.utcnow() > datetime.fromisoformat(expires_at):
                return None
            await db.execute(
                "UPDATE email_verification_tokens SET used = 1 WHERE token = ?", (token,)
            )
            await db.execute(
                "UPDATE users SET email_verified = 1 WHERE id = ?", (user_id,)
            )
            await db.commit()
        return user_id

    async def create_reset_token(self, user_id: str) -> str:
        """Crée un token de reset de mot de passe (valide 1h). Invalide les anciens."""
        import secrets as _secrets
        from datetime import timedelta
        token = _secrets.token_urlsafe(32)
        expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            # Invalide tous les tokens non utilisés existants pour cet user
            await db.execute(
                "UPDATE password_reset_tokens SET used = 1 WHERE user_id = ? AND used = 0",
                (user_id,)
            )
            await db.execute(
                "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_id, expires_at)
            )
            await db.commit()
        return token

    async def use_reset_token(self, token: str) -> str | None:
        """Valide le token de reset, le marque comme utilisé. Retourne user_id ou None."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT user_id, expires_at, used FROM password_reset_tokens WHERE token = ?",
                (token,)
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                return None
            user_id, expires_at, used = row
            if used:
                return None
            if datetime.utcnow() > datetime.fromisoformat(expires_at):
                return None
            await db.execute(
                "UPDATE password_reset_tokens SET used = 1 WHERE token = ?", (token,)
            )
            await db.commit()
        return user_id

    # ── Members ───────────────────────────────────────────────────────────────

    async def get_org_members(self, org_id: str) -> list[dict]:
        """Retourne les membres actifs d'une organisation."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT id, name, email, role, created_at, email_verified, default_scope
                   FROM users WHERE org_id = ? AND is_active = 1 AND deleted_at IS NULL
                   ORDER BY created_at ASC""",
                (org_id,)
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def count_org_members(self, org_id: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE org_id = ? AND is_active = 1 AND deleted_at IS NULL",
                (org_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return row[0] if row else 0

    async def get_org_max_members(self, org_id: str) -> int:
        """Retourne la limite de membres : depuis subscription si dispo, sinon depuis le plan."""
        async with aiosqlite.connect(self.db_path) as db:
            # D'abord tenter depuis la subscription (override admin)
            async with db.execute(
                "SELECT max_members, plan FROM subscriptions WHERE org_id = ?", (org_id,)
            ) as cursor:
                sub = await cursor.fetchone()
            if sub and sub[0] is not None:
                return sub[0]
            # Fallback sur le plan de l'org
            async with db.execute(
                "SELECT plan FROM organizations WHERE id = ?", (org_id,)
            ) as cursor:
                org = await cursor.fetchone()
            plan_key = (sub[1] if sub else None) or (org[0] if org else "free")
            async with db.execute(
                "SELECT max_members FROM plans WHERE key = ?", (plan_key,)
            ) as cursor:
                plan = await cursor.fetchone()
        return plan[0] if plan and plan[0] is not None else 1

    async def update_member_role(self, user_id: str, org_id: str, role: str) -> bool:
        if role not in ("admin", "member"):
            return False
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE users SET role = ? WHERE id = ? AND org_id = ? AND role != 'owner'",
                (role, user_id, org_id)
            )
            await db.commit()
        return cursor.rowcount > 0

    async def remove_member(self, user_id: str, org_id: str) -> bool:
        """Retire un membre de l'org (soft-delete user uniquement, pas l'org)."""
        async with aiosqlite.connect(self.db_path) as db:
            now = datetime.utcnow().isoformat()
            cursor = await db.execute(
                "UPDATE users SET is_active = 0, deleted_at = ? WHERE id = ? AND org_id = ? AND role != 'owner'",
                (now, user_id, org_id)
            )
            await db.commit()
        return cursor.rowcount > 0

    async def update_user_default_scope(self, user_id: str, default_scope: str) -> bool:
        if default_scope not in ("private", "org"):
            return False
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE users SET default_scope = ? WHERE id = ?", (default_scope, user_id)
            )
            await db.commit()
        return cursor.rowcount > 0

    async def get_user_default_scope(self, user_id: str) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT default_scope FROM users WHERE id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return row[0] if row and row[0] else "private"

    # ── Invitations ───────────────────────────────────────────────────────────

    async def create_invitation(self, org_id: str, email: str, role: str, invited_by: str) -> str:
        import secrets as _secrets
        from datetime import timedelta
        token = _secrets.token_urlsafe(32)
        now = datetime.utcnow().isoformat()
        expires_at = (datetime.utcnow() + timedelta(days=7)).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            # Invalide les invitations en attente pour ce même email dans cette org
            await db.execute(
                "UPDATE invitations SET used = 1 WHERE org_id = ? AND email = ? AND used = 0",
                (org_id, email.lower())
            )
            await db.execute(
                "INSERT INTO invitations (token, org_id, email, role, invited_by, expires_at, used, created_at) VALUES (?,?,?,?,?,?,0,?)",
                (token, org_id, email.lower(), role, invited_by, expires_at, now)
            )
            await db.commit()
        return token

    async def get_invitation(self, token: str) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT i.*, o.name as org_name
                   FROM invitations i JOIN organizations o ON o.id = i.org_id
                   WHERE i.token = ?""",
                (token,)
            ) as cursor:
                row = await cursor.fetchone()
        return dict(row) if row else None

    async def use_invitation(self, token: str) -> dict | None:
        """Valide et consomme le token. Retourne l'invitation ou None si invalide."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM invitations WHERE token = ?", (token,)
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                return None
            inv = dict(row)
            if inv["used"]:
                return None
            if datetime.utcnow() > datetime.fromisoformat(inv["expires_at"]):
                return None
            await db.execute(
                "UPDATE invitations SET used = 1 WHERE token = ?", (token,)
            )
            await db.commit()
        return inv

    async def list_pending_invitations(self, org_id: str) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT token, email, role, expires_at, created_at
                   FROM invitations WHERE org_id = ? AND used = 0 AND expires_at > ?
                   ORDER BY created_at DESC""",
                (org_id, datetime.utcnow().isoformat())
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def cancel_invitation(self, token: str, org_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE invitations SET used = 1 WHERE token = ? AND org_id = ?",
                (token, org_id)
            )
            await db.commit()
        return cursor.rowcount > 0

    async def update_subscription_max_members(self, org_id: str, max_members: int) -> bool:
        """Override admin : modifie le nombre max de membres pour une subscription."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE subscriptions SET max_members = ? WHERE org_id = ?",
                (max_members, org_id)
            )
            await db.commit()
        return cursor.rowcount > 0

    # ── Memories ──────────────────────────────────────────────────────────────

    async def save_memory(self, memory: Memory) -> Memory:
        async with aiosqlite.connect(self.db_path) as db:
            now = datetime.utcnow().isoformat()
            await db.execute(
                """INSERT OR REPLACE INTO memories
                   (id, org_id, user_id, content, category, source, scope, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (memory.id, memory.org_id, memory.user_id, memory.content,
                 memory.category, memory.source, memory.scope, now, now)
            )
            # Tags
            await db.execute("DELETE FROM tags WHERE memory_id = ?", (memory.id,))
            for tag in memory.tags:
                await db.execute(
                    "INSERT OR IGNORE INTO tags (memory_id, tag) VALUES (?, ?)",
                    (memory.id, tag.lower().strip())
                )
            # Catégorie — incrémenter usage
            if memory.category:
                await db.execute(
                    """INSERT INTO categories (org_id, name, usage_count) VALUES (?, ?, 1)
                       ON CONFLICT(org_id, name) DO UPDATE SET usage_count = usage_count + 1""",
                    (memory.org_id, memory.category)
                )
            await db.commit()
        return memory

    async def get_memory(self, memory_id: str, org_id: str) -> Memory | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM memories WHERE id = ? AND org_id = ?",
                (memory_id, org_id)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
            tags = await self._get_tags(db, memory_id)
            return self._row_to_memory(row, tags)

    async def get_memories_by_ids(self, memory_ids: list[str], org_id: str) -> list[Memory]:
        if not memory_ids:
            return []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            placeholders = ",".join("?" * len(memory_ids))
            async with db.execute(
                f"SELECT * FROM memories WHERE id IN ({placeholders}) AND org_id = ?",
                (*memory_ids, org_id)
            ) as cursor:
                rows = await cursor.fetchall()
            result = []
            for row in rows:
                tags = await self._get_tags(db, row["id"])
                result.append(self._row_to_memory(row, tags))
            return result

    async def delete_memory(self, memory_id: str, org_id: str, user_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, scope FROM memories WHERE id = ? AND org_id = ?",
                (memory_id, org_id)
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                return False
            await db.execute("DELETE FROM tags WHERE memory_id = ?", (memory_id,))
            await db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            await db.commit()
            return True

    async def list_memories(
        self,
        org_id: str,
        user_id: str,
        scope: str = "private",
        category: str = None,
        limit: int = 50,
        offset: int = 0
    ) -> list[Memory]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            conditions = ["org_id = ?"]
            params: list = [org_id]
            if scope == "private":
                conditions.append("user_id = ?")
                params.append(user_id)
            if category:
                conditions.append("category = ?")
                params.append(category)
            where = " AND ".join(conditions)
            params += [limit, offset]
            async with db.execute(
                f"SELECT * FROM memories WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params
            ) as cursor:
                rows = await cursor.fetchall()
            result = []
            for row in rows:
                tags = await self._get_tags(db, row["id"])
                result.append(self._row_to_memory(row, tags))
            return result

    # ── API Keys ──────────────────────────────────────────────────────────────

    async def create_api_key(self, key_id: str, org_id: str, user_id: str,
                              name: str, key_hash: str, prefix: str) -> dict:
        async with aiosqlite.connect(self.db_path) as db:
            now = datetime.utcnow().isoformat()
            await db.execute(
                """INSERT INTO api_keys (id, org_id, user_id, name, key_hash, prefix, created_at, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
                (key_id, org_id, user_id, name, key_hash, prefix, now)
            )
            await db.commit()
        return {"id": key_id, "org_id": org_id, "name": name,
                "prefix": prefix, "created_at": now, "is_active": True}

    async def list_api_keys(self, org_id: str) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT id, org_id, user_id, name, prefix, created_at, last_used_at, is_active
                   FROM api_keys WHERE org_id = ? ORDER BY created_at DESC""",
                (org_id,)
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_api_key_by_hash(self, key_hash: str) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM api_keys WHERE key_hash = ? AND is_active = 1",
                (key_hash,)
            ) as cursor:
                row = await cursor.fetchone()
        return dict(row) if row else None

    async def touch_api_key(self, key_id: str):
        """Met à jour last_used_at."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), key_id)
            )
            await db.commit()

    async def revoke_api_key(self, key_id: str, org_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE api_keys SET is_active = 0 WHERE id = ? AND org_id = ?",
                (key_id, org_id)
            )
            await db.commit()
        return cursor.rowcount > 0

    # ── Usage ─────────────────────────────────────────────────────────────────

    async def increment_usage(self, org_id: str, field: str):
        """Incrémente un compteur pour aujourd'hui (memories_created ou recalls)."""
        _VALID_USAGE_FIELDS = {"memories_created", "recalls", "memories_deleted"}
        if field not in _VALID_USAGE_FIELDS:
            raise ValueError(f"Champ usage invalide : {field!r}")
        today = datetime.utcnow().date().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"""INSERT INTO usage_daily (org_id, date, {field})
                    VALUES (?, ?, 1)
                    ON CONFLICT(org_id, date) DO UPDATE SET {field} = {field} + 1""",
                (org_id, today)
            )
            await db.commit()

    async def get_usage_today(self, org_id: str) -> dict:
        """Retourne les compteurs d'aujourd'hui."""
        today = datetime.utcnow().date().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT memories_created, recalls FROM usage_daily WHERE org_id = ? AND date = ?",
                (org_id, today)
            ) as cursor:
                row = await cursor.fetchone()
        return {"memories_created": row[0] if row else 0, "recalls": row[1] if row else 0}

    async def get_usage_month(self, org_id: str, year_month: str | None = None) -> dict:
        """Retourne les totaux du mois (format YYYY-MM, défaut = mois courant)."""
        if not year_month:
            year_month = datetime.utcnow().strftime("%Y-%m")
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT COALESCE(SUM(memories_created), 0), COALESCE(SUM(recalls), 0)
                   FROM usage_daily WHERE org_id = ? AND date LIKE ?""",
                (org_id, f"{year_month}%")
            ) as cursor:
                row = await cursor.fetchone()
        return {"memories_created": row[0] if row else 0, "recalls": row[1] if row else 0}

    async def get_usage_history(self, org_id: str, days: int = 30) -> list[dict]:
        """Retourne l'historique jour par jour (N derniers jours)."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT date, memories_created, recalls
                   FROM usage_daily WHERE org_id = ?
                   ORDER BY date DESC LIMIT ?""",
                (org_id, days)
            ) as cursor:
                rows = await cursor.fetchall()
        return [{"date": r[0], "memories_created": r[1], "recalls": r[2]} for r in rows]

    async def count_memories(self, org_id: str, user_id: str | None = None) -> int:
        """Compte le nombre total de mémoires pour l'org (ou l'user si précisé)."""
        async with aiosqlite.connect(self.db_path) as db:
            if user_id:
                async with db.execute(
                    "SELECT COUNT(*) FROM memories WHERE org_id = ? AND user_id = ?",
                    (org_id, user_id)
                ) as cursor:
                    row = await cursor.fetchone()
            else:
                async with db.execute(
                    "SELECT COUNT(*) FROM memories WHERE org_id = ?",
                    (org_id,)
                ) as cursor:
                    row = await cursor.fetchone()
        return row[0] if row else 0

    async def get_org_plan(self, org_id: str) -> str:
        """Retourne le plan de l'organisation."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT plan FROM organizations WHERE id = ? AND is_active = 1 AND deleted_at IS NULL", (org_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return row[0] if row else "free"

    async def is_org_active(self, org_id: str) -> bool:
        """Vérifie si l'organisation est active et non supprimée."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id FROM organizations WHERE id = ? AND is_active = 1 AND deleted_at IS NULL", (org_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return row is not None

    async def update_org_plan(self, org_id: str, plan: str) -> bool:
        """Met à jour le plan d'une organisation."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE organizations SET plan = ? WHERE id = ?", (plan, org_id)
            )
            await db.commit()
        return cursor.rowcount > 0

    # ── Admin ─────────────────────────────────────────────────────────────────

    async def admin_update_org(self, org_id: str, name: str,
                               billing_name: str = None, billing_address_line1: str = None,
                               billing_address_line2: str = None, billing_city: str = None,
                               billing_zip: str = None, billing_country: str = None,
                               billing_vat: str = None, billing_contact_name: str = None,
                               billing_contact_email: str = None, billing_contact_phone: str = None) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """UPDATE organizations SET
                   name = ?, billing_name = ?, billing_address_line1 = ?,
                   billing_address_line2 = ?, billing_city = ?, billing_zip = ?,
                   billing_country = ?, billing_vat = ?,
                   billing_contact_name = ?, billing_contact_email = ?, billing_contact_phone = ?
                   WHERE id = ?""",
                (name, billing_name, billing_address_line1, billing_address_line2,
                 billing_city, billing_zip, billing_country, billing_vat,
                 billing_contact_name, billing_contact_email, billing_contact_phone, org_id)
            )
            await db.commit()
        return cursor.rowcount > 0

    async def admin_set_org_status(self, org_id: str, is_active: bool, soft_delete: bool = False) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            deleted_at = datetime.utcnow().isoformat() if soft_delete else None
            cursor = await db.execute(
                "UPDATE organizations SET is_active = ?, deleted_at = ? WHERE id = ?",
                (1 if is_active else 0, deleted_at, org_id)
            )
            await db.commit()
        return cursor.rowcount > 0

    async def admin_update_user(self, user_id: str, name: str, email: str, org_id: str = None) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            if org_id:
                cursor = await db.execute(
                    "UPDATE users SET name = ?, email = ?, org_id = ? WHERE id = ?",
                    (name, email, org_id, user_id)
                )
            else:
                cursor = await db.execute(
                    "UPDATE users SET name = ?, email = ? WHERE id = ?", (name, email, user_id)
                )
            await db.commit()
        return cursor.rowcount > 0

    async def admin_soft_delete_org_users(self, org_id: str):
        """Supprime logiquement tous les users d'une org (cascade sur delete org)."""
        async with aiosqlite.connect(self.db_path) as db:
            deleted_at = datetime.utcnow().isoformat()
            await db.execute(
                "UPDATE users SET is_active = 0, deleted_at = ? WHERE org_id = ? AND deleted_at IS NULL",
                (deleted_at, org_id)
            )
            await db.commit()

    async def admin_set_user_status(self, user_id: str, is_active: bool, soft_delete: bool = False) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            deleted_at = datetime.utcnow().isoformat() if soft_delete else None
            cursor = await db.execute(
                "UPDATE users SET is_active = ?, deleted_at = ? WHERE id = ?",
                (1 if is_active else 0, deleted_at, user_id)
            )
            await db.commit()
        return cursor.rowcount > 0

    async def list_all_orgs(self) -> list[dict]:
        """Retourne toutes les orgs avec leurs stats (admin — pas de filtre is_active)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT o.id, o.name, o.slug, o.plan, o.created_at,
                       o.is_active, o.deleted_at,
                       o.billing_name, o.billing_address_line1, o.billing_address_line2,
                       o.billing_city, o.billing_zip, o.billing_country, o.billing_vat,
                       o.billing_contact_name, o.billing_contact_email, o.billing_contact_phone,
                       COUNT(DISTINCT u.id) as user_count,
                       COUNT(DISTINCT m.id) as memory_count
                FROM organizations o
                LEFT JOIN users u ON u.org_id = o.id
                LEFT JOIN memories m ON m.org_id = o.id
                GROUP BY o.id
                ORDER BY o.created_at DESC
            """) as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def list_all_users(self) -> list[dict]:
        """Retourne tous les utilisateurs avec leur org (admin — pas de filtre is_active)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT u.id, u.name, u.email, u.role, u.created_at,
                       u.is_active, u.deleted_at,
                       o.name as org_name, o.plan as org_plan, o.id as org_id
                FROM users u
                JOIN organizations o ON o.id = u.org_id
                ORDER BY u.created_at DESC
            """) as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_global_stats(self) -> dict:
        """Retourne les stats globales de la plateforme."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM organizations") as c:
                orgs = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM users") as c:
                users = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM memories") as c:
                memories = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM organizations WHERE plan != 'free'") as c:
                paid = (await c.fetchone())[0]
            async with db.execute(
                "SELECT COALESCE(SUM(recalls),0), COALESCE(SUM(memories_created),0) FROM usage_daily"
            ) as c:
                row = await c.fetchone()
                total_recalls, total_writes = row[0], row[1]
        return {
            "orgs": orgs, "users": users, "memories": memories,
            "paid_orgs": paid, "total_recalls": total_recalls, "total_writes": total_writes,
        }

    # ── Subscriptions ─────────────────────────────────────────────────────────

    async def get_subscription(self, org_id: str) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM subscriptions WHERE org_id = ?", (org_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_subscription_by_customer(self, stripe_customer_id: str) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM subscriptions WHERE stripe_customer_id = ?", (stripe_customer_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return dict(row) if row else None

    async def upsert_subscription(self, org_id: str, stripe_customer_id: str,
                                   stripe_subscription_id: str = None, stripe_price_id: str = None,
                                   plan: str = "free", period: str = "monthly",
                                   status: str = "active", current_period_start: str = None,
                                   current_period_end: str = None, cancel_at_period_end: bool = False,
                                   max_members: int = None) -> dict:
        import uuid
        now = datetime.utcnow().isoformat()
        # Si max_members non fourni, le lire depuis le plan
        if max_members is None:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT max_members FROM plans WHERE key = ?", (plan,)
                ) as cursor:
                    row = await cursor.fetchone()
            max_members = row[0] if row and row[0] is not None else 1
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO subscriptions
                   (id, org_id, stripe_customer_id, stripe_subscription_id, stripe_price_id,
                    plan, period, status, current_period_start, current_period_end,
                    cancel_at_period_end, max_members, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(org_id) DO UPDATE SET
                   stripe_customer_id = excluded.stripe_customer_id,
                   stripe_subscription_id = COALESCE(excluded.stripe_subscription_id, stripe_subscription_id),
                   stripe_price_id = COALESCE(excluded.stripe_price_id, stripe_price_id),
                   plan = excluded.plan,
                   period = excluded.period,
                   status = excluded.status,
                   current_period_start = COALESCE(excluded.current_period_start, current_period_start),
                   current_period_end = COALESCE(excluded.current_period_end, current_period_end),
                   cancel_at_period_end = excluded.cancel_at_period_end,
                   max_members = excluded.max_members,
                   updated_at = excluded.updated_at""",
                (str(uuid.uuid4()), org_id, stripe_customer_id, stripe_subscription_id,
                 stripe_price_id, plan, period, status, current_period_start,
                 current_period_end, 1 if cancel_at_period_end else 0, max_members, now, now)
            )
            await db.commit()
        return await self.get_subscription(org_id)

    async def list_all_subscriptions(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT s.*, o.name as org_name
                FROM subscriptions s
                JOIN organizations o ON o.id = s.org_id
                ORDER BY s.created_at DESC
            """) as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def set_org_stripe_customer(self, org_id: str, stripe_customer_id: str):
        """Stocke le customer Stripe sur l'org directement (avant création sub)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE organizations SET settings = json_set(COALESCE(settings,'{}'), '$.stripe_customer_id', ?) WHERE id = ?",
                (stripe_customer_id, org_id)
            )
            await db.commit()

    async def update_plan_stripe_ids(self, key: str, stripe_product_id: str = None,
                                      stripe_price_monthly_id: str = None,
                                      stripe_price_annual_id: str = None) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """UPDATE plans SET
                   stripe_product_id = COALESCE(?, stripe_product_id),
                   stripe_price_monthly_id = COALESCE(?, stripe_price_monthly_id),
                   stripe_price_annual_id = COALESCE(?, stripe_price_annual_id)
                   WHERE key = ?""",
                (stripe_product_id, stripe_price_monthly_id, stripe_price_annual_id, key)
            )
            await db.commit()
        return cursor.rowcount > 0

    # ── Plans ─────────────────────────────────────────────────────────────────

    async def get_plan_by_stripe_price_id(self, price_id: str) -> dict | None:
        """Retourne (plan_key, period) depuis un Stripe Price ID stocké en DB."""
        if not price_id:
            return None
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT key,
                          CASE WHEN stripe_price_monthly_id = ? THEN 'monthly'
                               WHEN stripe_price_annual_id  = ? THEN 'annual'
                               ELSE NULL END AS period
                   FROM plans
                   WHERE (stripe_price_monthly_id = ? OR stripe_price_annual_id = ?)
                     AND is_active = 1 AND deleted_at IS NULL
                   LIMIT 1""",
                (price_id, price_id, price_id, price_id)
            ) as cur:
                row = await cur.fetchone()
                if row:
                    return {"plan": row["key"], "period": row["period"]}
        return None

    async def get_plan(self, key: str) -> dict:
        """Retourne un plan depuis la DB ; fallback sur plans.py si absent."""
        from api.plans import PLANS
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM plans WHERE key = ?", (key,)
            ) as cursor:
                row = await cursor.fetchone()
        if row:
            return dict(row)
        return PLANS.get(key, PLANS["free"])

    async def list_all_plans(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM plans ORDER BY sort_order, key"
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def create_plan(self, key: str, label: str, max_memories: int,
                          max_recalls_per_day: int, price_monthly, price_annual,
                          sort_order: int = 99) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    """INSERT INTO plans (key, label, max_memories, max_recalls_per_day,
                       price_monthly, price_annual, sort_order) VALUES (?,?,?,?,?,?,?)""",
                    (key, label, max_memories, max_recalls_per_day,
                     price_monthly, price_annual, sort_order)
                )
                await db.commit()
                return True
            except Exception:
                return False

    async def update_plan(self, key: str, label: str, max_memories: int,
                          max_recalls_per_day: int, price_monthly, price_annual) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """UPDATE plans SET label=?, max_memories=?, max_recalls_per_day=?,
                   price_monthly=?, price_annual=? WHERE key=?""",
                (label, max_memories, max_recalls_per_day, price_monthly, price_annual, key)
            )
            await db.commit()
        return cursor.rowcount > 0

    async def set_plan_status(self, key: str, is_active: bool, soft_delete: bool = False) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            deleted_at = datetime.utcnow().isoformat() if soft_delete else None
            cursor = await db.execute(
                "UPDATE plans SET is_active=?, deleted_at=? WHERE key=?",
                (1 if is_active else 0, deleted_at, key)
            )
            await db.commit()
        return cursor.rowcount > 0

    # ── Categories ────────────────────────────────────────────────────────────

    async def get_categories(self, org_id: str, limit: int = 20) -> list[CategorySuggestion]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT name, usage_count FROM categories WHERE org_id = ? ORDER BY usage_count DESC LIMIT ?",
                (org_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
            return [CategorySuggestion(name=r[0], usage_count=r[1]) for r in rows]

    # ── Facts (Temporal Knowledge Graph) ─────────────────────────────────────

    async def create_fact(self, fact) -> "Fact":
        from api.models import Fact
        from datetime import date
        today = date.today().isoformat()
        fact_id = fact.id if hasattr(fact, "id") and fact.id else str(__import__("uuid").uuid4())
        valid_from = fact.valid_from or today
        now = datetime.utcnow().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            # Auto-invalider le fait précédent si même (org, user, subject, predicate, scope) actif
            supersedes = None
            async with db.execute(
                """SELECT id FROM facts
                   WHERE org_id=? AND user_id=? AND subject=? AND predicate=? AND scope=? AND valid_to IS NULL
                   ORDER BY created_at DESC LIMIT 1""",
                (fact.org_id, fact.user_id, fact.subject, fact.predicate, fact.scope)
            ) as cursor:
                row = await cursor.fetchone()
            if row:
                supersedes = row[0]
                await db.execute(
                    "UPDATE facts SET valid_to=? WHERE id=?",
                    (today, supersedes)
                )
            await db.execute(
                """INSERT INTO facts (id, org_id, user_id, subject, predicate, object, scope,
                                     valid_from, valid_to, supersedes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
                (fact_id, fact.org_id, fact.user_id, fact.subject, fact.predicate,
                 fact.object, fact.scope, valid_from, supersedes, now)
            )
            await db.commit()

        return Fact(
            id=fact_id, org_id=fact.org_id, user_id=fact.user_id,
            subject=fact.subject, predicate=fact.predicate, object=fact.object,
            scope=fact.scope, valid_from=valid_from, valid_to=None,
            supersedes=supersedes, created_at=datetime.fromisoformat(now)
        )

    async def list_facts(self, org_id: str, user_id: str, scope: str = "private",
                         subject: str = None, predicate: str = None,
                         include_history: bool = False) -> list["Fact"]:
        from api.models import Fact
        conditions = ["org_id=?", "user_id=?", "scope=?"]
        params: list = [org_id, user_id, scope]
        if not include_history:
            conditions.append("valid_to IS NULL")
        if subject:
            conditions.append("subject=?")
            params.append(subject)
        if predicate:
            conditions.append("predicate=?")
            params.append(predicate)
        query = f"SELECT * FROM facts WHERE {' AND '.join(conditions)} ORDER BY created_at DESC"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_fact(r) for r in rows]

    async def get_fact(self, fact_id: str, org_id: str) -> "Fact | None":
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM facts WHERE id=? AND org_id=?", (fact_id, org_id)
            ) as cursor:
                row = await cursor.fetchone()
        return self._row_to_fact(row) if row else None

    async def invalidate_fact(self, fact_id: str, org_id: str, valid_to: str = None) -> bool:
        from datetime import date
        valid_to = valid_to or date.today().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE facts SET valid_to=? WHERE id=? AND org_id=? AND valid_to IS NULL",
                (valid_to, fact_id, org_id)
            )
            await db.commit()
        return cursor.rowcount > 0

    async def get_fact_contradictions(self, org_id: str, user_id: str, scope: str = "private") -> list[dict]:
        """Retourne les (subject, predicate) avec plusieurs facts actifs (valid_to IS NULL)."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT subject, predicate, COUNT(*) as cnt
                   FROM facts
                   WHERE org_id=? AND user_id=? AND scope=? AND valid_to IS NULL
                   GROUP BY subject, predicate HAVING cnt > 1""",
                (org_id, user_id, scope)
            ) as cursor:
                rows = await cursor.fetchall()
        return [{"subject": r[0], "predicate": r[1], "active_count": r[2]} for r in rows]

    def _row_to_fact(self, row) -> "Fact":
        from api.models import Fact
        return Fact(
            id=row["id"], org_id=row["org_id"], user_id=row["user_id"],
            subject=row["subject"], predicate=row["predicate"], object=row["object"],
            scope=row["scope"], valid_from=row["valid_from"], valid_to=row["valid_to"],
            supersedes=row["supersedes"],
            created_at=datetime.fromisoformat(row["created_at"])
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_tags(self, db, memory_id: str) -> list[str]:
        async with db.execute(
            "SELECT tag FROM tags WHERE memory_id = ?", (memory_id,)
        ) as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]

    def _row_to_memory(self, row, tags: list[str]) -> Memory:
        return Memory(
            id=row["id"],
            org_id=row["org_id"],
            user_id=row["user_id"],
            content=row["content"],
            category=row["category"],
            source=row["source"],
            scope=row["scope"],
            tags=tags,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"])
        )


_store: MetadataStore | None = None


async def get_metadata_store() -> MetadataStore:
    global _store
    if _store is None:
        _store = MetadataStore()
        await _store.init()
    return _store
