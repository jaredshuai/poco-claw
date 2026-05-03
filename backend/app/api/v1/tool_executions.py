import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db, get_policy_engine
from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.identity import Actor
from app.core.policy import PolicyEngine
from app.schemas.response import Response, ResponseSchema
from app.schemas.tool_execution import ToolExecutionResponse
from app.services.session_service import SessionService
from app.services.tool_execution_service import ToolExecutionService

router = APIRouter(prefix="/tool-executions", tags=["tool-executions"])

tool_execution_service = ToolExecutionService()
session_service = SessionService()


@router.get("/{execution_id}", response_model=ResponseSchema[ToolExecutionResponse])
async def get_tool_execution(
    execution_id: uuid.UUID,
    actor: Actor = Depends(get_current_actor),
    policy_engine: PolicyEngine = Depends(get_policy_engine),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Gets a tool execution by ID."""
    execution = tool_execution_service.get_tool_execution(db, execution_id)
    db_session = session_service.get_session(db, execution.session_id)
    decision = policy_engine.can_access_user_resource(actor, db_session.user_id)
    if not decision.allowed:
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="Tool execution does not belong to the user",
        )
    return Response.success(
        data=ToolExecutionResponse.model_validate(execution),
        message="Tool execution retrieved successfully",
    )
