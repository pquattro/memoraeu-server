from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Literal
from api.models import Fact, FactCreate, FactInvalidate
from api.services.metadata_store import get_metadata_store
from api.dependencies import get_current_user

router = APIRouter(prefix="/facts", tags=["facts"])


@router.post("", response_model=Fact, status_code=201)
async def create_fact(
    data: FactCreate,
    current_user=Depends(get_current_user),
):
    """Crée un fait. Invalide automatiquement le précédent sur même (subject, predicate, scope)."""
    ms = await get_metadata_store()
    data.org_id = current_user.org_id
    data.user_id = current_user.id
    try:
        return await ms.create_fact(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=list[Fact])
async def list_facts(
    subject: Optional[str] = Query(None),
    predicate: Optional[str] = Query(None),
    scope: Literal["private", "org"] = Query("private"),
    history: bool = Query(False, description="Inclure les faits expirés"),
    current_user=Depends(get_current_user),
):
    """Liste les faits actifs (valid_to IS NULL) ou l'historique complet."""
    ms = await get_metadata_store()
    return await ms.list_facts(
        org_id=current_user.org_id,
        user_id=current_user.id,
        scope=scope,
        subject=subject,
        predicate=predicate,
        include_history=history,
    )


@router.get("/contradictions")
async def get_contradictions(
    scope: Literal["private", "org"] = Query("private"),
    current_user=Depends(get_current_user),
):
    """Détecte les (subject, predicate) avec plusieurs faits actifs simultanément."""
    ms = await get_metadata_store()
    return await ms.get_fact_contradictions(
        org_id=current_user.org_id,
        user_id=current_user.id,
        scope=scope,
    )


@router.get("/history")
async def get_fact_history(
    subject: str = Query(...),
    predicate: str = Query(...),
    scope: Literal["private", "org"] = Query("private"),
    current_user=Depends(get_current_user),
):
    """Historique temporel complet d'un fait (subject + predicate)."""
    ms = await get_metadata_store()
    return await ms.list_facts(
        org_id=current_user.org_id,
        user_id=current_user.id,
        scope=scope,
        subject=subject,
        predicate=predicate,
        include_history=True,
    )


@router.get("/{fact_id}", response_model=Fact)
async def get_fact(
    fact_id: str,
    current_user=Depends(get_current_user),
):
    ms = await get_metadata_store()
    fact = await ms.get_fact(fact_id, current_user.org_id, current_user.id)
    if not fact:
        raise HTTPException(status_code=404, detail="Fait introuvable")
    return fact


@router.put("/{fact_id}/invalidate", response_model=dict)
async def invalidate_fact(
    fact_id: str,
    body: FactInvalidate = None,
    current_user=Depends(get_current_user),
):
    """Marque un fait comme expiré (valid_to = aujourd'hui ou date fournie)."""
    ms = await get_metadata_store()
    valid_to = body.valid_to if body else None
    ok = await ms.invalidate_fact(fact_id, current_user.org_id, current_user.id, valid_to)
    if not ok:
        raise HTTPException(status_code=404, detail="Fait introuvable ou déjà invalidé")
    return {"invalidated": True, "fact_id": fact_id}
