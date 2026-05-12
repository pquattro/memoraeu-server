"""
Suggestion automatique de catégorie.
Provider : Mistral AI si MISTRAL_API_KEY présent, sinon Ollama local.
Non bloquant : retourne None en cas d'erreur.
"""
import httpx
from api.config import get_settings

settings = get_settings()

SYSTEM_PROMPT = (
    "Tu es un assistant de classification de notes personnelles. "
    "Réponds UNIQUEMENT avec un seul mot en minuscules, sans ponctuation ni explication."
)

USER_TEMPLATE = """Catégories existantes : {categories}

Texte à classifier : "{content}"

Règles :
- Si le texte correspond à une catégorie existante, utilise-la
- Sinon, crée une catégorie courte (1 mot, minuscules)

Catégorie :"""


def _clean_category(raw: str) -> str | None:
    word = raw.strip().lower().split()[0] if raw.strip().split() else None
    if word:
        word = "".join(c for c in word if c.isalnum() or c == "-")
    return word or None


async def _suggest_mistral(content: str, existing: list[str]) -> str | None:
    cats = ", ".join(existing) if existing else "aucune pour l'instant"
    user_msg = USER_TEMPLATE.format(categories=cats, content=content[:500])
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{settings.mistral_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.mistral_api_key}"},
                json={
                    "model": settings.mistral_model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 10,
                }
            )
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"]
            return _clean_category(raw)
    except Exception as e:
        print(f"[category_suggester/mistral] Erreur : {e}")
        return None


async def _suggest_ollama(content: str, existing: list[str]) -> str | None:
    cats = ", ".join(existing) if existing else "aucune pour l'instant"
    prompt = USER_TEMPLATE.format(categories=cats, content=content[:500])
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": "llama3.2",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 10},
                }
            )
            r.raise_for_status()
            raw = r.json().get("response", "")
            return _clean_category(raw)
    except Exception as e:
        print(f"[category_suggester/ollama] Erreur : {e}")
        return None


async def suggest_category(content: str, existing_categories: list[str]) -> str | None:
    if settings.mistral_api_key:
        return await _suggest_mistral(content, existing_categories)
    return await _suggest_ollama(content, existing_categories)
