import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import (
    get_db,
    get_user_id_by_session_id,
    require_executor_manager,
    require_internal_token,
)
from app.schemas.memory import (
    InternalMemoryCreateRequest,
    InternalMemorySearchRequest,
    InternalMemoryUpdateRequest,
    MemoryCreateJobEnqueueResponse,
    MemoryCreateJobResponse,
    MemoryCreateRequest,
    MemorySearchRequest,
)
from app.schemas.response import Response, ResponseSchema
from app.services.memory_create_job_service import MemoryCreateJobService
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/internal", tags=["internal"])

memory_service = MemoryService()
memory_create_job_service = MemoryCreateJobService(memory_service=memory_service)


@router.post("/memories", response_model=ResponseSchema[MemoryCreateJobEnqueueResponse])
async def create_memories_internal(
    request: InternalMemoryCreateRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_executor_manager),
    user_id: str = Depends(get_user_id_by_session_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    memory_request = MemoryCreateRequest(
        messages=request.messages,
        metadata=request.metadata,
    )
    result = memory_create_job_service.enqueue_create(
        db,
        user_id=user_id,
        request=memory_request,
    )
    background_tasks.add_task(
        memory_create_job_service.process_create_job,
        result.job_id,
    )
    return Response.success(
        data=result, message="Memory create job queued successfully"
    )


@router.get(
    "/memories/jobs/{job_id:uuid}",
    response_model=ResponseSchema[MemoryCreateJobResponse],
)
async def get_memory_create_job_internal(
    job_id: uuid.UUID,
    _token: None = Depends(require_internal_token),
    user_id: str = Depends(get_user_id_by_session_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = memory_create_job_service.get_job(
        db,
        user_id=user_id,
        job_id=job_id,
    )
    return Response.success(
        data=result, message="Memory create job retrieved successfully"
    )


@router.get("/memories", response_model=ResponseSchema[Any])
async def list_memories_internal(
    _: None = Depends(require_internal_token),
    user_id: str = Depends(get_user_id_by_session_id),
) -> JSONResponse:
    result = memory_service.list_memories(
        user_id=user_id,
    )
    return Response.success(data=result, message="Memories retrieved successfully")


@router.post("/memories/search", response_model=ResponseSchema[Any])
async def search_memories_internal(
    request: InternalMemorySearchRequest,
    _: None = Depends(require_internal_token),
    user_id: str = Depends(get_user_id_by_session_id),
) -> JSONResponse:
    search_request = MemorySearchRequest(
        query=request.query,
        filters=request.filters,
    )
    result = memory_service.search_memories(user_id=user_id, request=search_request)
    return Response.success(data=result, message="Memories searched successfully")


@router.get("/memories/{memory_id}", response_model=ResponseSchema[Any])
async def get_memory_internal(
    memory_id: str,
    _token: None = Depends(require_internal_token),
    user_id: str = Depends(get_user_id_by_session_id),
) -> JSONResponse:
    result = memory_service.get_memory(memory_id=memory_id, user_id=user_id)
    return Response.success(data=result, message="Memory retrieved successfully")


@router.put("/memories/{memory_id}", response_model=ResponseSchema[Any])
async def update_memory_internal(
    memory_id: str,
    request: InternalMemoryUpdateRequest,
    _token: None = Depends(require_executor_manager),
    user_id: str = Depends(get_user_id_by_session_id),
) -> JSONResponse:
    result = memory_service.update_memory(
        memory_id=memory_id,
        user_id=user_id,
        text=request.text,
    )
    return Response.success(data=result, message="Memory updated successfully")


@router.get("/memories/{memory_id}/history", response_model=ResponseSchema[Any])
async def get_memory_history_internal(
    memory_id: str,
    _token: None = Depends(require_internal_token),
    user_id: str = Depends(get_user_id_by_session_id),
) -> JSONResponse:
    result = memory_service.get_memory_history(
        memory_id=memory_id,
        user_id=user_id,
    )
    return Response.success(
        data=result, message="Memory history retrieved successfully"
    )


@router.delete("/memories/{memory_id}", response_model=ResponseSchema[dict[str, str]])
async def delete_memory_internal(
    memory_id: str,
    _token: None = Depends(require_executor_manager),
    user_id: str = Depends(get_user_id_by_session_id),
) -> JSONResponse:
    memory_service.delete_memory(memory_id=memory_id, user_id=user_id)
    return Response.success(
        data={"id": memory_id}, message="Memory deleted successfully"
    )


@router.delete("/memories", response_model=ResponseSchema[dict[str, bool]])
async def delete_all_memories_internal(
    _: None = Depends(require_executor_manager),
    user_id: str = Depends(get_user_id_by_session_id),
) -> JSONResponse:
    memory_service.delete_all_memories(
        user_id=user_id,
    )
    return Response.success(
        data={"deleted": True},
        message="All relevant memories deleted successfully",
    )
