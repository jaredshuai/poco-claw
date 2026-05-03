import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db
from app.core.identity import Actor
from app.schemas.response import Response, ResponseSchema
from app.schemas.search import GlobalSearchResponse
from app.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["search"])

search_service = SearchService()


@router.get("", response_model=ResponseSchema[GlobalSearchResponse])
async def global_search(
    q: str = Query(default="", max_length=200),
    limit_tasks: int = Query(default=10, ge=0, le=20),
    limit_projects: int = Query(default=5, ge=0, le=20),
    limit_messages: int = Query(default=10, ge=0, le=20),
    project_id: uuid.UUID | None = Query(default=None),
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = search_service.search(
        db,
        user_id=actor.user_id,
        query=q,
        limit_tasks=limit_tasks,
        limit_projects=limit_projects,
        limit_messages=limit_messages,
        project_id=project_id,
    )
    return Response.success(data=result, message="Search completed successfully")
