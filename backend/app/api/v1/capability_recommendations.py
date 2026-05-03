from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db
from app.core.identity import Actor
from app.schemas.capability_recommendation import (
    CapabilityRecommendationRequest,
    CapabilityRecommendationResponse,
)
from app.schemas.response import Response, ResponseSchema
from app.services.capability_recommendation_service import (
    CapabilityRecommendationService,
)

router = APIRouter(
    prefix="/capability-recommendations", tags=["capability-recommendations"]
)

service = CapabilityRecommendationService()


@router.post("", response_model=ResponseSchema[CapabilityRecommendationResponse])
async def recommend_capabilities(
    request: CapabilityRecommendationRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = await service.recommend(
        db=db,
        user_id=actor.user_id,
        query=request.query,
        limit=request.limit,
    )
    return Response.success(data=result, message="Capability recommendations retrieved")
