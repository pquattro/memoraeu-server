# Changelog

All notable changes to **MemoraEU Server** are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) — [Semantic Versioning](https://semver.org/)

---

## [1.0.0] - 2026-05-12

### Security
- JWT access token reduced from 30 days to 1 hour + 30-day refresh token with rotation (stored in SQLite)
- JWT stored in `HttpOnly; Secure; SameSite=Strict` cookie — no longer exposed to JavaScript
- `POST /auth/refresh` — silent token rotation endpoint
- `POST /auth/logout` — server-side cookie + refresh token revocation
- OAuth PKCE codes persisted in SQLite (no longer in-process dict — survives restarts)
- OAuth `redirect_uri` validated against an allowlist (`claude.ai`, `app.memoraeu.com`, `localhost`)
- Billing `success_url` / `cancel_url` hardcoded server-side (not client-controlled)
- GDPR admin HTML log: all values escaped via `html.escape()` (XSS prevention)
- nginx: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` headers added globally
- Full Content Security Policy on landing and dashboard vhosts
- `api/dependencies.py`: `get_current_user` accepts `memoraeu_token` cookie in addition to Bearer header

### Added
- `oauth_codes` table (SQLite) — PKCE code persistence across restarts
- `refresh_tokens` table (SQLite) — refresh token lifecycle with rotation
- `email` field in `TokenResponse` — returned on all auth endpoints

### Changed
- `jwt_expire_minutes`: 43200 → 60 (1 hour)
- `refresh_token_expire_days`: 30 (new setting)

---

## [0.9.0] - 2026-05-12

### Added
- **Full GDPR compliance** (Articles 15, 17, 20):
  - `GET /gdpr/status` — data statistics per user
  - `GET /gdpr/export` — full JSON export (`memoraeu-export.json`)
  - `DELETE /gdpr/delete-account` — irreversible purge (Qdrant + SQLite)
  - `GET /me/gdpr-history` — user GDPR operation history
  - `GET /gdpr/admin/log` — filterable HTML admin log (protected by `X-Admin-Key`)
  - `GET /gdpr/admin/log-json` — same log as JSON for the dashboard
- Crisp live chat integrated on landing and dashboard
- Open Source section on landing with self-host vs cloud comparison
- Documentation link in dashboard sidebar

---

## [0.8.0] - 2026-05-03

### Added
- ChatGPT MCP connector support (CORS: `chatgpt.com`, `chat.openai.com`)
- OAuth 2.0 Authorization Code + PKCE flow (`/oauth/authorize`, `/oauth/token`)
- RFC 8414 / RFC 9728 discovery endpoints
- MFA (TOTP) — setup, enable, disable, verify
- Billing: Stripe Checkout, Customer Portal, webhook handler
- Invite system: `POST /org/invite`, `GET /auth/invite-info`, `POST /auth/accept-invite`
- Usage tracking: `GET /usage`, `GET /usage/history`
- Admin panel: orgs, users, plans, subscriptions management

---

## [0.7.0] - 2026-04-28

### Added
- Zero-knowledge encryption C2: client-side key derivation via PBKDF2-HMAC-SHA256 (210k iterations)
- `kdf_salt` per organization, `enc_migrated` migration flag
- Vault re-encryption endpoint `POST /auth/reencrypt-vault`
- Temporal Knowledge Graph: `facts` table, `remember_fact`, `recall_facts`, `invalidate_fact` (MCP tools)
- Multi-tenant architecture: organizations, members, roles (owner / admin / member)

---

## [0.6.0] - 2026-04-19

### Added
- Initial open-source release (AGPL v3)
- FastAPI backend, SQLite + Qdrant vector store
- MCP SSE transport (`/mcp/sse`) + HTTP Streamable
- `remember`, `recall`, `forget`, `list_memories`, `list_categories` MCP tools
- React/Vite dashboard (`app.memoraeu.com`)
- React/Vite landing (`memoraeu.com`)
- Docker Compose deployment
