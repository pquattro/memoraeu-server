import uuid
from datetime import datetime
from api.models import Memory, MemoryCreate, SearchRequest, SearchResponse, SearchResult
from api.services.embedding import get_embedding_service
from api.services.vector_store import get_vector_store
from api.services.metadata_store import get_metadata_store
from api.services.category_suggester import suggest_category
from api.services.compressor import compress_if_needed
from api.config import get_settings

settings = get_settings()


class MemoryService:
    """
    Orchestre embedding → vector_store → metadata_store.
    Point d'entrée unique pour toute opération sur les mémoires.
    """

    async def create(
        self,
        data: MemoryCreate,
        org_id: str = None,
        user_id: str = None
    ) -> Memory:
        org_id = org_id or settings.default_org_id
        user_id = user_id or settings.default_user_id

        if data.pre_processed:
            # Contenu déjà traité côté client (chiffré) — on skip compression et catégorisation
            content = data.content
            category = data.category or "personnel"
            print(f"[memory_service] pre_processed=True, skip compression/catégorisation")
        else:
            # Compression si contenu long
            content, was_compressed = await compress_if_needed(data.content)
            if was_compressed:
                data = data.model_copy(update={"content": content})

            # Suggestion auto de catégorie si non fournie
            category = data.category
            if not category:
                ms = await get_metadata_store()
                existing = await ms.get_categories(org_id, limit=20)
                existing_names = [c.name for c in existing]
                category = await suggest_category(data.content, existing_names)
                if category:
                    print(f"[category_suggester] Catégorie suggérée : {category}")

        memory = Memory(
            id=str(uuid.uuid4()),
            org_id=org_id,
            user_id=user_id,
            content=data.content,
            category=category,
            tags=data.tags,
            source=data.source,
            scope=data.scope,
        )

        # 1. Embedding — utilise le vecteur pré-calculé si fourni (zero-knowledge)
        if data.embedding:
            vector = data.embedding
            print(f"[memory_service] Embedding pré-calculé reçu ({len(vector)} dims)")
        else:
            embedder = get_embedding_service()
            vector = await embedder.embed(data.content)

        # 2. Qdrant
        vs = await get_vector_store()
        await vs.upsert(
            org_id=org_id,
            user_id=user_id,
            memory_id=memory.id,
            vector=vector,
            payload={
                "category": category,
                "scope": data.scope,
                "source": data.source,
                "tags": data.tags,
                # M2 — pas de content_preview en clair dans Qdrant (zero-knowledge)
            }
        )

        # 3. SQLite
        ms = await get_metadata_store()
        await ms.save_memory(memory)

        return memory

    async def search(
        self,
        request: SearchRequest,
        org_id: str = None,
        user_id: str = None
    ) -> SearchResponse:
        org_id = org_id or request.org_id or settings.default_org_id
        user_id = user_id or request.user_id or settings.default_user_id

        # 1. Embed la requête
        embedder = get_embedding_service()
        query_vector = await embedder.embed(request.query)

        # 2. Recherche vectorielle
        vs = await get_vector_store()
        vector_results = await vs.search(
            org_id=org_id,
            user_id=user_id,
            query_vector=query_vector,
            scope=request.scope,
            category=request.category,
            limit=request.limit
        )

        if not vector_results:
            return SearchResponse(results=[], total=0, query=request.query)

        # 3. Récupérer les métadonnées complètes depuis SQLite
        memory_ids = [r.memory_id for r in vector_results]
        ms = await get_metadata_store()
        memories_by_id = {
            m.id: m
            for m in await ms.get_memories_by_ids(memory_ids, org_id)
        }

        # 4. Assembler résultats dans l'ordre du score
        results = []
        for vr in vector_results:
            memory = memories_by_id.get(vr.memory_id)
            if memory:
                # Filtre tags côté Python si demandé
                if request.tags:
                    if not any(t in memory.tags for t in request.tags):
                        continue
                results.append(SearchResult(memory=memory, score=vr.score))

        return SearchResponse(results=results, total=len(results), query=request.query)

    async def delete(
        self,
        memory_id: str,
        org_id: str = None,
        user_id: str = None
    ) -> bool:
        org_id = org_id or settings.default_org_id
        user_id = user_id or settings.default_user_id

        # Résoudre l'ID partiel → UUID complet
        ms = await get_metadata_store()
        memory = await ms.get_memory(memory_id, org_id, user_id)
        if not memory:
            return False
        full_id = memory.id

        vs = await get_vector_store()
        await vs.delete(org_id=org_id, user_id=user_id, memory_id=full_id)
        return await ms.delete_memory(full_id, org_id, user_id)

    async def list(
        self,
        org_id: str = None,
        user_id: str = None,
        scope: str = "private",
        category: str = None,
        limit: int = 50,
        offset: int = 0
    ) -> list[Memory]:
        org_id = org_id or settings.default_org_id
        user_id = user_id or settings.default_user_id

        ms = await get_metadata_store()
        return await ms.list_memories(
            org_id=org_id,
            user_id=user_id,
            scope=scope,
            category=category,
            limit=limit,
            offset=offset
        )


_service: MemoryService | None = None


def get_memory_service() -> MemoryService:
    global _service
    if _service is None:
        _service = MemoryService()
    return _service
