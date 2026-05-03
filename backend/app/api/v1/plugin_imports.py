import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db
from app.core.identity import Actor
from app.schemas.plugin_import import (
    PluginImportCommitEnqueueResponse,
    PluginImportCommitRequest,
    PluginImportDiscoverResponse,
    PluginImportJobResponse,
)
from app.schemas.response import Response, ResponseSchema
from app.services.plugin_import_job_service import PluginImportJobService
from app.services.plugin_import_service import PluginImportService

router = APIRouter(prefix="/plugins/import", tags=["plugins"])

import_service: PluginImportService | None = None
job_service: PluginImportJobService | None = None


def get_import_service() -> PluginImportService:
    global import_service
    if import_service is None:
        import_service = PluginImportService()
    return import_service


def get_job_service() -> PluginImportJobService:
    global job_service
    if job_service is None:
        job_service = PluginImportJobService(import_service=get_import_service())
    return job_service


@router.post(
    "/discover",
    response_model=ResponseSchema[PluginImportDiscoverResponse],
)
def discover_plugin_import(
    file: UploadFile | None = File(default=None),
    github_url: str | None = Form(default=None),
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    service = get_import_service()
    result = service.discover(
        db,
        user_id=actor.user_id,
        file=file,
        github_url=github_url,
    )
    return Response.success(data=result, message="Plugin import discovered")


@router.post(
    "/commit",
    response_model=ResponseSchema[PluginImportCommitEnqueueResponse],
)
def commit_plugin_import(
    request: PluginImportCommitRequest,
    background_tasks: BackgroundTasks,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    service = get_job_service()
    result = service.enqueue_commit(db, user_id=actor.user_id, request=request)
    background_tasks.add_task(service.process_commit_job, result.job_id)
    return Response.success(data=result, message="Plugin import queued")


@router.get(
    "/jobs/{job_id}",
    response_model=ResponseSchema[PluginImportJobResponse],
)
def get_plugin_import_job(
    job_id: uuid.UUID,
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    service = get_job_service()
    result = service.get_job(db, user_id=actor.user_id, job_id=job_id)
    return Response.success(data=result, message="Plugin import job retrieved")
