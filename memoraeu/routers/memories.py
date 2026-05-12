from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal, Optional
from api.models import (
    MemoryCreate, Memory, SearchRequest, SearchResponse,
    CategoriesResponse, User
)
from api.services.memory_service import get_memory_service
from api.services.metadata_store import get_metadata_store
from api.services.vector_store import get_vector_store
from api.dependencies import get_current_user


class VectorSearchRequest(BaseModel):
    vector: list[float]
    limit: int = Field(1, ge=1, le=100)
    scope: Literal["private", "org", "all"] = "private"
    threshold: float = Field(0.0, ge=0.0, le=1.0)

router = APIRouter(prefix="/memories", tags=["memories"])


@router.post("", response_model=Memory, status_code=201)
async def create_memory(
    data: MemoryCreate,
    current_user: User = Depends(get_current_user),
):
    """Crée une nouvelle mémoire et l'indexe dans Qdrant."""
    ms = await get_metadata_store()

    # ── Vérification limite du plan ──────────────────────────────────────────
    plan_name = await ms.get_org_plan(current_user.org_id)
    plan = await ms.get_plan(plan_name)
    if plan["max_memories"] != -1:
        total = await ms.count_memories(current_user.org_id)
        if total >= plan["max_memories"]:
            raise HTTPException(
                status_code=429,
                detail=f"Limite du plan {plan['label']} atteinte ({plan['max_memories']} mémoires). "
                       f"Passez au plan supérieur pour continuer."
            )

    svc = get_memory_service()
    try:
        memory = await svc.create(data, org_id=current_user.org_id, user_id=current_user.id)
        # ── Tracking ─────────────────────────────────────────────────────────
        await ms.increment_usage(current_user.org_id, "memories_created")
        return memory
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=SearchResponse)
async def search_memories(
    request: SearchRequest,
    current_user: User = Depends(get_current_user),
):
    """Recherche sémantique dans les mémoires."""
    ms = await get_metadata_store()

    # ── Vérification limite recalls/jour ────────────────────────────────────
    plan_name = await ms.get_org_plan(current_user.org_id)
    plan = await ms.get_plan(plan_name)
    if plan["max_recalls_per_day"] != -1:
        today = await ms.get_usage_today(current_user.org_id)
        if today["recalls"] >= plan["max_recalls_per_day"]:
            raise HTTPException(
                status_code=429,
                detail=f"Limite de recalls journaliers atteinte ({plan['max_recalls_per_day']}/jour). "
                       f"Passez au plan supérieur ou réessayez demain."
            )

    svc = get_memory_service()
    try:
        result = await svc.search(request, org_id=current_user.org_id, user_id=current_user.id)
        await ms.increment_usage(current_user.org_id, "recalls")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=list[Memory])
async def list_memories(
    scope: str = Query("private", enum=["private", "org"]),
    category: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
):
    """Liste les mémoires avec filtres optionnels."""
    svc = get_memory_service()
    return await svc.list(
        org_id=current_user.org_id,
        user_id=current_user.id,
        scope=scope,
        category=category,
        limit=limit,
        offset=offset
    )


@router.post("/search-by-vector", response_model=SearchResponse)
async def search_by_vector(
    request: VectorSearchRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Recherche par vecteur pré-calculé (zero-knowledge).
    Le MCP génère l'embedding côté client et l'envoie directement —
    aucun plaintext ne transite vers le serveur.
    """
    ms = await get_metadata_store()

    # ── Vérification limite recalls/jour ────────────────────────────────────
    plan_name = await ms.get_org_plan(current_user.org_id)
    plan = await ms.get_plan(plan_name)
    if plan["max_recalls_per_day"] != -1:
        today = await ms.get_usage_today(current_user.org_id)
        if today["recalls"] >= plan["max_recalls_per_day"]:
            raise HTTPException(
                status_code=429,
                detail=f"Limite de recalls journaliers atteinte ({plan['max_recalls_per_day']}/jour). "
                       f"Passez au plan supérieur ou réessayez demain."
            )

    vs = await get_vector_store()
    vector_results = await vs.search(
        org_id=current_user.org_id,
        user_id=current_user.id,
        query_vector=request.vector,
        scope=request.scope,
        limit=request.limit,
    )

    # Filtrer par threshold
    vector_results = [r for r in vector_results if r.score >= request.threshold]

    if not vector_results:
        return SearchResponse(results=[], total=0, query="[vector]")

    memory_ids = [r.memory_id for r in vector_results]
    memories_by_id = {m.id: m for m in await ms.get_memories_by_ids(memory_ids, current_user.org_id)}

    from api.models import SearchResult
    results = []
    for vr in vector_results:
        memory = memories_by_id.get(vr.memory_id)
        if memory:
            results.append(SearchResult(memory=memory, score=vr.score))

    await ms.increment_usage(current_user.org_id, "recalls")
    return SearchResponse(results=results, total=len(results), query="[vector]")


@router.get("/categories", response_model=CategoriesResponse)
async def get_categories(current_user: User = Depends(get_current_user)):
    """Retourne les catégories existantes triées par usage (pour suggestions)."""
    ms = await get_metadata_store()
    categories = await ms.get_categories(current_user.org_id)
    return CategoriesResponse(categories=categories)


@router.get("/duplicates", response_model=list[dict])
async def find_duplicates(
    threshold: float = Query(0.94, ge=0.5, le=1.0),
    current_user: User = Depends(get_current_user),
):
    """
    Trouve les paires de mémoires similaires (doublons potentiels).
    Pour chaque mémoire, recherche son voisin le plus proche dans Qdrant
    sans recalculer d'embedding — utilise les vecteurs déjà stockés.
    """
    ms = await get_metadata_store()
    vs = await get_vector_store()

    memories = await ms.list_memories(
        org_id=current_user.org_id,
        user_id=current_user.id,
        scope="private",
        limit=500,
    )
    if len(memories) < 2:
        return []

    pairs_seen: set[tuple] = set()
    duplicates = []
    memories_by_id = {m.id: m for m in memories}

    for memory in memories:
        try:
            results = await vs.search_similar_to(
                org_id=current_user.org_id,
                user_id=current_user.id,
                memory_id=memory.id,
                scope="private",
                limit=1,
            )
        except Exception:
            continue

        for r in results:
            if r.score < threshold:
                continue
            pair_key = tuple(sorted([memory.id, r.memory_id]))
            if pair_key in pairs_seen:
                continue
            pairs_seen.add(pair_key)
            other = memories_by_id.get(r.memory_id)
            if other:
                duplicates.append({
                    "score": round(r.score, 4),
                    "memory_a": {"id": memory.id, "content": memory.content, "category": memory.category, "created_at": memory.created_at.isoformat()},
                    "memory_b": {"id": other.id,  "content": other.content,  "category": other.category,  "created_at": other.created_at.isoformat()},
                })

    duplicates.sort(key=lambda x: x["score"], reverse=True)
    return duplicates


@router.get("/{memory_id}", response_model=Memory)
async def get_memory(
    memory_id: str,
    current_user: User = Depends(get_current_user),
):
    """Récupère une mémoire par son ID."""
    ms = await get_metadata_store()
    memory = await ms.get_memory(memory_id, current_user.org_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Mémoire introuvable")
    return memory


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: str,
    current_user: User = Depends(get_current_user),
):
    """Supprime une mémoire (Qdrant + SQLite)."""
    svc = get_memory_service()
    try:
        deleted = await svc.delete(memory_id, org_id=current_user.org_id, user_id=current_user.id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Mémoire introuvable")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
