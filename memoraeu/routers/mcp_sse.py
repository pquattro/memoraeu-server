"""
MemoraEU — Transport MCP remote (dual: Legacy SSE + HTTP Streamable)

Legacy SSE (Cursor, curl)        : GET  /mcp/sse  +  POST /mcp/messages
HTTP Streamable (claude.ai 2025) : POST /mcp/sse  (avec gestion de session)

Auth : Authorization: Bearer header  OU  ?token= query param.
"""
import asyncio
import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http import StreamableHTTPServerTransport
from mcp.types import TextContent, Tool

from api.models import User
from api.services.memory_service import get_memory_service
from api.services.metadata_store import get_metadata_store

router = APIRouter(tags=["mcp"])

bearer_scheme = HTTPBearer(auto_error=False)

# Legacy SSE transport (Cursor, curl, clients MCP < 2025)
sse_transport = SseServerTransport("/mcp/messages")

# Sessions HTTP Streamable actives  {session_id → {transport, task, ready_event}}
_streamable_sessions: dict[str, dict] = {}

# Désactiver DNS rebinding protection — on est derrière nginx TLS, requêtes légitimes d'Anthropic
from mcp.server.transport_security import TransportSecuritySettings
_no_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)


# ── Auth ───────────────────────────────────────────────────────────────────

async def get_mcp_user(
    request: Request,
    token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    """Accepte Bearer header OU ?token= query param (EventSource navigateur)."""
    raw = (credentials.credentials if credentials else None) or token
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token manquant — passer Authorization: Bearer ou ?token=",
            headers={"WWW-Authenticate": "Bearer"},
        )

    ms = await get_metadata_store()

    if raw.startswith("meu-sk-"):
        key_hash = hashlib.sha256(raw.encode()).hexdigest()
        row = await ms.get_api_key_by_hash(key_hash)
        if not row:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clé API invalide.")
        await ms.touch_api_key(row["id"])
        user = await ms.get_user_by_id(row["user_id"])
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable.")
        return user

    from api.services.auth_service import decode_access_token
    import jwt as pyjwt
    try:
        payload = decode_access_token(raw)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expiré.")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide.")
    user = await ms.get_user_by_id(payload.get("sub"))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable.")
    return user


# ── MCP Server builder ─────────────────────────────────────────────────────

def _build_mcp_server(user: User) -> Server:
    server = Server("memoraeu")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="remember",
                description=(
                    "Store a memory with optional category and tags. "
                    "Use automatically when the user shares preferences, decisions, biographical facts, "
                    "or durable constraints."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "category": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["content"],
                },
            ),
            Tool(
                name="recall",
                description=(
                    "Semantic search through memories in natural language. "
                    "Call automatically on the first message of each conversation."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 3},
                        "category": {"type": "string"},
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="forget",
                description="Delete a memory by its ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"memory_id": {"type": "string"}},
                    "required": ["memory_id"],
                },
            ),
            Tool(
                name="list_memories",
                description="List recent memories with optional category filter.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "limit": {"type": "integer", "default": 20},
                    },
                },
            ),
            Tool(
                name="list_categories",
                description="Return existing categories sorted by usage.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="remember_fact",
                description=(
                    "Store a structured fact (subject/predicate/object) with temporal validity. "
                    "Auto-invalidates the previous value on the same (subject, predicate)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string"},
                        "predicate": {"type": "string"},
                        "object": {"type": "string"},
                        "valid_from": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
                        "scope": {"type": "string", "enum": ["private", "org"], "default": "private"},
                    },
                    "required": ["subject", "predicate", "object"],
                },
            ),
            Tool(
                name="recall_facts",
                description="Retrieve active facts for a subject. Supports full history with history=true.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string"},
                        "predicate": {"type": "string"},
                        "scope": {"type": "string", "enum": ["private", "org"], "default": "private"},
                        "history": {"type": "boolean", "default": False},
                    },
                    "required": ["subject"],
                },
            ),
            Tool(
                name="invalidate_fact",
                description="Mark a fact as expired by its ID.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "fact_id": {"type": "string"},
                        "valid_to": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
                    },
                    "required": ["fact_id"],
                },
            ),
            # ── ChatGPT Deep Research tools ───────────────────────────────────
            Tool(
                name="search",
                description=(
                    "Search memories by natural language query. "
                    "Returns a list of relevant memories with scores. "
                    "Used by ChatGPT Deep Research mode."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural language search query"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="fetch",
                description=(
                    "Fetch a specific memory by its ID. "
                    "Used by ChatGPT Deep Research mode to retrieve full memory content."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Memory ID (full or prefix)"},
                    },
                    "required": ["id"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        svc = get_memory_service()
        ms = await get_metadata_store()

        plan_name = await ms.get_org_plan(user.org_id)
        plan = await ms.get_plan(plan_name)

        async def _check_memory_limit() -> TextContent | None:
            if plan["max_memories"] != -1:
                total = await ms.count_memories(user.org_id)
                if total >= plan["max_memories"]:
                    return TextContent(
                        type="text",
                        text=f"Memory limit reached ({plan['max_memories']} on {plan['label']} plan). Upgrade to store more.",
                    )
            return None

        async def _check_recall_limit() -> TextContent | None:
            if plan["max_recalls_per_day"] != -1:
                today = await ms.get_usage_today(user.org_id)
                if today["recalls"] >= plan["max_recalls_per_day"]:
                    return TextContent(
                        type="text",
                        text=f"Daily recall limit reached ({plan['max_recalls_per_day']} on {plan['label']} plan). Try again tomorrow or upgrade.",
                    )
            return None

        if name == "remember":
            try:
                if err := await _check_memory_limit():
                    return [err]
                from api.models import MemoryCreate
                data = MemoryCreate(
                    content=arguments["content"],
                    category=arguments.get("category"),
                    tags=arguments.get("tags", []),
                    source="mcp_sse",
                    scope="private",
                )
                memory = await svc.create(data, org_id=user.org_id, user_id=user.id)
                await ms.increment_usage(user.org_id, "memories_created")
                cat = memory.category or "uncategorized"
                return [TextContent(type="text", text=f"Stored (ID: {memory.id}, category: {cat})")]
            except Exception as e:
                return [TextContent(type="text", text=f"Error: {e}")]

        elif name == "recall":
            try:
                if err := await _check_recall_limit():
                    return [err]
                from api.models import SearchRequest
                req = SearchRequest(
                    query=arguments["query"],
                    limit=arguments.get("limit", 3),
                    category=arguments.get("category"),
                    scope="private",
                )
                result = await svc.search(req, org_id=user.org_id, user_id=user.id)
                await ms.increment_usage(user.org_id, "recalls")
                results = result.results
                if not results:
                    return [TextContent(type="text", text="No memories found.")]
                lines = [f"{len(results)} memory(ies):\n"]
                for r in results:
                    m = r.memory
                    cat = m.category or "—"
                    lines.append(f"• [{round(r.score * 100)}%] {m.content}\n  category: {cat} | ID: {m.id}")
                return [TextContent(type="text", text="\n".join(lines))]
            except Exception as e:
                return [TextContent(type="text", text=f"Error: {e}")]

        elif name == "forget":
            try:
                deleted = await svc.delete(arguments["memory_id"], org_id=user.org_id, user_id=user.id)
                return [TextContent(type="text", text="Deleted." if deleted else "Not found.")]
            except Exception as e:
                return [TextContent(type="text", text=f"Error: {e}")]

        elif name == "list_memories":
            try:
                memories = await svc.list(
                    org_id=user.org_id, user_id=user.id, scope="private",
                    category=arguments.get("category"), limit=arguments.get("limit", 20), offset=0,
                )
                if not memories:
                    return [TextContent(type="text", text="No memories.")]
                lines = [f"{len(memories)} memory(ies):\n"]
                for m in memories:
                    preview = m.content[:100] + ("…" if len(m.content) > 100 else "")
                    lines.append(f"• [{m.category or '—'}] {preview} (ID: {m.id})")
                return [TextContent(type="text", text="\n".join(lines))]
            except Exception as e:
                return [TextContent(type="text", text=f"Error: {e}")]

        elif name == "list_categories":
            try:
                response = await ms.get_categories(user.org_id)
                cats = response if isinstance(response, list) else response.get("categories", [])
                if not cats:
                    return [TextContent(type="text", text="No categories.")]
                lines = ["Categories:\n"] + [
                    f"• {c['name']} ({c['usage_count']})" if isinstance(c, dict)
                    else f"• {c.name} ({c.usage_count})" for c in cats
                ]
                return [TextContent(type="text", text="\n".join(lines))]
            except Exception as e:
                return [TextContent(type="text", text=f"Error: {e}")]

        elif name == "remember_fact":
            try:
                if err := await _check_memory_limit():
                    return [err]
                from api.models import FactCreate
                data = FactCreate(
                    subject=arguments["subject"], predicate=arguments["predicate"],
                    object=arguments["object"], valid_from=arguments.get("valid_from"),
                    scope=arguments.get("scope", "private"), org_id=user.org_id, user_id=user.id,
                )
                fact = await ms.create_fact(data)
                return [TextContent(type="text", text=f"Fact stored (ID: {fact.id})")]
            except Exception as e:
                return [TextContent(type="text", text=f"Error: {e}")]

        elif name == "recall_facts":
            try:
                facts = await ms.list_facts(
                    org_id=user.org_id, user_id=user.id, scope=arguments.get("scope", "private"),
                    subject=arguments["subject"], predicate=arguments.get("predicate"),
                    include_history=arguments.get("history", False),
                )
                if not facts:
                    return [TextContent(type="text", text="No facts found.")]
                lines = [f"{len(facts)} fact(s):\n"]
                for f in facts:
                    lines.append(f"• {f.subject} {f.predicate} {f.object} (valid from: {f.valid_from or '—'})")
                return [TextContent(type="text", text="\n".join(lines))]
            except Exception as e:
                return [TextContent(type="text", text=f"Error: {e}")]

        elif name == "invalidate_fact":
            try:
                ok = await ms.invalidate_fact(arguments["fact_id"], user.org_id, arguments.get("valid_to"))
                return [TextContent(type="text", text="Invalidated." if ok else "Not found.")]
            except Exception as e:
                return [TextContent(type="text", text=f"Error: {e}")]

        elif name == "search":
            try:
                if err := await _check_recall_limit():
                    return [err]
                from api.models import SearchRequest
                req = SearchRequest(
                    query=arguments["query"],
                    limit=arguments.get("limit", 10),
                    scope="private",
                )
                result = await svc.search(req, org_id=user.org_id, user_id=user.id)
                await ms.increment_usage(user.org_id, "recalls")
                results = result.results
                if not results:
                    return [TextContent(type="text", text="No memories found.")]
                lines = [f"{len(results)} result(s):\n"]
                for r in results:
                    m = r.memory
                    lines.append(
                        f"• id={m.id} score={round(r.score * 100)}% category={m.category or '—'}\n"
                        f"  {m.content}"
                    )
                return [TextContent(type="text", text="\n".join(lines))]
            except Exception as e:
                return [TextContent(type="text", text=f"Error: {e}")]

        elif name == "fetch":
            try:
                memory = await ms.get_memory(arguments["id"], org_id=user.org_id)
                if not memory:
                    return [TextContent(type="text", text="Memory not found.")]
                return [TextContent(
                    type="text",
                    text=f"id={memory.id}\ncategory={memory.category or '—'}\ntags={memory.tags}\n\n{memory.content}",
                )]
            except Exception as e:
                return [TextContent(type="text", text=f"Error: {e}")]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


# ── HTTP Streamable session management ─────────────────────────────────────

async def _run_streamable_session(session_id: str) -> None:
    """Background task : maintient le transport MCP ouvert pour une session."""
    session = _streamable_sessions.get(session_id)
    if not session:
        return
    transport: StreamableHTTPServerTransport = session["transport"]
    user: User = session["user"]
    mcp_server = _build_mcp_server(user)
    ready: asyncio.Event = session["ready"]
    try:
        async with transport.connect() as (read_stream, write_stream):
            ready.set()
            await mcp_server.run(read_stream, write_stream, mcp_server.create_initialization_options())
    finally:
        _streamable_sessions.pop(session_id, None)


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/mcp/sse")
async def mcp_sse_get(
    request: Request,
    current_user: User = Depends(get_mcp_user),
):
    """GET /mcp/sse — Legacy SSE stream (Cursor, curl)."""
    mcp_server = _build_mcp_server(current_user)
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send  # type: ignore[attr-defined]
    ) as (read_stream, write_stream):
        await mcp_server.run(read_stream, write_stream, mcp_server.create_initialization_options())


@router.post("/mcp/messages")
async def mcp_messages(request: Request):
    """POST /mcp/messages — messages client→server pour transport SSE legacy."""
    await sse_transport.handle_post_message(
        request.scope, request.receive, request._send  # type: ignore[attr-defined]
    )


@router.post("/mcp/sse")
async def mcp_sse_post(
    request: Request,
    current_user: User = Depends(get_mcp_user),
):
    """POST /mcp/sse — HTTP Streamable transport (spec MCP 2025, claude.ai web)."""
    session_id = request.headers.get("mcp-session-id")

    # Session existante → router vers le bon transport
    if session_id and session_id in _streamable_sessions:
        transport = _streamable_sessions[session_id]["transport"]
        await transport.handle_request(request.scope, request.receive, request._send)  # type: ignore
        return

    # Nouvelle session
    new_sid = uuid.uuid4().hex
    transport = StreamableHTTPServerTransport(
        mcp_session_id=new_sid,
        is_json_response_enabled=False,
        security_settings=_no_security,
    )
    ready = asyncio.Event()
    _streamable_sessions[new_sid] = {
        "transport": transport,
        "user": current_user,
        "ready": ready,
    }
    task = asyncio.create_task(_run_streamable_session(new_sid))
    _streamable_sessions[new_sid]["task"] = task

    # Attendre que connect() soit entré (streams prêts)
    await asyncio.wait_for(ready.wait(), timeout=5.0)

    await transport.handle_request(request.scope, request.receive, request._send)  # type: ignore
