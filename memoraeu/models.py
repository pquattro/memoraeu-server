from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
import uuid


# ── Organizations ──────────────────────────────────────────────────────────────

class OrganizationCreate(BaseModel):
    name: str
    slug: str
    plan: Literal["free", "pro", "team", "enterprise"] = "free"
    settings: Optional[dict] = None


class Organization(OrganizationCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True


# ── Users ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    org_id: str
    name: str
    email: Optional[str] = None
    role: Literal["owner", "admin", "member"] = "member"
    settings: Optional[dict] = None


class User(UserCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    password_hash: Optional[str] = None
    lang: str = "fr"
    email_verified: int = 0
    is_active: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True


class UserRegister(BaseModel):
    name: str
    email: str
    password: str
    lang: str = "fr"  # langue de l'interface au moment de l'inscription


class UserLogin(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    org_id: str
    name: str
    plan: str = "free"
    role: str = "member"
    is_admin: bool = False
    # C2 — ZK: client derives enc_key = PBKDF2(password, kdf_salt) locally
    kdf_salt: Optional[str] = None
    needs_reencryption: bool = False
    # Legacy — only included when needs_reencryption=True (migration, one last time)
    enc_secret: Optional[str] = None
    enc_salt: Optional[str] = None


# ── Memories ───────────────────────────────────────────────────────────────────

class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=1, description="Texte brut de la mémoire")
    category: Optional[str] = Field(None, description="Catégorie libre (suggérée auto)")
    tags: list[str] = Field(default_factory=list)
    source: Literal["claude_desktop", "api", "manual", "sdk", "mcp_sse"] = "api"
    scope: Literal["private", "org"] = "private"
    pre_processed: bool = Field(False, description="Si True, skip compression et catégorisation (contenu déjà traité/chiffré côté client)")
    embedding: Optional[list[float]] = Field(None, description="Embedding pré-calculé côté client (zero-knowledge)")
    # org_id et user_id injectés par l'API selon le contexte
    org_id: Optional[str] = None
    user_id: Optional[str] = None


class Memory(MemoryCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str
    user_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    scope: Optional[Literal["private", "org"]] = None


# ── Search ─────────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(10, ge=1, le=50)
    scope: Literal["private", "org", "all"] = "private"
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    org_id: Optional[str] = None
    user_id: Optional[str] = None


class SearchResult(BaseModel):
    memory: Memory
    score: float = Field(..., description="Score de similarité cosinus [0-1]")


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    query: str


# ── API Keys ───────────────────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)

class ApiKeyResponse(BaseModel):
    id: str
    name: str
    prefix: str
    created_at: str
    last_used_at: Optional[str] = None
    is_active: bool

class ApiKeyCreated(ApiKeyResponse):
    """Retourné une seule fois à la création — contient la clé complète."""
    key: str

# ── Categories ─────────────────────────────────────────────────────────────────

class CategorySuggestion(BaseModel):
    name: str
    usage_count: int


class CategoriesResponse(BaseModel):
    categories: list[CategorySuggestion]


# ── Facts (Temporal Knowledge Graph) ──────────────────────────────────────────

class FactCreate(BaseModel):
    subject: str = Field(..., min_length=1, description="Sujet du fait (ex: 'scanner_iot')")
    predicate: str = Field(..., min_length=1, description="Prédicat (ex: 'utilise_hardware')")
    object: str = Field(..., min_length=1, description="Valeur chiffrée côté MCP")
    valid_from: Optional[str] = Field(None, description="Date de validité (YYYY-MM-DD), défaut: aujourd'hui")
    scope: Literal["private", "org"] = "private"
    org_id: Optional[str] = None
    user_id: Optional[str] = None


class Fact(FactCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str
    user_id: str
    valid_to: Optional[str] = None
    supersedes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True


class FactInvalidate(BaseModel):
    """Corps optionnel pour PUT /facts/{id}/invalidate"""
    valid_to: Optional[str] = Field(None, description="Date de fin (YYYY-MM-DD), défaut: aujourd'hui")
