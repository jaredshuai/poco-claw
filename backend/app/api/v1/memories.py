import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db, require_internal_token
from app.core.identity import Actor
from app.schemas.memory import (
    MemoryCreateJobEnqueueResponse,
    MemoryCreateJobResponse,
    MemoryConfigureRequest,
    MemoryCreateRequest,
    MemorySearchRequest,
    MemoryUpdateRequest,
)
from app.schemas.response import Response, ResponseSchema
from app.services.memory_create_job_service import MemoryCreateJobService
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/memories", tags=["memories"])

memory_service = MemoryService()
memory_create_job_service = MemoryCreateJobService(memory_service=memory_service)


@router.post("/configure", response_model=ResponseSchema[dict[str, bool]])
async def configure_memory(
    request: MemoryConfigureRequest,
    _: None = Depends(require_internal_token),
) -> JSONResponse:
    memory_service.configure(enabled=request.enabled, config=request.config)
    return Response.success(
        data={"configured": True, "enabled": memory_service.is_enabled()},
        message="Memory configuration updated",
    )


@router.post("", response_model=ResponseSchema[MemoryCreateJobEnqueueResponse])
async def create_memories(
    request: MemoryCreateRequest,
    background_tasks: BackgroundTasks,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = memory_create_job_service.enqueue_create(
        db,
        user_id=actor.user_id,
        request=request,
    )
    background_tasks.add_task(
        memory_create_job_service.process_create_job,
        result.job_id,
    )
    return Response.success(
        data=result, message="Memory create job queued successfully"
    )


@router.get(
    "/jobs/active",
    response_model=ResponseSchema[MemoryCreateJobResponse | None],
)
async def get_active_memory_create_job(
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = memory_create_job_service.get_active_job(
        db,
        user_id=actor.user_id,
    )
    return Response.success(
        data=result, message="Active memory create job retrieved successfully"
    )


@router.get(
    "/jobs/{job_id:uuid}",
    response_model=ResponseSchema[MemoryCreateJobResponse],
)
async def get_memory_create_job(
    job_id: uuid.UUID,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = memory_create_job_service.get_job(
        db,
        user_id=actor.user_id,
        job_id=job_id,
    )
    return Response.success(
        data=result, message="Memory create job retrieved successfully"
    )


@router.get("", response_model=ResponseSchema[Any])
async def list_memories(
    run_id: str | None = None,
    actor: Actor = Depends(get_current_actor),
) -> JSONResponse:
    result = memory_service.list_memories(
        user_id=actor.user_id,
        run_id=run_id,
    )
    return Response.success(data=result, message="Memories retrieved successfully")


@router.post("/search", response_model=ResponseSchema[Any])
async def search_memories(
    request: MemorySearchRequest,
    actor: Actor = Depends(get_current_actor),
) -> JSONResponse:
    result = memory_service.search_memories(user_id=actor.user_id, request=request)
    return Response.success(data=result, message="Memories searched successfully")


@router.get("/{memory_id}", response_model=ResponseSchema[Any])
async def get_memory(memory_id: str) -> JSONResponse:
    result = memory_service.get_memory(memory_id)
    return Response.success(data=result, message="Memory retrieved successfully")


@router.put("/{memory_id}", response_model=ResponseSchema[Any])
async def update_memory(
    memory_id: str,
    request: MemoryUpdateRequest,
) -> JSONResponse:
    result = memory_service.update_memory(memory_id=memory_id, text=request.text)
    return Response.success(data=result, message="Memory updated successfully")


@router.get("/{memory_id}/history", response_model=ResponseSchema[Any])
async def get_memory_history(memory_id: str) -> JSONResponse:
    result = memory_service.get_memory_history(memory_id=memory_id)
    return Response.success(
        data=result, message="Memory history retrieved successfully"
    )


@router.delete("/{memory_id}", response_model=ResponseSchema[dict[str, str]])
async def delete_memory(memory_id: str) -> JSONResponse:
    memory_service.delete_memory(memory_id=memory_id)
    return Response.success(
        data={"id": memory_id}, message="Memory deleted successfully"
    )


@router.delete("", response_model=ResponseSchema[dict[str, bool]])
async def delete_all_memories(
    run_id: str | None = None,
    actor: Actor = Depends(get_current_actor),
) -> JSONResponse:
    memory_service.delete_all_memories(
        user_id=actor.user_id,
        run_id=run_id,
    )
    return Response.success(
        data={"deleted": True},
        message="All relevant memories deleted successfully",
    )


@router.post("/reset", response_model=ResponseSchema[dict[str, bool]])
async def reset_memories(
    _: None = Depends(require_internal_token),
) -> JSONResponse:
    memory_service.reset()
    return Response.success(
        data={"reset": True}, message="All memories reset successfully"
    )
