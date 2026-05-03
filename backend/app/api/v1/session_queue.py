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
from app.schemas.session_queue_item import (
    SessionQueueItemResponse,
    SessionQueueItemUpdateRequest,
)
from app.schemas.task import TaskEnqueueResponse
from app.services.session_queue_service import SessionQueueService
from app.services.session_service import SessionService

router = APIRouter(
    prefix="/sessions/{session_id}/queued-queries", tags=["session-queue"]
)

session_service = SessionService()
session_queue_service = SessionQueueService()


def _get_owned_session(
    db: Session,
    session_id: uuid.UUID,
    actor: Actor,
    policy_engine: PolicyEngine,
):
    db_session = session_service.get_session(db, session_id)
    decision = policy_engine.can_access_user_resource(actor, db_session.user_id)
    if not decision.allowed:
        raise AppException(
            error_code=ErrorCode.FORBIDDEN,
            message="Session does not belong to the user",
        )
    return db_session


@router.get("", response_model=ResponseSchema[list[SessionQueueItemResponse]])
async def list_queued_queries(
    session_id: uuid.UUID,
    actor: Actor = Depends(get_current_actor),
    policy_engine: PolicyEngine = Depends(get_policy_engine),
    db: Session = Depends(get_db),
) -> JSONResponse:
    db_session = _get_owned_session(db, session_id, actor, policy_engine)
    items = session_queue_service.list_item_responses(db, db_session.id)
    return Response.success(data=items, message="Queued queries retrieved successfully")


@router.patch("/{item_id}", response_model=ResponseSchema[SessionQueueItemResponse])
async def update_queued_query(
    session_id: uuid.UUID,
    item_id: uuid.UUID,
    request: SessionQueueItemUpdateRequest,
    actor: Actor = Depends(get_current_actor),
    policy_engine: PolicyEngine = Depends(get_policy_engine),
    db: Session = Depends(get_db),
) -> JSONResponse:
    db_session = _get_owned_session(db, session_id, actor, policy_engine)
    item = session_queue_service.update_item(db, db_session, item_id, request)
    db.commit()
    db.refresh(item)
    return Response.success(
        data=SessionQueueItemResponse.model_validate(item),
        message="Queued query updated successfully",
    )


@router.delete("/{item_id}", response_model=ResponseSchema[SessionQueueItemResponse])
async def delete_queued_query(
    session_id: uuid.UUID,
    item_id: uuid.UUID,
    actor: Actor = Depends(get_current_actor),
    policy_engine: PolicyEngine = Depends(get_policy_engine),
    db: Session = Depends(get_db),
) -> JSONResponse:
    db_session = _get_owned_session(db, session_id, actor, policy_engine)
    item = session_queue_service.cancel_item(db, db_session, item_id)
    db.commit()
    db.refresh(item)
    return Response.success(
        data=SessionQueueItemResponse.model_validate(item),
        message="Queued query deleted successfully",
    )


@router.post("/{item_id}/send-now", response_model=ResponseSchema[TaskEnqueueResponse])
async def send_queued_query_now(
    session_id: uuid.UUID,
    item_id: uuid.UUID,
    actor: Actor = Depends(get_current_actor),
    policy_engine: PolicyEngine = Depends(get_policy_engine),
    db: Session = Depends(get_db),
) -> JSONResponse:
    db_session = _get_owned_session(db, session_id, actor, policy_engine)
    result = session_queue_service.send_now(db, db_session, item_id)
    db.commit()
    return Response.success(data=result, message="Queued query updated successfully")
