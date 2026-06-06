from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_executor_manager
from app.schemas.response import Response, ResponseSchema
from app.schemas.scheduled_task import (
    ScheduledTaskDispatchRequest,
    ScheduledTaskDispatchResponse,
)
from app.services.scheduled_task_service import ScheduledTaskService

router = APIRouter(prefix="/internal", tags=["internal"])

scheduled_task_service = ScheduledTaskService()


@router.post(
    "/scheduled-tasks/dispatch-due",
    response_model=ResponseSchema[ScheduledTaskDispatchResponse],
)
async def dispatch_due_scheduled_tasks(
    request: ScheduledTaskDispatchRequest,
    _: None = Depends(require_executor_manager),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = scheduled_task_service.dispatch_due(db, limit=request.limit)
    return Response.success(
        data=result.model_dump(), message="Scheduled tasks dispatched"
    )
