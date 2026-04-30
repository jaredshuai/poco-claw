from typing import Any, Protocol

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.schemas.response import Response, ResponseSchema
from app.schemas.task import (
    ContainerDeleteRequest,
    ContainerStatsResponse,
    TaskCancelRequest,
)
from app.scheduler.task_dispatcher import TaskDispatcher

router = APIRouter(prefix="/executor", tags=["executor"])


class ExecutorContainerPool(Protocol):
    async def cancel_task(self, session_id: str) -> None: ...

    async def delete_container(self, container_id: str) -> None: ...

    def get_container_stats(self) -> Any: ...


def get_container_pool() -> ExecutorContainerPool:
    return TaskDispatcher.get_container_pool()


@router.post("/cancel", response_model=ResponseSchema[dict])
async def cancel_task(
    request: TaskCancelRequest,
    container_pool: ExecutorContainerPool = Depends(get_container_pool),
) -> JSONResponse:
    """Cancel running task and delete container.

    Args:
        request: Cancel task request

    Returns:
        Success response with session_id and status
    """
    await container_pool.cancel_task(request.session_id)

    return Response.success(
        data={"session_id": request.session_id, "status": "canceled"},
        message="Task canceled successfully",
    )


@router.post("/delete", response_model=ResponseSchema[dict])
async def delete_container(
    request: ContainerDeleteRequest,
    container_pool: ExecutorContainerPool = Depends(get_container_pool),
) -> JSONResponse:
    """Delete persistent container explicitly.

    Args:
        request: Delete container request

    Returns:
        Success response with container_id and status
    """
    await container_pool.delete_container(request.container_id)

    return Response.success(
        data={"container_id": request.container_id, "status": "deleted"},
        message="Container deleted successfully",
    )


@router.get("/load", response_model=ResponseSchema[ContainerStatsResponse])
async def get_executor_load(
    container_pool: ExecutorContainerPool = Depends(get_container_pool),
) -> JSONResponse:
    """Get executor container load statistics.

    Returns:
        Container statistics response
    """
    stats = container_pool.get_container_stats()

    return Response.success(data=stats)
