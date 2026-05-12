from typing import Protocol
import httpx
from api.config import get_settings

settings = get_settings()


class EmbeddingService(Protocol):
    async def embed(self, text: str) -> list[float]: ...
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbedding:
    """
    Embedding local via Ollama (nomic-embed-text).
    Zéro donnée sortante — tourne sur la machine locale.
    Compatible GPU via Ollama si disponible (RTX 4070).
    """

    def __init__(self, model: str = None, base_url: str = None):
        self.model = model or settings.embed_model
        self.base_url = base_url or settings.embed_url

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text}
            )
            response.raise_for_status()
            return response.json()["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Ollama ne supporte pas le batch natif — on parallélise
        import asyncio
        return await asyncio.gather(*[self.embed(t) for t in texts])


class MistralEmbedding:
    """
    Embedding via Mistral AI (mistral-embed).
    Hébergé en EU — alternative cloud pour prod.
    Nécessite MISTRAL_API_KEY dans .env
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.mistral_api_key
        self.base_url = settings.mistral_base_url

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": "mistral-embed", "input": [text]}
            )
            response.raise_for_status()
            return response.json()["data"][0]["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": "mistral-embed", "input": texts}
            )
            response.raise_for_status()
            data = response.json()["data"]
            return [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]


def get_embedding_service() -> OllamaEmbedding | MistralEmbedding:
    """Factory — switcher via .env sans toucher au code."""
    provider = settings.embed_provider.lower()
    if provider == "ollama":
        return OllamaEmbedding()
    elif provider == "mistral":
        return MistralEmbedding()
    else:
        raise ValueError(f"Embedding provider inconnu : {provider}")
