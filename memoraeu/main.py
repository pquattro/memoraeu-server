from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from api.routers import memories, users, auth, api_keys, usage, admin, billing, org
from api.routers import facts
from api.routers import mcp_sse
from api.routers import oauth
from api.services.metadata_store import get_metadata_store
from api.services.vector_store import get_vector_store
from api.config import get_settings

settings = get_settings()

# E4 — Rate limiter global
limiter = Limiter(key_func=get_remote_address)


# M5 — Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Init au démarrage : SQLite schema + Qdrant collection."""
    print("🚀 MemoraEU API démarrage...")
    ms = await get_metadata_store()
    vs = await get_vector_store()
    print(f"✅ SQLite initialisé : {settings.sqlite_path}")
    print(f"✅ Qdrant connecté : {settings.qdrant_url}")
    print(f"✅ Embedding : {settings.embed_provider} / {settings.embed_model}")
    yield
    print("👋 MemoraEU API arrêt")


app = FastAPI(
    title="MemoraEU API",
    description="Couche mémoire universelle, zero-knowledge, hébergée en Europe.",
    version="0.1.0",
    lifespan=lifespan
)

# E4 — Attacher le limiter à l'app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# M5 — Security headers
app.add_middleware(SecurityHeadersMiddleware)

# M3 — CORS restreint aux origines de production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app.memoraeu.com",
        "https://memoraeu.com",
        "https://claude.ai",
        "https://cursor.sh",
        "https://codeium.com",
        "https://chatgpt.com",
        "https://chat.openai.com",
        "http://localhost:5173",   # dev local dashboard
        "http://localhost:3000",   # dev local landing
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(memories.router)
app.include_router(users.router)
app.include_router(api_keys.router)
app.include_router(usage.router)
app.include_router(admin.router)
app.include_router(billing.router)
app.include_router(org.router)
app.include_router(facts.router)
app.include_router(mcp_sse.router)
app.include_router(oauth.router)


@app.get("/.well-known/mcp.json", include_in_schema=False)
async def mcp_discovery():
    """Découverte automatique du serveur MCP — convention émergente."""
    return {
        "name": "memoraeu",
        "display_name": "MemoraEU",
        "description": (
            "Zero-knowledge persistent memory layer for AI agents. "
            "Stores, indexes and retrieves information in natural language. "
            "All content is encrypted client-side — the server never sees plaintext. "
            "Hosted in Europe (GDPR compliant)."
        ),
        "version": "0.1.7",
        "url": "https://api.memoraeu.com",
        "homepage": "https://memoraeu.com",
        "documentation": "https://memoraeu.com/docs/api",
        "license": "MIT",
        "transport": ["stdio", "sse"],
        "remotes": {
            "sse": "https://api.memoraeu.com/mcp/sse"
        },
        "install": {
            "uvx": "memoraeu-mcp@latest",
            "pip": "memoraeu-mcp",
            "pypi": "https://pypi.org/project/memoraeu-mcp/"
        },
        "configuration": {
            "env": {
                "MEMORAEU_API_URL": {
                    "description": "API base URL",
                    "default": "https://api.memoraeu.com",
                    "required": False
                },
                "MEMORAEU_API_KEY": {
                    "description": "Bearer token (meu-sk-…) from app.memoraeu.com",
                    "required": True
                },
                "MEMORAEU_SECRET": {
                    "description": "User password — used locally to derive AES-256 encryption key via PBKDF2. Never sent to the server.",
                    "required": True,
                    "sensitive": True
                },
                "MEMORAEU_SALT": {
                    "description": "KDF salt unique per account, provided at registration.",
                    "required": True,
                    "sensitive": True
                }
            }
        },
        "tools": [
            {
                "name": "remember",
                "description": "Store a memory with optional category and tags. Content is encrypted client-side before transmission."
            },
            {
                "name": "recall",
                "description": "Semantic search through memories in natural language."
            },
            {
                "name": "forget",
                "description": "Delete a memory by its ID."
            },
            {
                "name": "list_memories",
                "description": "List recent memories with optional category filter."
            },
            {
                "name": "list_categories",
                "description": "Return existing categories sorted by usage."
            },
            {
                "name": "remember_fact",
                "description": "Store a structured fact (subject/predicate/object) with temporal validity. Auto-invalidates the previous value on the same (subject, predicate)."
            },
            {
                "name": "recall_facts",
                "description": "Retrieve active facts for a subject. Supports full history with history=true."
            },
            {
                "name": "invalidate_fact",
                "description": "Mark a fact as expired by its ID."
            }
        ],
        "security": {
            "zero_knowledge": True,
            "encryption": "AES-256-GCM",
            "kdf": "PBKDF2-SHA256 (210 000 iterations)",
            "data_residency": "France (OVH)"
        }
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "embed_provider": settings.embed_provider,
        "embed_model": settings.embed_model
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload
    )
