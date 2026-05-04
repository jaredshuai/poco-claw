from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_internal_actor
from app.core.identity import Actor
from app.schemas.plugin_config import PluginConfigResolveRequest
from app.schemas.response import Response, ResponseSchema
from app.services.plugin_config_service import PluginConfigService

router = APIRouter(prefix="/internal", tags=["internal"])

service = PluginConfigService()


@router.post(
    "/plugin-config/resolve",
    response_model=ResponseSchema[dict],
)
async def resolve_plugin_config(
    request: PluginConfigResolveRequest,
    actor: Actor = Depends(get_internal_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    resolved = service.resolve_user_plugin_files(
        db=db, user_id=actor.user_id, plugin_ids=request.plugin_ids
    )
    return Response.success(data=resolved, message="Plugin config resolved")
