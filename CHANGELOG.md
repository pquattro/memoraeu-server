# Changelog

🇫🇷 [Français](#français) · 🇬🇧 [English](#english)

---

## Français

Toutes les modifications notables sont documentées ici.
Format : [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/) — [Semantic Versioning](https://semver.org/)

### [1.0.0] — 2026-05-12

#### Sécurité (revue complète)
- **JWT HttpOnly cookies** : le token d'accès ne transite plus par `localStorage` — stocké en cookie `HttpOnly; Secure; SameSite=Strict`
- **Refresh token** : access token réduit à 1 heure, refresh token 30 jours avec rotation à chaque usage (persisté en SQLite, invalidation serveur)
- **OAuth PKCE strict** : `code_challenge` S256 obligatoire, `redirect_uri` validée contre une allowlist (`claude.ai`, `app.memoraeu.com`, `localhost`)
- **OAuth codes SQLite** : les codes PKCE persistés en SQLite avec TTL et purge automatique (plus de dict Python in-process)
- **Billing URLs hardcodées** : `success_url` / `cancel_url` / `return_url` Stripe ne sont plus acceptés depuis le client
- **XSS GDPR log** : toutes les valeurs du journal HTML admin passent par `html.escape()`
- **Headers nginx** : `X-Content-Type-Options`, `X-Frame-Options SAMEORIGIN`, `Referrer-Policy strict-origin-when-cross-origin`
- **CSP** : Content Security Policy complète sur landing et dashboard (`script-src`, `style-src`, `connect-src`, `font-src`, `frame-src`, `object-src`)
- **Crisp** : `client.crisp.chat` ajouté à `style-src` et `font-src` dans les deux CSP
- **Autocomplete** : tous les champs `type="password"` ont `autoComplete="current-password"` ou `"new-password"` ; les champs email ont `autoComplete="username"`
- **Champ username caché** (formulaire Unlock) : `<input type="hidden" autocomplete="username">` pour les gestionnaires de mots de passe
- **Email dans TokenResponse** : retourné dans toutes les réponses d'authentification et stocké dans `memoraeu_user`

#### Ajouté
- `POST /auth/refresh` — rafraîchissement silencieux avec rotation du cookie
- `POST /auth/logout` — efface les cookies access + refresh, révoque le refresh token en DB
- Table `oauth_codes` (SQLite) — persistance des codes PKCE inter-redémarrages
- Table `refresh_tokens` (SQLite) — gestion des refresh tokens avec rotation
- Refresh automatique côté frontend : 401 → tentative `/auth/refresh` → retry transparent ; événement `memoraeu:session-expired` si refresh échoué

#### Modifié
- `jwt_expire_minutes` : 43200 → 60 (1 heure)
- `credentials: 'include'` sur tous les fetch, suppression du header `Authorization: Bearer` (géré par cookie)
- Session restore via `api.me()` (plus de lecture `localStorage` pour le token)
- `handleLogout` async avec révocation serveur

---

### [0.9.0] — 2026-05-12

#### Ajouté
- **RGPD complet** (`api/routers/gdpr.py`) :
  - `GET /gdpr/status` — statistiques données utilisateur
  - `GET /gdpr/export` — export JSON signé (Art. 20 RGPD)
  - `DELETE /gdpr/delete-account` — purge irréversible Qdrant + SQLite (Art. 17)
  - `GET /me/gdpr-history` — historique des opérations RGPD
  - `GET /gdpr/admin/log` — journal HTML filtrable (org, date), protégé `X-Admin-Key`
  - `GET /gdpr/admin/log-json` — même journal en JSON pour le dashboard React
- **Dashboard RGPD** : vue utilisateur (statut, export, suppression) + vue admin (journal avec recherche approximative)
- **Support in-app** : formulaire sidebar, ouvre le client email
- **Crisp chat** intégré sur landing et dashboard

---

### [0.8.0] — 2026-05-03

#### Ajouté
- **Support ChatGPT MCP connector** : CORS `chatgpt.com` / `chat.openai.com`, tool `search()` (alias de `recall`), tool `fetch(id)` pour Deep Research

---

### [0.7.0] — 2026-05-02

#### Ajouté
- **OAuth 2.0 Authorization Code + PKCE** : `/oauth/authorize`, `/oauth/token`, RFC 8414 + RFC 9728
- **HTTP Streamable MCP transport** (`POST /mcp/sse`) — spec MCP 2025-03-26
- **CORS étendu** : `claude.ai`, `cursor.sh`, `codeium.com`

---

### [0.6.0] — 2026-05-02

#### Ajouté
- **Transport SSE/HTTP Streamable MCP** : 8 outils MCP via `GET /mcp/sse` + `POST /mcp/messages`
- Authentification Bearer identique à l'API REST

---

### [0.5.0] — 2026-05-02

#### Ajouté
- **Temporal Knowledge Graph** : faits structurés `subject / predicate / object` avec validité temporelle, auto-invalidation, endpoints `/facts`
- `remember_fact`, `recall_facts`, `invalidate_fact` dans le MCP

---

### [0.4.0] — 2026-04-19

#### Ajouté
- **Déduplication zero-knowledge** : embedding local avant stockage, seuil 94 % (rejet) / 85 % (avertissement)
- `POST /memories/search-by-vector`, `GET /memories/duplicates`
- Section "Doublons" dans le dashboard

---

### [0.1.0] — 2026-04-18

#### Ajouté
- API REST FastAPI — CRUD mémoires
- Recherche sémantique Qdrant + embeddings Mistral
- Persistance SQLite (catégories, tags, timestamps)
- Serveur MCP stdio — 5 outils : `remember`, `recall`, `forget`, `list_memories`, `list_categories`
- Chiffrement zero-knowledge AES-256-GCM + PBKDF2-SHA256
- Docker Compose (Qdrant + API)

---

## English

All notable changes are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) — [Semantic Versioning](https://semver.org/)

### [1.0.0] — 2026-05-12

#### Security (full review)
- **JWT HttpOnly cookies**: access token no longer stored in `localStorage` — set as `HttpOnly; Secure; SameSite=Strict` cookie
- **Refresh token**: access token reduced to 1 hour, refresh token 30 days with rotation on each use (persisted in SQLite, server-side revocation)
- **Strict OAuth PKCE**: `code_challenge` S256 mandatory, `redirect_uri` validated against allowlist (`claude.ai`, `app.memoraeu.com`, `localhost`)
- **PKCE codes in SQLite**: no more in-process Python dict — persisted with TTL and automatic cleanup
- **Hardcoded billing URLs**: Stripe `success_url` / `cancel_url` / `return_url` no longer accepted from client
- **GDPR log XSS**: all values in the HTML admin log pass through `html.escape()`
- **nginx headers**: `X-Content-Type-Options`, `X-Frame-Options SAMEORIGIN`, `Referrer-Policy strict-origin-when-cross-origin`
- **CSP**: full Content Security Policy on landing and dashboard
- **Crisp**: `client.crisp.chat` added to `style-src` and `font-src` in both CSPs
- **Autocomplete**: all `type="password"` fields have `autoComplete="current-password"` or `"new-password"`; email fields have `autoComplete="username"`
- **Hidden username field** (Unlock form): for password manager compatibility
- **Email in TokenResponse**: returned in all auth responses and stored in `memoraeu_user`

#### Added
- `POST /auth/refresh` — silent refresh with cookie rotation
- `POST /auth/logout` — clears access + refresh cookies, revokes refresh token in DB
- Table `oauth_codes` (SQLite) — PKCE code persistence across restarts
- Table `refresh_tokens` (SQLite) — refresh token management with rotation
- Frontend auto-refresh: 401 → `/auth/refresh` attempt → transparent retry; `memoraeu:session-expired` event on failure

#### Changed
- `jwt_expire_minutes`: 43200 → 60 (1 hour)
- `credentials: 'include'` on all fetch calls, removed `Authorization: Bearer` header (managed by cookie)
- Session restore via `api.me()` (no more `localStorage` token read)
- `handleLogout` async with server-side revocation

---

### [0.9.0] — 2026-05-12

#### Added
- **Full GDPR** (`api/routers/gdpr.py`):
  - `GET /gdpr/status` — stored data statistics
  - `GET /gdpr/export` — signed JSON export (Art. 20 GDPR)
  - `DELETE /gdpr/delete-account` — irreversible purge Qdrant + SQLite (Art. 17)
  - `GET /me/gdpr-history` — GDPR operation history
  - `GET /gdpr/admin/log` — filterable HTML log (org, date), protected by `X-Admin-Key`
  - `GET /gdpr/admin/log-json` — same log as JSON for the React dashboard
- **GDPR dashboard**: user view (status, export, deletion) + admin view (log with fuzzy search)
- **In-app support**: sidebar form, opens email client
- **Crisp chat** integrated on landing and dashboard

---

### [0.8.0] — 2026-05-03

#### Added
- **ChatGPT MCP connector support**: CORS `chatgpt.com` / `chat.openai.com`, `search()` tool (alias of `recall`), `fetch(id)` tool for Deep Research

---

### [0.7.0] — 2026-05-02

#### Added
- **OAuth 2.0 Authorization Code + PKCE**: `/oauth/authorize`, `/oauth/token`, RFC 8414 + RFC 9728
- **HTTP Streamable MCP transport** (`POST /mcp/sse`) — MCP spec 2025-03-26
- **Extended CORS**: `claude.ai`, `cursor.sh`, `codeium.com`

---

### [0.6.0] — 2026-05-02

#### Added
- **SSE/HTTP Streamable MCP transport**: 8 MCP tools via `GET /mcp/sse` + `POST /mcp/messages`
- Bearer authentication identical to the REST API

---

### [0.5.0] — 2026-05-02

#### Added
- **Temporal Knowledge Graph**: structured facts `subject / predicate / object` with temporal validity, auto-invalidation, `/facts` endpoints
- `remember_fact`, `recall_facts`, `invalidate_fact` in the MCP

---

### [0.4.0] — 2026-04-19

#### Added
- **Zero-knowledge deduplication**: local embedding before storage, 94% threshold (reject) / 85% (warning)
- `POST /memories/search-by-vector`, `GET /memories/duplicates`
- "Duplicates" section in dashboard

---

### [0.1.0] — 2026-04-18

#### Added
- FastAPI REST API — memory CRUD
- Semantic search with Qdrant + Mistral embeddings
- SQLite persistence (categories, tags, timestamps)
- MCP stdio server — 5 tools: `remember`, `recall`, `forget`, `list_memories`, `list_categories`
- Zero-knowledge AES-256-GCM + PBKDF2-SHA256 encryption
- Docker Compose (Qdrant + API)
