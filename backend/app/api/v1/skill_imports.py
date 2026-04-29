import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id, get_db
from app.schemas.response import Response, ResponseSchema
from app.schemas.skill_import import (
    SkillImportCommitRequest,
    SkillImportCommitEnqueueResponse,
    SkillImportDiscoverResponse,
    SkillImportJobResponse,
)
from app.services.skill_import_service import SkillImportService
from app.services.skill_import_job_service import SkillImportJobService

router = APIRouter(prefix="/skills/import", tags=["skills"])

import_service: SkillImportService | None = None
job_service: SkillImportJobService | None = None


def get_import_service() -> SkillImportService:
    global import_service
    if import_service is None:
        import_service = SkillImportService()
    return import_service


def get_job_service() -> SkillImportJobService:
    global job_service
    if job_service is None:
        job_service = SkillImportJobService(import_service=get_import_service())
    return job_service


@router.post(
    "/discover",
    response_model=ResponseSchema[SkillImportDiscoverResponse],
)
def discover_skill_import(
    file: UploadFile | None = File(default=None),
    github_url: str | None = Form(default=None),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    service = get_import_service()
    result = service.discover(
        db,
        user_id=user_id,
        file=file,
        github_url=github_url,
    )
    return Response.success(data=result, message="Skill import discovered")


@router.post(
    "/commit",
    response_model=ResponseSchema[SkillImportCommitEnqueueResponse],
)
def commit_skill_import(
    request: SkillImportCommitRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    service = get_job_service()
    result = service.enqueue_commit(db, user_id=user_id, request=request)
    background_tasks.add_task(service.process_commit_job, result.job_id)
    return Response.success(data=result, message="Skill import queued")


@router.get(
    "/jobs/{job_id}",
    response_model=ResponseSchema[SkillImportJobResponse],
)
def get_skill_import_job(
    job_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    service = get_job_service()
    result = service.get_job(db, user_id=user_id, job_id=job_id)
    return Response.success(data=result, message="Skill import job retrieved")
