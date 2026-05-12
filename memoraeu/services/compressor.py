"""
Compression automatique des mémoires longues.
Déclenché si len(content) > COMPRESSION_THRESHOLD.
Non bloquant : retourne le contenu original en cas d'erreur.

Provider : Mistral AI si MISTRAL_API_KEY présent, sinon Ollama local.
"""
import httpx
from api.config import get_settings

settings = get_settings()

COMPRESSION_THRESHOLD = 300  # caractères
MAX_COMPRESSED_LENGTH = 250  # cible de compression

SYSTEM_PROMPT = (
    "Tu es un assistant de mémorisation. Résume le texte en conservant "
    "les faits essentiels, chiffres, noms propres et décisions. "
    "Supprime les détails redondants. Réponds UNIQUEMENT avec le résumé."
)


async def _compress_mistral(content: str) -> str | None:
    prompt = f"Résume en {MAX_COMPRESSED_LENGTH} caractères maximum :\n\n{content}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{settings.mistral_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.mistral_api_key}"},
                json={
                    "model": settings.mistral_model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 200,
                }
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[compressor/mistral] Erreur : {e}")
        return None


async def _compress_ollama(content: str) -> str | None:
    prompt = (
        f"Résume en {MAX_COMPRESSED_LENGTH} caractères maximum. "
        f"Conserve les faits essentiels. Réponds UNIQUEMENT avec le résumé.\n\n{content}"
    )
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": "llama3.2",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 300},
                }
            )
            r.raise_for_status()
            return r.json().get("response", "").strip() or None
    except Exception as e:
        print(f"[compressor/ollama] Erreur : {e}")
        return None


async def compress_if_needed(content: str) -> tuple[str, bool]:
    """
    Retourne (contenu_final, was_compressed).
    Si content <= COMPRESSION_THRESHOLD, retourne tel quel.
    """
    if len(content) <= COMPRESSION_THRESHOLD:
        return content, False

    compressed = None
    if settings.mistral_api_key:
        compressed = await _compress_mistral(content)
    else:
        compressed = await _compress_ollama(content)

    if compressed and _is_valid_compression(content, compressed):
        print(f"[compressor] {len(content)} → {len(compressed)} chars")
        return compressed, True

    return content, False


def _is_valid_compression(original: str, compressed: str) -> bool:
    """Vérifie que la compression est valide — rejette les messages d'erreur Mistral."""
    if len(compressed) >= len(original):
        return False  # pas de compression réelle
    error_markers = [
        "erreur", "illisible", "impossible", "chiffré", "incompréhensible",
        "cannot", "unable", "encrypted", "error", "je ne peux pas", "je suis désolé"
    ]
    lower = compressed.lower()
    if any(m in lower for m in error_markers):
        print(f"[compressor] Réponse invalide détectée, contenu original conservé")
        return False
    return True
