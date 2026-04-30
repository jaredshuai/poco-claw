import logging
from typing import Protocol

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.deps import require_callback_token
from app.schemas.callback import AgentCallbackRequest, CallbackReceiveResponse
from app.schemas.response import Response, ResponseSchema
from app.services.callback_service import CallbackService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/callback", tags=["callback"])


class CallbackApiService(Protocol):
    async def process_callback(
        self, callback: AgentCallbackRequest
    ) -> CallbackReceiveResponse: ...


callback_service: CallbackApiService | None = None


def get_callback_service() -> CallbackApiService:
    global callback_service
    if callback_service is None:
        callback_service = CallbackService()
    return callback_service


@router.post("", response_model=ResponseSchema[CallbackReceiveResponse])
async def receive_callback(
    callback: AgentCallbackRequest,
    _: None = Depends(require_callback_token),
    service: CallbackApiService = Depends(get_callback_service),
) -> JSONResponse:
    """Receive callback from Executor and forward to Backend."""
    result = await service.process_callback(callback)
    return Response.success(data=result.model_dump(), message="Callback received")
