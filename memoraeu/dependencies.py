"""
MemoraEU — Dépendances FastAPI
Injection du user courant via JWT Bearer token OU clé API meu-sk-xxxx.
"""
import hashlib
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.models import User
from api.services.auth_service import decode_access_token
from api.services.metadata_store import get_metadata_store

bearer_scheme = HTTPBearer(auto_error=False)

API_KEY_PREFIX = "meu-sk-"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    """
    Accepte deux formats Bearer :
    - JWT  : émis par /auth/login ou /auth/register
    - API Key : meu-sk-xxxx  (hashée en DB, last_used_at mis à jour)
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token Bearer manquant",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    ms = await get_metadata_store()

    # ── Clé API meu-sk-xxxx ───────────────────────────────────────────────────
    if token.startswith(API_KEY_PREFIX):
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        row = await ms.get_api_key_by_hash(key_hash)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Clé API invalide ou révoquée",
            )
        # Mise à jour last_used_at (non-bloquant)
        await ms.touch_api_key(row["id"])
        # Charger le user associé
        user = await ms.get_user_by_id(row["user_id"])
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Utilisateur introuvable",
            )
        return user

    # ── JWT ───────────────────────────────────────────────────────────────────
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # E3 — vérification révocation via jti
    jti = payload.get("jti")
    if jti and await ms.is_token_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token révoqué",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await ms.get_user_by_id(payload.get("sub"))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur introuvable",
        )
    return user
