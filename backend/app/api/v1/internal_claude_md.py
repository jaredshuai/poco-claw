from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_internal_actor
from app.core.identity import Actor
from app.schemas.claude_md import ClaudeMdResponse
from app.schemas.response import Response, ResponseSchema
from app.services.claude_md_service import ClaudeMdService

router = APIRouter(prefix="/internal", tags=["internal"])

service = ClaudeMdService()


@router.get("/claude-md", response_model=ResponseSchema[ClaudeMdResponse])
async def get_claude_md_internal(
    actor: Actor = Depends(get_internal_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.get_settings(db, user_id=actor.user_id)
    return Response.success(data=result, message="CLAUDE.md retrieved")
