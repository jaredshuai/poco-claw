import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.models.skill_import_job import SkillImportJob
from app.repositories.skill_import_job_repository import SkillImportJobRepository
from app.schemas.skill_import import (
    SkillImportCommitEnqueueResponse,
    SkillImportCommitRequest,
    SkillImportCommitResponse,
    SkillImportJobResponse,
)
from app.services.clock import Clock, SystemClock
from app.services.skill_import_service import SkillImportService

logger = logging.getLogger(__name__)


class SkillImportJobService:
    def __init__(
        self,
        import_service: SkillImportService | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.import_service = import_service or SkillImportService()
        self._clock = clock or SystemClock()

    def enqueue_commit(
        self,
        db: Session,
        *,
        user_id: str,
        request: SkillImportCommitRequest,
    ) -> SkillImportCommitEnqueueResponse:
        selections: list[dict[str, Any]] = [
            selection.model_dump() for selection in request.selections
        ]
        job = SkillImportJobRepository.create(
            db,
            user_id=user_id,
            archive_key=request.archive_key,
            selections=selections,
        )
        db.commit()
        db.refresh(job)
        return SkillImportCommitEnqueueResponse(job_id=job.id, status=job.status)

    def get_job(
        self,
        db: Session,
        *,
        user_id: str,
        job_id: uuid.UUID,
    ) -> SkillImportJobResponse:
        job = SkillImportJobRepository.get_by_id(db, job_id)
        if job is None:
            raise AppException(
                error_code=ErrorCode.NOT_FOUND,
                message="Skill import job not found",
            )
        if job.user_id != user_id:
            raise AppException(
                error_code=ErrorCode.FORBIDDEN,
                message="Skill import job does not belong to the user",
            )
        return self._to_schema(job)

    def process_commit_job(self, job_id: uuid.UUID) -> None:
        """Run a skill import commit job in the background."""

        db = SessionLocal()
        job: SkillImportJob | None = None
        try:
            job = SkillImportJobRepository.get_by_id(db, job_id)
            if job is None:
                return
            if job.status not in {"queued", "running"}:
                return

            job_ref = job
            job.status = "running"
            job.progress = 0
            job.started_at = self._clock.now_utc()
            job.error = None
            db.commit()

            request = SkillImportCommitRequest(
                archive_key=job.archive_key,
                selections=job.selections,
            )

            def on_progress(processed: int, total: int) -> None:
                if total <= 0:
                    return
                # Persist coarse progress so the UI can poll.
                job_ref.progress = min(99, int(processed * 100 / total))
                db.commit()

            result = self.import_service.commit(
                db,
                user_id=job.user_id,
                request=request,
                on_progress=on_progress,
            )

            self._mark_success(db, job, result)
        except Exception as exc:
            logger.exception("skill_import_job_failed", extra={"job_id": str(job_id)})
            if job is not None:
                db.rollback()
                self._mark_failed(db, job, str(exc))
        finally:
            db.close()

    def _mark_success(
        self,
        db: Session,
        job: SkillImportJob,
        result: SkillImportCommitResponse,
    ) -> None:
        job.status = "success"
        job.progress = 100
        job.result = result.model_dump()
        job.error = None
        job.finished_at = self._clock.now_utc()
        db.commit()

    def _mark_failed(self, db: Session, job: SkillImportJob, error: str) -> None:
        job.status = "failed"
        job.error = error
        job.finished_at = self._clock.now_utc()
        db.commit()

    @staticmethod
    def _to_schema(job: SkillImportJob) -> SkillImportJobResponse:
        result = (
            SkillImportCommitResponse.model_validate(job.result)
            if isinstance(job.result, dict)
            else None
        )
        return SkillImportJobResponse(
            job_id=job.id,
            status=job.status,
            progress=int(job.progress or 0),
            result=result,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
