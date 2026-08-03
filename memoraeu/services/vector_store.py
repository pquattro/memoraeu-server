from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue
)
from api.config import get_settings
from dataclasses import dataclass

settings = get_settings()

# Dimension nomic-embed-text = 768
# Dimension mistral-embed    = 1024
# On la détecte dynamiquement au premier upsert
EMBED_DIM = {
    "nomic-embed-text": 768,
    "mistral-embed": 1024,
}


@dataclass
class VectorSearchResult:
    memory_id: str
    org_id: str
    user_id: str
    score: float
    payload: dict


class QdrantVectorStore:
    """
    Toutes les opérations passent org_id + user_id.
    L'isolation multi-tenant est garantie par les filtres Qdrant.
    """

    def __init__(self):
        self.client = AsyncQdrantClient(url=settings.qdrant_url)
        self.collection = settings.qdrant_collection

    async def ensure_collection(self):
        """Crée la collection si elle n'existe pas."""
        collections = await self.client.get_collections()
        names = [c.name for c in collections.collections]
        if self.collection not in names:
            dim = EMBED_DIM.get(settings.embed_model, 768)
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=dim,
                    distance=Distance.COSINE
                )
            )
            # Index sur org_id et user_id pour les filtres rapides
            await self.client.create_payload_index(
                collection_name=self.collection,
                field_name="org_id",
                field_schema="keyword"
            )
            await self.client.create_payload_index(
                collection_name=self.collection,
                field_name="user_id",
                field_schema="keyword"
            )
            await self.client.create_payload_index(
                collection_name=self.collection,
                field_name="scope",
                field_schema="keyword"
            )

    async def upsert(
        self,
        org_id: str,
        user_id: str,
        memory_id: str,
        vector: list[float],
        payload: dict
    ) -> None:
        payload_full = {
            "org_id": org_id,
            "user_id": user_id,
            "memory_id": memory_id,
            **payload
        }
        await self.client.upsert(
            collection_name=self.collection,
            points=[PointStruct(
                id=memory_id,
                vector=vector,
                payload=payload_full
            )]
        )

    async def search(
        self,
        org_id: str,
        user_id: str,
        query_vector: list[float],
        scope: str = "private",
        category: str = None,
        limit: int = 10
    ) -> list[VectorSearchResult]:
        """
        scope="private" → mémoires du user uniquement
        scope="org"     → mémoires de toute l'org
        scope="all"     → private + org
        """
        conditions = [
            FieldCondition(key="org_id", match=MatchValue(value=org_id))
        ]

        should: list = []
        if scope == "private":
            conditions.append(
                FieldCondition(key="user_id", match=MatchValue(value=user_id))
            )
        elif scope == "org":
            # Filtrer sur le scope réellement enregistré : sans cela, "org"
            # remontait aussi les mémoires privées des autres utilisateurs.
            conditions.append(FieldCondition(key="scope", match=MatchValue(value="org")))
        else:  # "all" -> les siennes OU celles partagees a l'org
            should = [
                FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                FieldCondition(key="scope", match=MatchValue(value="org")),
            ]

        if category:
            conditions.append(
                FieldCondition(key="category", match=MatchValue(value=category))
            )

        response = await self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            query_filter=(Filter(must=conditions, should=should) if should
                          else Filter(must=conditions)),
            limit=limit,
            with_payload=True
        )

        return [
            VectorSearchResult(
                memory_id=str(r.id),
                org_id=r.payload.get("org_id", ""),
                user_id=r.payload.get("user_id", ""),
                score=r.score,
                payload=r.payload
            )
            for r in response.points
        ]

    async def search_similar_to(
        self,
        org_id: str,
        user_id: str,
        memory_id: str,
        scope: str = "private",
        limit: int = 2,
    ) -> list[VectorSearchResult]:
        """
        Trouve les mémoires similaires à une mémoire existante (par son ID).
        Utilise le vecteur déjà stocké dans Qdrant — aucun embedding supplémentaire.
        """
        # 1. Récupérer le vecteur stocké
        points = await self.client.retrieve(
            collection_name=self.collection,
            ids=[memory_id],
            with_vectors=True,
            with_payload=True,
        )
        if not points or points[0].vector is None:
            return []
        vector = points[0].vector

        # 2. Chercher les voisins (en excluant la mémoire elle-même)
        conditions = [
            FieldCondition(key="org_id", match=MatchValue(value=org_id))
        ]
        if scope == "private":
            conditions.append(FieldCondition(key="user_id", match=MatchValue(value=user_id)))

        response = await self.client.query_points(
            collection_name=self.collection,
            query=vector,
            query_filter=Filter(must=conditions),
            limit=limit + 1,  # +1 pour exclure self
            with_payload=True,
        )

        return [
            VectorSearchResult(
                memory_id=str(r.id),
                org_id=r.payload.get("org_id", ""),
                user_id=r.payload.get("user_id", ""),
                score=r.score,
                payload=r.payload,
            )
            for r in response.points
            if str(r.id) != memory_id   # exclure la mémoire elle-même
        ]

    async def delete(self, org_id: str, user_id: str, memory_id: str) -> None:
        """
        Vérifie l'appartenance avant suppression (sécurité multi-tenant).
        """
        points = await self.client.retrieve(
            collection_name=self.collection,
            ids=[memory_id],
            with_payload=True
        )
        if not points:
            return
        point = points[0]
        # Vérification appartenance
        if point.payload.get("org_id") != org_id:
            raise PermissionError("Mémoire hors scope organisation")
        if point.payload.get("user_id") != user_id and point.payload.get("scope") == "private":
            raise PermissionError("Mémoire privée d'un autre utilisateur")

        await self.client.delete(
            collection_name=self.collection,
            points_selector=[memory_id]
        )


_store: QdrantVectorStore | None = None


async def get_vector_store() -> QdrantVectorStore:
    global _store
    if _store is None:
        _store = QdrantVectorStore()
        await _store.ensure_collection()
    return _store
