import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_executor_manager
from app.schemas.callback import AgentCallbackRequest, CallbackResponse
from app.schemas.response import Response, ResponseSchema
from app.services.callback_service import CallbackService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/callback", tags=["callback"])

callback_service = CallbackService()


@router.post("", response_model=ResponseSchema[CallbackResponse])
async def receive_callback(
    callback: AgentCallbackRequest,
    _: None = Depends(require_executor_manager),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Receives executor callback and updates session status."""
    result = callback_service.process_agent_callback(db, callback)
    return Response.success(
        data=result,
        message="Callback processed successfully",
    )


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "callback-receiver"}
