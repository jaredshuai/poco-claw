from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db
from app.core.identity import Actor
from app.schemas.mcp_server import (
    McpServerCreateRequest,
    McpServerResponse,
    McpServerUpdateRequest,
)
from app.schemas.response import Response, ResponseSchema
from app.services.mcp_server_service import McpServerService

router = APIRouter(prefix="/mcp-servers", tags=["mcp-servers"])

service = McpServerService()


@router.get("", response_model=ResponseSchema[list[McpServerResponse]])
async def list_mcp_servers(
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.list_servers(db, user_id=actor.user_id)
    return Response.success(data=result, message="MCP servers retrieved")


@router.get("/{server_id}", response_model=ResponseSchema[McpServerResponse])
async def get_mcp_server(
    server_id: int,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.get_server(db, actor.user_id, server_id)
    return Response.success(data=result, message="MCP server retrieved")


@router.post("", response_model=ResponseSchema[McpServerResponse])
async def create_mcp_server(
    request: McpServerCreateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.create_server(db, actor.user_id, request)
    return Response.success(data=result, message="MCP server created")


@router.patch("/{server_id}", response_model=ResponseSchema[McpServerResponse])
async def update_mcp_server(
    server_id: int,
    request: McpServerUpdateRequest,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.update_server(db, actor.user_id, server_id, request)
    return Response.success(data=result, message="MCP server updated")


@router.delete("/{server_id}", response_model=ResponseSchema[dict])
async def delete_mcp_server(
    server_id: int,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    service.delete_server(db, actor.user_id, server_id)
    return Response.success(data={"id": server_id}, message="MCP server deleted")
