from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_internal_actor, require_executor_manager
from app.core.identity import Actor
from app.schemas.response import Response, ResponseSchema
from app.schemas.slash_command_config import SlashCommandResolveRequest
from app.services.slash_command_config_service import SlashCommandConfigService

router = APIRouter(prefix="/internal", tags=["internal"])

service = SlashCommandConfigService()


@router.post(
    "/slash-commands/resolve",
    response_model=ResponseSchema[dict[str, str]],
)
async def resolve_slash_commands(
    request: SlashCommandResolveRequest,
    _: None = Depends(require_executor_manager),
    actor: Actor = Depends(get_internal_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    resolved = service.resolve_user_commands(
        db,
        user_id=actor.user_id,
        names=request.names,
        skill_names=request.skill_names,
    )
    return Response.success(data=resolved, message="Slash commands resolved")
