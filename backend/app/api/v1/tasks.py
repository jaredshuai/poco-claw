from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db
from app.core.identity import Actor
from app.schemas.response import Response, ResponseSchema
from app.schemas.task import TaskEnqueueRequest, TaskEnqueueResponse
from app.services.session_title_service import SessionTitleService
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])

task_service = TaskService()
title_service = SessionTitleService()


@router.post("", response_model=ResponseSchema[TaskEnqueueResponse])
async def enqueue_task(
    request: TaskEnqueueRequest,
    background_tasks: BackgroundTasks,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Enqueue a task (agent run) for execution."""
    result = task_service.enqueue_task(db, actor.user_id, request)
    if request.session_id is None:
        background_tasks.add_task(
            title_service.generate_and_update, result.session_id, request.prompt
        )
    return Response.success(data=result, message="Task enqueued successfully")
