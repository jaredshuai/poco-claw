from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_internal_actor
from app.core.identity import Actor
from app.schemas.response import Response, ResponseSchema
from app.schemas.skill_config import SkillConfigResolveRequest
from app.services.skill_config_service import SkillConfigService

router = APIRouter(prefix="/internal", tags=["internal"])

service = SkillConfigService()


@router.post(
    "/skill-config/resolve",
    response_model=ResponseSchema[dict],
)
async def resolve_skill_config(
    request: SkillConfigResolveRequest,
    actor: Actor = Depends(get_internal_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    resolved = service.resolve_user_skill_files(
        db=db, user_id=actor.user_id, skill_ids=request.skill_ids
    )
    return Response.success(data=resolved, message="Skill config resolved")
