from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_internal_actor, require_executor_manager
from app.core.identity import Actor
from app.schemas.response import Response, ResponseSchema
from app.services.execution_settings_service import ExecutionSettingsService

router = APIRouter(prefix="/internal", tags=["internal"])

service = ExecutionSettingsService()


@router.get(
    "/execution-settings/resolve",
    response_model=ResponseSchema[dict],
)
async def resolve_execution_settings(
    _: None = Depends(require_executor_manager),
    actor: Actor = Depends(get_internal_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.resolve_for_execution(db, actor.user_id)
    return Response.success(data=result, message="Execution settings resolved")
