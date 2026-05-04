from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db
from app.core.identity import Actor
from app.schemas.response import Response, ResponseSchema
from app.schemas.sub_agent import (
    SubAgentCreateRequest,
    SubAgentResponse,
    SubAgentUpdateRequest,
)
from app.services.sub_agent_service import SubAgentService

router = APIRouter(prefix="/subagents", tags=["subagents"])

service = SubAgentService()


@router.get("", response_model=ResponseSchema[list[SubAgentResponse]])
async def list_subagents(
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.list_subagents(db, user_id=actor.user_id)
    return Response.success(data=result, message="Subagents retrieved")


@router.get("/{subagent_id}", response_model=ResponseSchema[SubAgentResponse])
async def get_subagent(
    subagent_id: int,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.get_subagent(db, user_id=actor.user_id, subagent_id=subagent_id)
    return Response.success(data=result, message="Subagent retrieved")


@router.post("", response_model=ResponseSchema[SubAgentResponse])
async def create_subagent(
    request: SubAgentCreateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.create_subagent(db, user_id=actor.user_id, request=request)
    return Response.success(data=result, message="Subagent created")


@router.patch("/{subagent_id}", response_model=ResponseSchema[SubAgentResponse])
async def update_subagent(
    subagent_id: int,
    request: SubAgentUpdateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.update_subagent(
        db,
        user_id=actor.user_id,
        subagent_id=subagent_id,
        request=request,
    )
    return Response.success(data=result, message="Subagent updated")


@router.delete("/{subagent_id}", response_model=ResponseSchema[dict])
async def delete_subagent(
    subagent_id: int,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    service.delete_subagent(db, user_id=actor.user_id, subagent_id=subagent_id)
    return Response.success(data={"id": subagent_id}, message="Subagent deleted")
