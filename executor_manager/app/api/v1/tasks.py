from functools import lru_cache
import logging
from typing import Protocol

from fastapi import APIRouter, Depends
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


class TaskApiService(Protocol):
    async def create_task(
        self,
        user_id: str,
        prompt: str,
        config: dict[str, object],
        session_id: str | None = None,
    ) -> TaskCreateResponse: ...

    def get_task_status(self, task_id: str) -> TaskStatusResponse: ...

    async def get_session_status(self, session_id: str) -> SessionStatusResponse: ...


def build_task_service() -> TaskApiService:
    return TaskService()


@lru_cache(maxsize=1)
def get_task_service() -> TaskApiService:
    return build_task_service()


@router.post("", response_model=ResponseSchema[TaskCreateResponse])
async def create_task(
    request: TaskCreateRequest,
    service: TaskApiService = Depends(get_task_service),
) -> JSONResponse:
    """Create a task and schedule it for execution. If session_id is provided, continues existing conversation."""
    result = await service.create_task(
        user_id=request.user_id,
        prompt=request.prompt,
        config=request.config.model_dump(),
        session_id=request.session_id,
    )
    return Response.success(data=result.model_dump(), message="Task created")


@router.get("/{task_id}", response_model=ResponseSchema[TaskStatusResponse])
async def get_task_status(
    task_id: str,
    service: TaskApiService = Depends(get_task_service),
) -> JSONResponse:
    """Get task status."""
    result = service.get_task_status(task_id)
    return Response.success(data=result.model_dump())


@router.get(
    "/session/{session_id}", response_model=ResponseSchema[SessionStatusResponse]
)
async def get_task_status_by_session(
    session_id: str,
    service: TaskApiService = Depends(get_task_service),
) -> JSONResponse:
    """Get task status by session ID."""
    result = await service.get_session_status(session_id)
    return Response.success(data=result.model_dump())
