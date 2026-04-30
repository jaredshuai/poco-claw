from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from typing import Any, Protocol

from app.core.deps import require_callback_token
from app.schemas.response import Response, ResponseSchema
from app.schemas.user_input_request import (
    UserInputRequestCreateRequest,
    UserInputRequestResponse,
)
from app.services.backend_client import BackendClient

router = APIRouter(prefix="/user-input-requests", tags=["user-input-requests"])


class UserInputRequestsBackendClient(Protocol):
    async def create_user_input_request(self, payload: dict[str, Any]) -> Any: ...

    async def get_user_input_request(self, request_id: str) -> Any: ...


backend_client: BackendClient | None = None


def get_backend_client() -> UserInputRequestsBackendClient:
    global backend_client
    if backend_client is None:
        backend_client = BackendClient()
    return backend_client


@router.post("", response_model=ResponseSchema[UserInputRequestResponse])
async def create_user_input_request(
    request: UserInputRequestCreateRequest,
    _: None = Depends(require_callback_token),
    backend: UserInputRequestsBackendClient = Depends(get_backend_client),
) -> JSONResponse:
    result = await backend.create_user_input_request(request.model_dump())
    return Response.success(data=result, message="User input request created")


@router.get("/{request_id}", response_model=ResponseSchema[UserInputRequestResponse])
async def get_user_input_request(
    request_id: str,
    _: None = Depends(require_callback_token),
    backend: UserInputRequestsBackendClient = Depends(get_backend_client),
) -> JSONResponse:
    result = await backend.get_user_input_request(request_id)
    return Response.success(data=result, message="User input request retrieved")
