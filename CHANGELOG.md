# Changelog

🇫🇷 [Français](#français) · 🇬🇧 [English](#english)

---

## Français

Toutes les modifications notables sont documentées ici.
Format : [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/) — [Semantic Versioning](https://semver.org/)

### [1.3.1] — 2026-05-16

#### Corrigé
- **Recall sémantique cassé** : `AsyncQdrantClient.search()` supprimé dans qdrant-client 1.17.x → migré vers `query_points()`
- **Fetch/Delete par ID partiel** : `get_memory` utilise `LIKE id || '%'` + `delete` résout l'UUID complet avant suppression
- **UUIDs complets** dans les réponses des tools `remember`, `recall`, `list_memories`, `remember_fact`

---

### [1.3.0] — 2026-05-14

#### Ajouté
- **Smithery Marketplace** — publié `pquattro-3b11/memoraeu`, score 100/100 (Capability Quality 40/40, Server Metadata 35/35, Configuration UX 25/25)
- **GitHub Copilot (VS Code 1.99+)** — transport HTTP Streamable, API key via `inputs` secret storage VS Code
- **n8n** — transport HTTP Streamable, node MCP Client Tool, 10 outils disponibles comme sous-outils de workflow
- Tools renommés en dot-notation (`memory.store`, `memory.recall`, `fact.list`…) — requis par Smithery Naming
- Doc landing mise à jour — tabs GitHub Copilot + n8n

#### Corrigé
- Fix body-replay `_replay_receive` : retourne le body une seule fois puis délègue à `request.receive()` — évitait une boucle infinie qui bloquait l'event loop asyncio (tous les endpoints gelaient)
- Patch `ServerSession._received_request` : auto-transition `Initializing→Initialized` pour les scanners qui envoient `tools/list` avant `initialized`

---

### [1.2.0] — 2026-05-13

#### Ajouté
- **Compatibilité Mistral connecteurs MCP (beta)** : endpoint `/.well-known/mcp/server-card/{path}` requis par Mistral lors de la découverte
- Connecteur enregistré et testé : discovery 10 tools ✅, auth `?token=` ✅, server-card ✅
- Doc : onglet Mistral dans la page MCP avec config Python SDK et note beta
- ⚠️ Exécution des tool calls en attente du déploiement complet côté Mistral

---

### [1.1.0] — 2026-05-12

#### Ajouté
- **Fusion intelligente de doublons** (`POST /memories/merge`) : reçoit deux contenus déchiffrés, appelle Mistral (Ollama en fallback) pour les fusionner en préservant tous les faits sans redondance
- **Dashboard — bouton "Fusionner"** : sur chaque paire, fusionne, re-chiffre et supprime les deux originales
- **Dashboard — bouton "Tout fusionner"** : traite toutes les paires séquentiellement avec skip des IDs déjà traités

---

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

### [1.3.1] — 2026-05-16

#### Fixed
- **Broken semantic recall**: `AsyncQdrantClient.search()` removed in qdrant-client 1.17.x → migrated to `query_points()`
- **Fetch/Delete by partial ID**: `get_memory` uses `LIKE id || '%'` + `delete` resolves full UUID before deletion
- **Full UUIDs** in `remember`, `recall`, `list_memories`, `remember_fact` tool responses

---

### [1.3.0] — 2026-05-14

#### Added
- **Smithery Marketplace** — published as `pquattro-3b11/memoraeu`, score 100/100 (Capability Quality 40/40, Server Metadata 35/35, Configuration UX 25/25)
- **GitHub Copilot (VS Code 1.99+)** — HTTP Streamable transport, API key via VS Code `inputs` secret storage
- **n8n** — HTTP Streamable transport, MCP Client Tool node, all 10 tools available as workflow sub-tools
- Tools renamed to dot-notation (`memory.store`, `memory.recall`, `fact.list`…) — required by Smithery Naming score
- Landing docs updated — GitHub Copilot + n8n tabs added

#### Fixed
- Body-replay `_replay_receive` fix: returns body once then delegates to `request.receive()` — was causing an infinite loop blocking the asyncio event loop (all endpoints frozen)
- `ServerSession._received_request` patch: auto-transition `Initializing→Initialized` for scanners that send `tools/list` before `initialized`

---

### [1.2.0] — 2026-05-13

#### Added
- **Mistral MCP connector compatibility (beta)**: `/.well-known/mcp/server-card/{path}` endpoint required by Mistral during connector discovery
- Connector registered and tested: 10-tool discovery ✅, `?token=` auth ✅, server-card ✅
- Docs: Mistral tab in MCP page with Python SDK config and beta note
- ⚠️ Tool call execution pending full rollout on Mistral's side

---

### [1.1.0] — 2026-05-12

#### Added
- **Intelligent duplicate merge** (`POST /memories/merge`): receives two decrypted contents, calls Mistral (Ollama fallback) to merge them while preserving all facts without redundancy
- **Dashboard — "Merge" button**: on each pair, merges, re-encrypts and deletes both originals
- **Dashboard — "Merge all" button**: processes all pairs sequentially, skipping already-processed IDs

---

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
