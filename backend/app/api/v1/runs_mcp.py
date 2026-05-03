import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.deps import get_current_actor, get_db, get_policy_engine
from app.core.identity import Actor
from app.core.policy import PolicyEngine
from app.schemas.response import Response
from app.services.mcp_connection_service import McpConnectionService
from app.services.run_service import RunService
from app.services.session_service import SessionService

router = APIRouter(prefix="/runs", tags=["runs-mcp"])

run_service = RunService()
session_service = SessionService()


def _ensure_run_belongs_to_user(
    db: Session, run_id: uuid.UUID, actor: Actor, policy_engine: PolicyEngine
) -> None:
    result = run_service.get_run(db, run_id)
    db_session = session_service.get_session(db, result.session_id)
    decision = policy_engine.can_access_user_resource(actor, db_session.user_id)
    if not decision.allowed:
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="Run does not belong to the user",
        )


@router.get("/{run_id}/mcp-connections")
def list_mcp_connections(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_current_actor),
    policy_engine: PolicyEngine = Depends(get_policy_engine),
) -> JSONResponse:
    _ensure_run_belongs_to_user(db, run_id, actor, policy_engine)
    service = McpConnectionService()
    connections = service.list_run_connections(db, run_id)
    return Response.success(data=[c.model_dump(mode="json") for c in connections])


@router.get("/{run_id}/mcp-connection-events")
def list_mcp_connection_events(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_current_actor),
    policy_engine: PolicyEngine = Depends(get_policy_engine),
) -> JSONResponse:
    _ensure_run_belongs_to_user(db, run_id, actor, policy_engine)
    from app.models.agent_run_mcp_connection_event import AgentRunMcpConnectionEvent

    events = (
        db.query(AgentRunMcpConnectionEvent)
        .filter(AgentRunMcpConnectionEvent.run_id == run_id)
        .order_by(AgentRunMcpConnectionEvent.created_at.asc())
        .all()
    )
    return Response.success(
        data=[
            {
                "id": str(e.id),
                "connection_id": str(e.connection_id),
                "run_id": str(e.run_id),
                "from_state": e.from_state,
                "to_state": e.to_state,
                "event_source": e.event_source,
                "error_message": e.error_message,
                "metadata": e.metadata_,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ]
    )


@router.get("/{run_id}/permission-audit")
def list_permission_audit(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_current_actor),
    policy_engine: PolicyEngine = Depends(get_policy_engine),
) -> JSONResponse:
    _ensure_run_belongs_to_user(db, run_id, actor, policy_engine)
    from app.models.permission_audit_event import PermissionAuditEvent

    events = (
        db.query(PermissionAuditEvent)
        .filter(PermissionAuditEvent.run_id == run_id)
        .order_by(PermissionAuditEvent.created_at.asc())
        .all()
    )
    return Response.success(
        data=[
            {
                "id": str(e.id),
                "run_id": str(e.run_id),
                "session_id": str(e.session_id),
                "tool_name": e.tool_name,
                "tool_input": e.tool_input,
                "policy_action": e.policy_action,
                "policy_rule_id": e.policy_rule_id,
                "policy_reason": e.policy_reason,
                "audit_mode": e.audit_mode,
                "context": e.context,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ]
    )
