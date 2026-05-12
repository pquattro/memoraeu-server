# MemoraEU

[![PyPI memoraeu-mcp](https://img.shields.io/pypi/v/memoraeu-mcp?label=memoraeu-mcp&color=1D9E75)](https://pypi.org/project/memoraeu-mcp/)
[![PyPI memoraeu](https://img.shields.io/pypi/v/memoraeu?label=sdk&color=1D9E75)](https://pypi.org/project/memoraeu/)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![MCP compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io/)
[![Hosted in EU](https://img.shields.io/badge/hosted-EU%20🇪🇺-003399.svg)](https://memoraeu.com)

> **MemoraEU** gives your AI a persistent, encrypted memory —
> sovereign, zero-knowledge, hosted in Europe.
> Works with Claude, Cursor, Windsurf, ChatGPT via MCP.
> Self-host for free (AGPL v3) or use the [managed EU cloud](https://memoraeu.com).

---

## Quick start

### ☁️ Option A — Managed cloud (zero config)

```bash
# Install the MCP client
uvx memoraeu-mcp

# Add to your Claude Desktop config:
# Server URL: https://api.memoraeu.com/mcp/sse
# Get your API key at: https://app.memoraeu.com
```

### 🏠 Option B — Self-host (free, AGPL v3)

```bash
git clone https://github.com/pquattro/memoraEu
cd memoraEu
cp .env.example .env   # fill MEMORAEU_SECRET, MEMORAEU_SALT, MISTRAL_API_KEY
docker compose up -d
# API running at http://localhost:8000
# MCP server: http://localhost:8000/mcp/sse
```

---

## Why MemoraEU?

| | MemoraEU | 0thers (like mem0:)|
|---|---|---|
| Open source | ✅ AGPL v3 | ✅ (core) |
| Hosted in EU | ✅ OVH France | ❌ US |
| Zero-knowledge | ✅ AES-256-GCM côté client | ❌ |
| Self-hostable | ✅ Docker Compose | ✅ |
| MCP native | ✅ stdio + SSE + HTTP Streamable | ❌ |
| OAuth 2.0 PKCE | ✅ | ❌ |
| Temporal knowledge graph | ✅ | ❌ |
| GDPR endpoints | ✅ natifs | ⚠️ partiel |

---

## Architecture

```
Claude Desktop / Claude Code                 claude.ai · Cursor · Windsurf · ChatGPT
         │                                              │
         │ stdio (MCP)  memoraeu-mcp (uvx)             │ HTTP Streamable / SSE
         ▼                                              │ OAuth 2.0 PKCE
  memoraeu_mcp/main.py                                 │
         │                                              ▼
         ├── Mistral API  ←── embeddings locaux   api/main.py  (FastAPI)
         │                    (avant chiffrement)       │
         │ HTTP + Bearer token                          ├── POST /mcp/sse   ← HTTP Streamable (2025)
         │ [contenu chiffré AES-256-GCM + vecteur]     ├── GET  /mcp/sse   ← Legacy SSE
         ▼                                              ├── /oauth/*        ← Authorization Code + PKCE
   api/main.py  (FastAPI)                              │
         │                                              ├── Qdrant          ← recherche vectorielle
         ├── Qdrant          ← recherche vectorielle   ├── SQLite (memories)
         ├── SQLite (memories)                         └── SQLite (facts)   ← knowledge graph
        └── SQLite (facts)     ← temporal knowledge graph
```

**Stack :**
- [FastAPI](https://fastapi.tiangolo.com/) — API REST async
- [Qdrant](https://qdrant.tech/) — base vectorielle (Docker)
- [Mistral AI](https://mistral.ai/) — embeddings (côté client MCP) + LLM admin
- [MCP](https://modelcontextprotocol.io/) — protocole Claude Desktop / Claude Code
- SQLite — persistance des métadonnées
- AES-256-GCM + PBKDF2-SHA256 (210k itérations) — chiffrement zero-knowledge côté client

---

## Flux zero-knowledge

Les trois variables de configuration du MCP ont des rôles distincts :

| Variable | Rôle |
|---|---|
| `MEMORAEU_API_KEY` | Authentification HTTP — Bearer token envoyé à chaque requête API |
| `MEMORAEU_SECRET` | Mot de passe de l'utilisateur — entrée PBKDF2 pour dériver la clé de chiffrement **localement** |
| `MEMORAEU_SALT` | Salt KDF unique par compte, généré par le serveur à l'inscription — jamais la clé elle-même |
| `MISTRAL_API_KEY` | Clé Mistral **côté client** — les embeddings sont calculés sur la machine de l'utilisateur avant chiffrement |

```
Flux remember() :
  texte clair
    → PBKDF2(SECRET, SALT, 210k) = clé AES locale
    → Mistral embed(texte clair) = vecteur           ← sur la machine de l'utilisateur
    → AES-256-GCM(texte clair, clé) = blob chiffré
    → POST /memories { blob chiffré, vecteur }        ← serveur ne voit que l'opaque
```

---

## Structure du projet

```
memoraeu/
├── docker-compose.yml          ← Qdrant + API + nginx (prod)
├── deploy.sh                   ← Script de déploiement VPS
├── .env.example                ← Template de configuration
│
├── api/
│   ├── main.py                 ← FastAPI entry point + lifespan + middlewares
│   ├── config.py               ← Settings (pydantic-settings)
│   ├── models.py               ← Schémas Pydantic
│   ├── dependencies.py         ← Auth middleware (JWT + API Key)
│   ├── routers/
│   │   ├── memories.py         ← CRUD mémoires + recherche sémantique
│   │   ├── facts.py            ← Temporal knowledge graph (subject/predicate/object)
│   │   ├── mcp_sse.py          ← MCP remote : GET SSE (legacy) + POST HTTP Streamable (2025)
│   │   ├── oauth.py            ← OAuth 2.0 Authorization Code + PKCE + client_credentials
│   │   ├── auth.py             ← Register, login, JWT, reset password, MFA
│   │   ├── api_keys.py         ← Gestion des clés API (meu-sk-…)
│   │   ├── users.py            ← Profil utilisateur
│   │   ├── org.py              ← Organisation, invitations membres
│   │   ├── billing.py          ← Abonnements Stripe
│   │   └── admin.py            ← Routes admin (plans, stats)
│   └── services/
│       ├── embedding.py        ← Client Mistral embed (fallback serveur)
│       ├── vector_store.py     ← Qdrant (isolation par org/user)
│       ├── metadata_store.py   ← SQLite (users, orgs, api_keys, categories…)
│       ├── memory_service.py   ← Orchestration CRUD
│       └── auth_service.py     ← JWT, hash password, MFA TOTP
│
├── dashboard/                  ← React/Vite (app.memoraeu.com)
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.jsx   ← Vue principale (mémoires + paramètres)
│       │   ├── Login.jsx       ← Connexion / inscription
│       │   ├── Unlock.jsx      ← Déverrouillage coffre (dérivation clé)
│       │   └── …
│       ├── crypto.js           ← AES-256-GCM + PBKDF2 (Web Crypto API)
│       └── CryptoContext.jsx   ← Contexte React pour la clé de session
│
├── landing/                    ← Site vitrine (memoraeu.com)
│
└── mcp/                        ← Package PyPI memoraeu-mcp
    └── memoraeu_mcp/
        ├── main.py             ← Serveur MCP stdio (8 outils)
        └── crypto.py           ← AES-256-GCM + PBKDF2 (Python)
│
├── sdk/                        ← Package PyPI memoraeu (Python SDK)
│   └── memoraeu/
│       ├── client.py           ← MemoraEU + AsyncMemoraEU (memories + facts)
│       └── models.py           ← Memory, Fact, SearchResult, Category
│
└── tests/                      ← Tests pytest-asyncio
    ├── conftest.py             ← Fixtures (env vars, store SQLite temporaire)
    ├── test_facts.py           ← 11 tests temporal knowledge graph
    └── test_mcp_sse.py         ← 5 tests transport SSE/HTTP Streamable
```

---

## Déploiement VPS

```bash
# Déploiement complet
bash deploy.sh ubuntu@memoraeu.com

# SSH
ssh -p 22 -i ~/.ssh/id_id ubuntu@yourip
```

| Composant | URL |
|---|---|
| Landing | https://memoraeu.com |
| Dashboard | https://app.memoraeu.com |
| API | https://api.memoraeu.com |
| Swagger | https://api.memoraeu.com/docs |

---

## Domaines et infra

- **VPS** : OVH (EU), Ubuntu, Docker Compose
- **Reverse proxy** : nginx
- **Backup** : Dropbox automatique toutes les nuits (`/opt/memoraeu/backup.sh`, rétention 31 jours)
- **TLS** : Let's Encrypt

---

## Roadmap

### Phase 1 — MVP local ✅
- [x] API REST FastAPI avec CRUD complet
- [x] Recherche sémantique via Qdrant + embeddings Mistral
- [x] Persistance des métadonnées en SQLite (catégories, tags)
- [x] Serveur MCP pour Claude Desktop (5 outils)

### Phase 2 — Sécurité & multi-utilisateurs ✅
- [x] Chiffrement zero-knowledge AES-256-GCM (clé côté client)
- [x] Authentification JWT multi-utilisateurs + MFA TOTP
- [x] Dashboard web (React/Vite)
- [x] Clés API `meu-sk-…` avec hash SHA-256
- [x] Auto-suggestion de catégories via Mistral (local, avant chiffrement)
- [x] Compression des mémoires longues (local, avant chiffrement)

### Phase 3 — Déploiement ✅
- [x] VPS européen + HTTPS + nginx
- [x] Package PyPI `memoraeu-mcp` (uvx)
- [x] Backup automatique Dropbox

### Phase 4 — Qualité mémoire ✅
- [x] Déduplication zero-knowledge (embedding local + `/search-by-vector`)
- [x] Détection de doublons dans le dashboard
- [x] Préfixe `ENCv1:` + PBKDF2 210k itérations (OWASP 2024)
- [x] Organisations + invitations membres
- [x] Plans admin en base de données (tarifs HT)

### Phase 5 — Temporal Knowledge Graph ✅
- [x] Table `facts` — faits structurés (subject/predicate/object) avec validité temporelle
- [x] Auto-invalidation + chaînage `supersedes` à la création
- [x] Endpoints `/facts` complets (CRUD + contradictions + historique)
- [x] MCP `memoraeu-mcp` 0.1.6 — `remember_fact`, `recall_facts`, `invalidate_fact`
- [x] SDK Python `memoraeu` 0.1.2 — sync + async
- [x] 11 tests pytest-asyncio

### Phase 6 — MCP Remote (claude.ai · Cursor · Windsurf · ChatGPT) ✅
- [x] Transport SSE legacy `GET /mcp/sse` + `POST /mcp/messages`
- [x] Transport HTTP Streamable `POST /mcp/sse` (spec MCP 2025-03-26)
- [x] OAuth 2.0 Authorization Code + PKCE — page de login, échange de code, PKCE S256
- [x] OAuth client_credentials — Cursor/Windsurf sans page de login
- [x] RFC 8414 `/.well-known/oauth-authorization-server` + RFC 9728 `/.well-known/oauth-protected-resource`
- [x] MCP package `memoraeu-mcp` 0.1.7 + SDK Python `memoraeu` 0.1.3
- [x] Doc publique refonte complète avec infographie + tabs par client
- [x] ChatGPT connector (Advanced Developer Mode) — tools `search` + `fetch` pour Deep Research mode


---

## Conformité RGPD

MemoraEU expose trois endpoints permettant à chaque utilisateur d'exercer ses droits RGPD directement depuis l'API.

### Endpoints utilisateur (Bearer token requis)

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/gdpr/status` | `GET` | Statistiques des données stockées (nombre de mémoires, de faits, taille estimée, dates) |
| `/gdpr/export` | `GET` | Export complet au format JSON — retourné en pièce jointe `memoraeu-export.json` (Art. 20) |
| `/gdpr/delete-account` | `DELETE` | Purge irréversible de toutes les mémoires (Qdrant + SQLite) et de tous les faits (Art. 17) |
| `/me/gdpr-history` | `GET` | Historique des opérations RGPD passées (exports, suppressions) |

> **Note chiffrement** : le champ `content` dans l'export est le ciphertext AES-256-GCM. Le déchiffrement s'effectue côté client via la clé dérivée de votre mot de passe (PBKDF2-SHA256). Le serveur ne voit jamais le contenu en clair.

### Journal admin

Un journal `gdpr_log` trace toutes les opérations (export / suppression) sans stocker de données personnelles. Il est consultable via :

```
GET /gdpr/admin/log?org_id=...&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
X-Admin-Key: <MEMORAEU_ADMIN_KEY>
```

L'interface retourne une page HTML filtrable par organisation et par date.

Le journal est également accessible en JSON (`GET /gdpr/admin/log-json`) pour intégration dans le dashboard React.

### Dashboard RGPD (backoffice)

Le dashboard app.memoraeu.com intègre une vue RGPD accessible via la sidebar :
- **Utilisateurs** : consulter son statut (mémoires, faits, taille), exporter ses données, supprimer son compte
- **Admins** : journal complet des opérations avec recherche par organisation (approximative) et filtre par date

---

## Support

Un formulaire de contact est disponible sur [memoraeu.com/contact](https://memoraeu.com/contact?subject=support). Les utilisateurs connectés disposent d'un formulaire intégré dans le dashboard (sidebar → Support), avec motif et message, qui prépare un email pré-rempli.

---

## Contributing

MemoraEU is open source (AGPL v3). Contributions welcome.

- 🐛 [Open an issue](https://github.com/pquattro/memoraEu/issues)
- 💬 [Start a discussion](https://github.com/pquattro/memoraEu/discussions)
- 📖 [Read the API docs](https://api.memoraeu.com/docs)
- ☁️ [Try the managed cloud](https://app.memoraeu.com)

Areas where help is most welcome:
- JavaScript/TypeScript SDK
- Mobile app (React Native)
- Additional MCP client integrations
- Translations

---

## Licence

[AGPL v3](LICENSE) — Copyright (c) 2026 Philippe Quattrocchi
