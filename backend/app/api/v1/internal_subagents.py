from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_internal_actor
from app.core.identity import Actor
from app.schemas.response import Response, ResponseSchema
from app.schemas.sub_agent import SubAgentResolveRequest, SubAgentResolveResponse
from app.services.sub_agent_service import SubAgentService

router = APIRouter(prefix="/internal", tags=["internal"])

service = SubAgentService()


@router.post(
    "/subagents/resolve",
    response_model=ResponseSchema[SubAgentResolveResponse],
)
async def resolve_subagents(
    request: SubAgentResolveRequest,
    actor: Actor = Depends(get_internal_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    resolved = service.resolve_for_execution(
        db,
        user_id=actor.user_id,
        subagent_ids=request.subagent_ids,
    )
    return Response.success(data=resolved, message="Subagents resolved")
