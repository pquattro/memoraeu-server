from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from api.routers import memories, users, auth, api_keys, usage, org
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
    ms = await get_metadata_store()
    vs = await get_vector_store()
    yield


app = FastAPI(
    title="MemoraEU API",
    description=(
        "Universal, sovereign, zero-knowledge memory layer for AI assistants.\n\n"
        "- **MCP transports**: Legacy SSE (`GET /mcp/sse`) + HTTP Streamable (`POST /mcp/sse`)\n"
        "- **Auth**: Bearer token (`meu-sk-...`) via `Authorization` header or `?token=` query param\n"
        "- **Zero-knowledge**: content encrypted client-side with AES-256-GCM — server never sees plaintext\n\n"
        "Source: [github.com/pquattro/memoraeu-server](https://github.com/pquattro/memoraeu-server) · "
        "Cloud: [memoraeu.com](https://memoraeu.com)"
    ),
    version="1.3.0",
    lifespan=lifespan,
    license_info={"name": "AGPL v3", "url": "https://www.gnu.org/licenses/agpl-3.0.html"},
    contact={"name": "MemoraEU", "url": "https://memoraeu.com"},
)

# E4 — Attacher le limiter à l'app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# M5 — Security headers
app.add_middleware(SecurityHeadersMiddleware)

# M3 — CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(memories.router)
app.include_router(users.router)
app.include_router(api_keys.router)
app.include_router(usage.router)
app.include_router(org.router)
app.include_router(facts.router)
app.include_router(mcp_sse.router)
app.include_router(oauth.router)


@app.get("/.well-known/mcp.json", include_in_schema=False)
async def mcp_discovery():
    return {
        "name": "memoraeu",
        "display_name": "MemoraEU",
        "description": (
            "Zero-knowledge persistent memory layer for AI agents. "
            "Stores, indexes and retrieves information in natural language. "
            "All content is encrypted client-side — the server never sees plaintext. "
            "Hosted in Europe (GDPR compliant)."
        ),
        "version": "1.3.0",
        "url": "https://api.memoraeu.com",
        "homepage": "https://memoraeu.com",
        "documentation": "https://memoraeu.com/docs/api",
        "license": "AGPL v3",
        "transport": ["stdio", "sse"],
        "remotes": {"sse": "https://api.memoraeu.com/mcp/sse"},
        "install": {
            "uvx": "memoraeu-mcp@latest",
            "pip": "memoraeu-mcp",
            "pypi": "https://pypi.org/project/memoraeu-mcp/"
        },
    }


@app.get("/health", tags=["System"])
async def health():
    return {
        "status": "ok",
        "version": "1.3.0",
        "embed_provider": settings.embed_provider,
        "embed_model": settings.embed_model,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload
    )
