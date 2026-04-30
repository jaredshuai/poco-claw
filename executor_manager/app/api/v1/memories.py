from typing import Any, Protocol

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.schemas.memory import (
    MemoryCreateJobEnqueueResponse,
    MemoryCreateJobResponse,
    MemoryCreateRequest,
    MemorySearchRequest,
    MemoryUpdateRequest,
)
from app.schemas.response import Response, ResponseSchema
from app.services.backend_client import BackendClient

router = APIRouter(prefix="/memories", tags=["memories"])


class MemoriesBackendClient(Protocol):
    async def create_memory(self, session_id: str, payload: dict[str, Any]) -> Any: ...

    async def get_memory_create_job(self, *, session_id: str, job_id: str) -> Any: ...

    async def list_memories(self, *, session_id: str) -> Any: ...

    async def search_memories(
        self, session_id: str, payload: dict[str, Any]
    ) -> Any: ...

    async def get_memory(self, *, session_id: str, memory_id: str) -> Any: ...

    async def update_memory(
        self, *, session_id: str, memory_id: str, payload: dict[str, Any]
    ) -> Any: ...

    async def get_memory_history(self, *, session_id: str, memory_id: str) -> Any: ...

    async def delete_memory(self, *, session_id: str, memory_id: str) -> Any: ...

    async def delete_all_memories(self, *, session_id: str) -> Any: ...


backend_client: BackendClient | None = None


def get_backend_client() -> MemoriesBackendClient:
    global backend_client
    if backend_client is None:
        backend_client = BackendClient()
    return backend_client


@router.post("", response_model=ResponseSchema[MemoryCreateJobEnqueueResponse])
async def create_memories(
    request: MemoryCreateRequest,
    backend: MemoriesBackendClient = Depends(get_backend_client),
) -> JSONResponse:
    payload = request.model_dump(mode="json", exclude={"session_id"})
    result = await backend.create_memory(request.session_id, payload)
    return Response.success(
        data=result, message="Memory create job queued successfully"
    )


@router.get("/jobs/{job_id}", response_model=ResponseSchema[MemoryCreateJobResponse])
async def get_memory_create_job(
    job_id: str,
    session_id: str = Query(...),
    backend: MemoriesBackendClient = Depends(get_backend_client),
) -> JSONResponse:
    result = await backend.get_memory_create_job(
        session_id=session_id,
        job_id=job_id,
    )
    return Response.success(
        data=result, message="Memory create job retrieved successfully"
    )


@router.get("", response_model=ResponseSchema[Any])
async def list_memories(
    session_id: str = Query(...),
    backend: MemoriesBackendClient = Depends(get_backend_client),
) -> JSONResponse:
    result = await backend.list_memories(session_id=session_id)
    return Response.success(data=result, message="Memories retrieved successfully")


@router.post("/search", response_model=ResponseSchema[Any])
async def search_memories(
    request: MemorySearchRequest,
    backend: MemoriesBackendClient = Depends(get_backend_client),
) -> JSONResponse:
    payload = request.model_dump(mode="json", exclude={"session_id"})
    result = await backend.search_memories(request.session_id, payload)
    return Response.success(data=result, message="Memories searched successfully")


@router.get("/{memory_id}", response_model=ResponseSchema[Any])
async def get_memory(
    memory_id: str,
    session_id: str = Query(...),
    backend: MemoriesBackendClient = Depends(get_backend_client),
) -> JSONResponse:
    result = await backend.get_memory(
        session_id=session_id,
        memory_id=memory_id,
    )
    return Response.success(data=result, message="Memory retrieved successfully")


@router.put("/{memory_id}", response_model=ResponseSchema[Any])
async def update_memory(
    memory_id: str,
    request: MemoryUpdateRequest,
    backend: MemoriesBackendClient = Depends(get_backend_client),
) -> JSONResponse:
    payload = request.model_dump(mode="json", exclude={"session_id"})
    result = await backend.update_memory(
        session_id=request.session_id,
        memory_id=memory_id,
        payload=payload,
    )
    return Response.success(data=result, message="Memory updated successfully")


@router.get("/{memory_id}/history", response_model=ResponseSchema[Any])
async def get_memory_history(
    memory_id: str,
    session_id: str = Query(...),
    backend: MemoriesBackendClient = Depends(get_backend_client),
) -> JSONResponse:
    result = await backend.get_memory_history(
        session_id=session_id,
        memory_id=memory_id,
    )
    return Response.success(
        data=result,
        message="Memory history retrieved successfully",
    )


@router.delete("/{memory_id}", response_model=ResponseSchema[dict[str, str]])
async def delete_memory(
    memory_id: str,
    session_id: str = Query(...),
    backend: MemoriesBackendClient = Depends(get_backend_client),
) -> JSONResponse:
    result = await backend.delete_memory(
        session_id=session_id,
        memory_id=memory_id,
    )
    return Response.success(data=result, message="Memory deleted successfully")


@router.delete("", response_model=ResponseSchema[dict[str, bool]])
async def delete_all_memories(
    session_id: str = Query(...),
    backend: MemoriesBackendClient = Depends(get_backend_client),
) -> JSONResponse:
    result = await backend.delete_all_memories(session_id=session_id)
    return Response.success(
        data=result,
        message="All relevant memories deleted successfully",
    )
