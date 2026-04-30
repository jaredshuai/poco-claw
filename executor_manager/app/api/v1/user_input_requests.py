from functools import lru_cache
from typing import Any, Protocol

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

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


def build_backend_client() -> UserInputRequestsBackendClient:
    return BackendClient()


@lru_cache(maxsize=1)
def get_backend_client() -> UserInputRequestsBackendClient:
    return build_backend_client()


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
