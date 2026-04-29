import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.response import Response, ResponseSchema
from app.schemas.task import (
    SessionStatusResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskStatusResponse,
)
from app.services.task_service import TaskService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])
task_service: TaskService | None = None


def get_task_service() -> TaskService:
    global task_service
    if task_service is None:
        task_service = TaskService()
    return task_service


@router.post("", response_model=ResponseSchema[TaskCreateResponse])
async def create_task(request: TaskCreateRequest) -> JSONResponse:
    """Create a task and schedule it for execution. If session_id is provided, continues existing conversation."""
    service = get_task_service()
    result = await service.create_task(
        user_id=request.user_id,
        prompt=request.prompt,
        config=request.config.model_dump(),
        session_id=request.session_id,
    )
    return Response.success(data=result.model_dump(), message="Task created")


@router.get("/{task_id}", response_model=ResponseSchema[TaskStatusResponse])
async def get_task_status(task_id: str) -> JSONResponse:
    """Get task status."""
    service = get_task_service()
    result = service.get_task_status(task_id)
    return Response.success(data=result.model_dump())


@router.get(
    "/session/{session_id}", response_model=ResponseSchema[SessionStatusResponse]
)
async def get_task_status_by_session(session_id: str) -> JSONResponse:
    """Get task status by session ID."""
    service = get_task_service()
    result = await service.get_session_status(session_id)
    return Response.success(data=result.model_dump())
