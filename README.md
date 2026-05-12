# MemoraEU Server

[![PyPI memoraeu-mcp](https://img.shields.io/pypi/v/memoraeu-mcp?label=memoraeu-mcp&color=1D9E75)](https://pypi.org/project/memoraeu-mcp/)
[![PyPI memoraeu](https://img.shields.io/pypi/v/memoraeu?label=sdk&color=1D9E75)](https://pypi.org/project/memoraeu/)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![MCP compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io/)
[![Hosted in EU](https://img.shields.io/badge/hosted-EU%20🇪🇺-003399.svg)](https://memoraeu.com)

---

🇫🇷 [Français](#français) · 🇬🇧 [English](#english)

---

## Français

> **MemoraEU** donne à votre IA une mémoire persistante et chiffrée —
> souveraine, zero-knowledge, hébergée en Europe.
> Compatible Claude, Cursor, Windsurf, ChatGPT via MCP.
> Auto-hébergement gratuit (AGPL v3) ou [cloud géré EU](https://memoraeu.com).

### Ce que ça fait

MemoraEU est un serveur de mémoire auto-hébergeable pour les assistants IA. Il implémente le [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) pour que n'importe quel client MCP (Claude, Cursor, Windsurf, ChatGPT…) puisse stocker et retrouver des souvenirs via recherche sémantique.

- **Recherche sémantique** propulsée par Qdrant + embeddings (Ollama ou Mistral)
- **Multi-utilisateur / multi-org** avec auth JWT
- **Transports MCP** : Legacy SSE (Cursor, curl) + HTTP Streamable (claude.ai 2025)
- **Faits temporels** avec périodes de validité
- **Chiffrement zero-knowledge** AES-256-GCM côté client (memoraeu-mcp)
- **RGPD natif** : endpoints export / suppression / historique intégrés
- **Fusion intelligente** : détection et merge de mémoires similaires via LLM (Mistral/Ollama)

### Démarrage rapide

#### ☁️ Option A — Cloud géré (zéro config)

```bash
# Installer le client MCP
uvx memoraeu-mcp

# Ajouter dans votre config Claude Desktop :
# Server URL : https://api.memoraeu.com/mcp/sse
# Clé API sur : https://app.memoraeu.com
```

#### 🏠 Option B — Auto-hébergement (gratuit, AGPL v3)

```bash
git clone https://github.com/pquattro/memoraeu-server
cd memoraeu-server
cp .env.example .env   # remplir MEMORAEU_SECRET, MEMORAEU_SALT, MISTRAL_API_KEY
docker compose up -d
# API disponible sur http://localhost:8000
# Docs : http://localhost:8000/docs
# Serveur MCP : http://localhost:8000/mcp/sse
```

### Configuration

Toute la configuration se fait via variables d'environnement (voir `.env.example`) :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `JWT_SECRET` | — | **Requis.** 32 caractères minimum. |
| `REGISTRATION_OPEN` | `true` | Autoriser les nouvelles inscriptions |
| `EMBED_PROVIDER` | `ollama` | `ollama` ou `mistral` |
| `EMBED_MODEL` | `nomic-embed-text` | Nom du modèle d'embedding |
| `EMBED_URL` | `http://localhost:11434` | URL de base Ollama |
| `MISTRAL_API_KEY` | — | Requis si `EMBED_PROVIDER=mistral` |
| `QDRANT_URL` | `http://qdrant:6333` | URL de l'instance Qdrant |
| `SQLITE_PATH` | `/data/memoraeu.db` | Chemin de la base SQLite |

### Connecter votre client MCP

**Claude Desktop / Cursor / Windsurf** (Legacy SSE) :
```json
{
  "mcpServers": {
    "memoraeu": {
      "url": "http://localhost:8000/mcp/sse",
      "headers": { "Authorization": "Bearer VOTRE_CLE_API" }
    }
  }
}
```

**claude.ai** (HTTP Streamable, nécessite une URL publique + OAuth) :
Voir la [documentation](https://memoraeu.com/docs/mcp).

### Pourquoi MemoraEU ?

| | MemoraEU | Autres (ex: mem0) |
|---|---|---|
| Open source | ✅ AGPL v3 | ✅ (core) |
| Hébergé en EU | ✅ OVH France | ❌ US |
| Zero-knowledge | ✅ AES-256-GCM côté client | ❌ |
| Auto-hébergeable | ✅ Docker Compose | ✅ |
| MCP natif | ✅ stdio + SSE + HTTP Streamable | ❌ |
| OAuth 2.0 PKCE | ✅ | ❌ |
| Graphe de connaissance temporel | ✅ | ❌ |
| Endpoints RGPD | ✅ natifs | ⚠️ partiel |

### Self-host vs Cloud

| | Auto-hébergé | [MemoraEU Cloud](https://memoraeu.com) |
|---|---|---|
| Installation | Docker Compose | Inscription, c'est tout |
| Localisation des données | Votre serveur | EU (OVH, France) |
| Embeddings | Ollama (local) ou Mistral | Mistral |
| Mises à jour | Manuelles | Automatiques |
| Prix | Gratuit (AGPL) | Tier gratuit + plans payants |

### Architecture

```
Claude Desktop / Claude Code                 claude.ai · Cursor · Windsurf · ChatGPT
         │                                              │
         │ stdio (MCP)  memoraeu-mcp (uvx)             │ HTTP Streamable / SSE
         ▼                                              │ OAuth 2.0 PKCE
  memoraeu_mcp/main.py                                 │
         │                                              ▼
         ├── Mistral API  ←── embeddings locaux   api/main.py  (FastAPI)
         │                    (avant chiffrement)       │
         │ HTTP + Bearer token                          ├── POST /mcp/sse   ← HTTP Streamable
         │ [contenu chiffré AES-256-GCM + vecteur]     ├── GET  /mcp/sse   ← SSE legacy
         ▼                                              ├── /oauth/*        ← PKCE
   api/main.py  (FastAPI)
         ├── Qdrant          ← recherche vectorielle
         ├── SQLite (memories)
         └── SQLite (facts)  ← graphe de connaissance temporel
```

**Stack :**
- [FastAPI](https://fastapi.tiangolo.com/) — API REST async
- [Qdrant](https://qdrant.tech/) — base vectorielle (Docker)
- [Mistral AI](https://mistral.ai/) — embeddings côté client MCP
- [MCP](https://modelcontextprotocol.io/) — protocole Claude Desktop / Claude Code
- SQLite — persistance des métadonnées
- AES-256-GCM + PBKDF2-SHA256 (210k itérations) — chiffrement zero-knowledge

### Flux zero-knowledge

| Variable | Rôle |
|---|---|
| `MEMORAEU_API_KEY` | Authentification HTTP — Bearer token envoyé à chaque requête |
| `MEMORAEU_SECRET` | Mot de passe — entrée PBKDF2 pour dériver la clé AES localement |
| `MEMORAEU_SALT` | Salt KDF unique par compte, généré à l'inscription |
| `MISTRAL_API_KEY` | Clé Mistral côté client — embeddings calculés avant chiffrement |

```
remember() :
  texte clair
    → PBKDF2(SECRET, SALT, 210k) = clé AES locale
    → Mistral embed(texte clair) = vecteur  ← sur la machine de l'utilisateur
    → AES-256-GCM(texte, clé) = blob chiffré
    → POST /memories { blob chiffré, vecteur }  ← le serveur ne voit que l'opaque
```

### Installer en package Python

```bash
pip install memoraeu
```

Avec les embeddings Mistral :
```bash
pip install "memoraeu[mistral]"
```

### Conformité RGPD

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/gdpr/status` | `GET` | Statistiques des données stockées |
| `/gdpr/export` | `GET` | Export JSON complet (Art. 20) |
| `/gdpr/delete-account` | `DELETE` | Purge irréversible Qdrant + SQLite (Art. 17) |
| `/me/gdpr-history` | `GET` | Historique des opérations RGPD |

Journal admin filtrable par organisation et date :
```
GET /gdpr/admin/log?org_id=...&date_from=YYYY-MM-DD
X-Admin-Key: <MEMORAEU_ADMIN_KEY>
```

### Contribuer

MemoraEU est open source (AGPL v3). Les contributions sont les bienvenues.

```bash
git clone https://github.com/pquattro/memoraeu-server
cd memoraeu-server
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # configurer votre .env local
uvicorn api.main:app --reload
```

Gardez les PRs ciblées — une fonctionnalité ou un correctif par PR.

- 🐛 [Ouvrir une issue](https://github.com/pquattro/memoraeu-server/issues)
- 💬 [Démarrer une discussion](https://github.com/pquattro/memoraeu-server/discussions)
- 📖 [Docs API](https://api.memoraeu.com/docs)
- ☁️ [Essayer le cloud](https://app.memoraeu.com)

Domaines où l'aide est la plus utile : SDK JavaScript/TypeScript, app mobile, intégrations MCP supplémentaires, traductions.

### Licence

[AGPL v3](LICENSE) — Copyright (c) 2026 Philippe Quattrocchi

Si vous faites tourner une version modifiée en tant que service réseau, vous devez rendre le code source disponible à vos utilisateurs.

---

## English

> **MemoraEU** gives your AI a persistent, encrypted memory —
> sovereign, zero-knowledge, hosted in Europe.
> Works with Claude, Cursor, Windsurf, ChatGPT via MCP.
> Self-host for free (AGPL v3) or use the [managed EU cloud](https://memoraeu.com).

### What it does

MemoraEU is a self-hostable memory server for AI assistants. It implements the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) so any MCP-compatible client (Claude, Cursor, Windsurf, ChatGPT…) can store and retrieve memories via semantic search.

- **Semantic search** powered by Qdrant + embeddings (Ollama or Mistral)
- **Multi-user / multi-org** with JWT auth
- **MCP transports**: Legacy SSE (Cursor, curl) + HTTP Streamable (claude.ai 2025)
- **Temporal facts** with validity periods
- **Zero-knowledge encryption** AES-256-GCM client-side (memoraeu-mcp)
- **Native GDPR**: built-in export / deletion / history endpoints
- **Intelligent merge**: similar memory detection and LLM-powered merge (Mistral/Ollama)

### Quick start

#### ☁️ Option A — Managed cloud (zero config)

```bash
# Install the MCP client
uvx memoraeu-mcp

# Add to your Claude Desktop config:
# Server URL: https://api.memoraeu.com/mcp/sse
# Get your API key at: https://app.memoraeu.com
```

#### 🏠 Option B — Self-host (free, AGPL v3)

```bash
git clone https://github.com/pquattro/memoraeu-server
cd memoraeu-server
cp .env.example .env   # fill MEMORAEU_SECRET, MEMORAEU_SALT, MISTRAL_API_KEY
docker compose up -d
# API running at http://localhost:8000
# Docs: http://localhost:8000/docs
# MCP server: http://localhost:8000/mcp/sse
```

### Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET` | — | **Required.** Min 32 chars. |
| `REGISTRATION_OPEN` | `true` | Allow new user registration |
| `EMBED_PROVIDER` | `ollama` | `ollama` or `mistral` |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model name |
| `EMBED_URL` | `http://localhost:11434` | Ollama base URL |
| `MISTRAL_API_KEY` | — | Required if `EMBED_PROVIDER=mistral` |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant instance URL |
| `SQLITE_PATH` | `/data/memoraeu.db` | SQLite database path |

### Connect your MCP client

**Claude Desktop / Cursor / Windsurf** (Legacy SSE):
```json
{
  "mcpServers": {
    "memoraeu": {
      "url": "http://localhost:8000/mcp/sse",
      "headers": { "Authorization": "Bearer YOUR_API_KEY" }
    }
  }
}
```

**claude.ai** (HTTP Streamable, requires public URL + OAuth):
See [documentation](https://memoraeu.com/docs/mcp).

### Why MemoraEU?

| | MemoraEU | Others (e.g. mem0) |
|---|---|---|
| Open source | ✅ AGPL v3 | ✅ (core) |
| Hosted in EU | ✅ OVH France | ❌ US |
| Zero-knowledge | ✅ AES-256-GCM client-side | ❌ |
| Self-hostable | ✅ Docker Compose | ✅ |
| MCP native | ✅ stdio + SSE + HTTP Streamable | ❌ |
| OAuth 2.0 PKCE | ✅ | ❌ |
| Temporal knowledge graph | ✅ | ❌ |
| GDPR endpoints | ✅ native | ⚠️ partial |

### Self-host vs Cloud

| | Self-hosted | [MemoraEU Cloud](https://memoraeu.com) |
|---|---|---|
| Setup | Docker Compose | Sign up, done |
| Data location | Your server | EU (OVH, France) |
| Embeddings | Ollama (local) or Mistral | Mistral |
| Updates | Manual | Automatic |
| Price | Free (AGPL) | Free tier + paid plans |

### Architecture

```
Claude Desktop / Claude Code                 claude.ai · Cursor · Windsurf · ChatGPT
         │                                              │
         │ stdio (MCP)  memoraeu-mcp (uvx)             │ HTTP Streamable / SSE
         ▼                                              │ OAuth 2.0 PKCE
  memoraeu_mcp/main.py                                 │
         │                                              ▼
         ├── Mistral API  ←── local embeddings    api/main.py  (FastAPI)
         │                    (before encryption)       │
         │ HTTP + Bearer token                          ├── POST /mcp/sse   ← HTTP Streamable
         │ [AES-256-GCM ciphertext + vector]           ├── GET  /mcp/sse   ← SSE legacy
         ▼                                              ├── /oauth/*        ← PKCE
   api/main.py  (FastAPI)
         ├── Qdrant          ← vector search
         ├── SQLite (memories)
         └── SQLite (facts)  ← temporal knowledge graph
```

**Stack:**
- [FastAPI](https://fastapi.tiangolo.com/) — async REST API
- [Qdrant](https://qdrant.tech/) — vector database (Docker)
- [Mistral AI](https://mistral.ai/) — client-side embeddings
- [MCP](https://modelcontextprotocol.io/) — Claude Desktop / Claude Code protocol
- SQLite — metadata persistence
- AES-256-GCM + PBKDF2-SHA256 (210k iterations) — zero-knowledge encryption

### Zero-knowledge flow

| Variable | Role |
|---|---|
| `MEMORAEU_API_KEY` | HTTP authentication — Bearer token sent with every request |
| `MEMORAEU_SECRET` | Password — PBKDF2 input to derive AES key locally |
| `MEMORAEU_SALT` | Per-account KDF salt, generated at registration |
| `MISTRAL_API_KEY` | Client-side Mistral key — embeddings computed before encryption |

```
remember() :
  plaintext
    → PBKDF2(SECRET, SALT, 210k) = local AES key
    → Mistral embed(plaintext) = vector  ← on the user's machine
    → AES-256-GCM(plaintext, key) = ciphertext
    → POST /memories { ciphertext, vector }  ← server only sees opaque blobs
```

### Install as Python package

```bash
pip install memoraeu
```

With Mistral embeddings:
```bash
pip install "memoraeu[mistral]"
```

### GDPR compliance

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/gdpr/status` | `GET` | Stored data statistics |
| `/gdpr/export` | `GET` | Full JSON export (Art. 20) |
| `/gdpr/delete-account` | `DELETE` | Irreversible purge Qdrant + SQLite (Art. 17) |
| `/me/gdpr-history` | `GET` | GDPR operation history |

Filterable admin log by organization and date:
```
GET /gdpr/admin/log?org_id=...&date_from=YYYY-MM-DD
X-Admin-Key: <MEMORAEU_ADMIN_KEY>
```

### Contributing

MemoraEU is open source (AGPL v3). Contributions welcome.

```bash
git clone https://github.com/pquattro/memoraeu-server
cd memoraeu-server
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # configure your local .env
uvicorn api.main:app --reload
```

Please keep PRs focused — one feature or fix per PR.

- 🐛 [Open an issue](https://github.com/pquattro/memoraeu-server/issues)
- 💬 [Start a discussion](https://github.com/pquattro/memoraeu-server/discussions)
- 📖 [Read the API docs](https://api.memoraeu.com/docs)
- ☁️ [Try the managed cloud](https://app.memoraeu.com)

Areas where help is most welcome: JavaScript/TypeScript SDK, mobile app, additional MCP client integrations, translations.

### License

[AGPL-3.0](LICENSE) — Copyright (C) 2026 Philippe Quattrocchi

If you run a modified version as a network service, you must make the source available to your users.
