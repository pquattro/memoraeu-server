# MemoraEU Server

**Sovereign European MCP memory layer** — give any AI assistant persistent, searchable memory, fully under your control.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![MCP compatible](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io/)

---

## What it does

MemoraEU is a self-hostable memory server for AI assistants. It implements the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) so any MCP-compatible client (Claude, Cursor, Windsurf, ChatGPT…) can store and retrieve memories via semantic search.

- **Semantic search** powered by Qdrant + embeddings (Ollama or Mistral)
- **Multi-user / multi-org** with JWT auth
- **MCP transports**: Legacy SSE (Cursor, curl) + HTTP Streamable (claude.ai 2025)
- **Temporal facts** with validity periods
- **GDPR-friendly**: runs entirely in your infrastructure, no data leaves your server

---

## Quick Start (Docker Compose)

```bash
git clone https://github.com/pquattro/memoraeu-server.git
cd memoraeu-server
cp .env.example .env
# Edit .env — set JWT_SECRET (min 32 chars) and embedding provider

docker compose up -d
```

The API is available at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

---

## Configuration

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

---

## Connect your MCP client

Once running, configure your MCP client to point to the server:

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

---

## Self-host vs Cloud

| | Self-hosted | [MemoraEU Cloud](https://memoraeu.com) |
|---|---|---|
| Setup | Docker Compose | Sign up, done |
| Data location | Your server | EU (OVH, France) |
| Embedding | Ollama (local) or Mistral | Mistral |
| Updates | Manual | Automatic |
| Price | Free (AGPL) | Free tier + paid plans |

---

## Install as Python package

```bash
pip install memoraeu-core
```

With Mistral embeddings:
```bash
pip install "memoraeu-core[mistral]"
```

---

## Contributing

Pull requests are welcome. For major changes, open an issue first.

```bash
git clone https://github.com/pquattro/memoraeu-server.git
cd memoraeu-server
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # configure your local .env
uvicorn memoraeu.main:app --reload
```

Please keep PRs focused — one feature or fix per PR.

---

## License

[AGPL-3.0](LICENSE) — Copyright (C) 2024-2026 Philippe Quattrocchi

If you run a modified version as a network service, you must make the source available to your users.
