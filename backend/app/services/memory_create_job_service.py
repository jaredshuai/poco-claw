import logging
import uuid
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.models.memory_create_job import MemoryCreateJob
from app.repositories.memory_create_job_repository import MemoryCreateJobRepository
from app.schemas.memory import (
    MemoryCreateJobEnqueueResponse,
    MemoryCreateJobResponse,
    MemoryCreateRequest,
)
from app.services.clock import Clock, SystemClock
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)


class MemoryCreateJobService:
    def __init__(
        self,
        memory_service: MemoryService | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.memory_service = memory_service or MemoryService()
        self._clock = clock or SystemClock()

    def enqueue_create(
        self,
        db: Session,
        *,
        user_id: str,
        request: MemoryCreateRequest,
    ) -> MemoryCreateJobEnqueueResponse:
        messages: list[dict[str, Any]] = [
            message.model_dump(mode="json") for message in request.messages
        ]
        metadata: dict[str, Any] | None = (
            request.metadata.copy() if request.metadata is not None else None
        )
        job = MemoryCreateJobRepository.create(
            db,
            user_id=user_id,
            messages=messages,
            run_id=request.run_id,
            metadata=metadata,
        )
        db.commit()
        db.refresh(job)
        return MemoryCreateJobEnqueueResponse(job_id=job.id, status=job.status)

    def get_job(
        self,
        db: Session,
        *,
        user_id: str,
        job_id: uuid.UUID,
    ) -> MemoryCreateJobResponse:
        job = MemoryCreateJobRepository.get_by_id(db, job_id)
        if job is None:
            raise AppException(
                error_code=ErrorCode.NOT_FOUND,
                message="Memory create job not found",
            )
        if job.user_id != user_id:
            raise AppException(
                error_code=ErrorCode.FORBIDDEN,
                message="Memory create job does not belong to the user",
            )
        return self._to_schema(job)

    def get_active_job(
        self,
        db: Session,
        *,
        user_id: str,
    ) -> MemoryCreateJobResponse | None:
        job = MemoryCreateJobRepository.get_latest_active_by_user(
            db,
            user_id=user_id,
        )
        if job is None:
            return None
        return self._to_schema(job)

    def process_create_job(self, job_id: uuid.UUID) -> None:
        db = SessionLocal()
        job: MemoryCreateJob | None = None
        try:
            job = MemoryCreateJobRepository.get_by_id(db, job_id)
            if job is None:
                return
            if job.status not in {"queued", "running"}:
                return

            job.status = "running"
            job.progress = 0
            job.started_at = self._clock.now_utc()
            job.error = None
            db.commit()

            request = MemoryCreateRequest(
                messages=job.messages,
                run_id=job.run_id,
                metadata=job.request_metadata,
            )
            result = self.memory_service.create_memories(
                user_id=job.user_id, request=request
            )
            self._mark_success(db, job, result)
        except Exception as exc:
            logger.exception("memory_create_job_failed", extra={"job_id": str(job_id)})
            if job is not None:
                db.rollback()
                self._mark_failed(db, job, str(exc))
        finally:
            db.close()

    def _mark_success(
        self,
        db: Session,
        job: MemoryCreateJob,
        result: Any,
    ) -> None:
        job.status = "success"
        job.progress = 100
        job.result = jsonable_encoder(result)
        job.error = None
        job.finished_at = self._clock.now_utc()
        db.commit()

    def _mark_failed(self, db: Session, job: MemoryCreateJob, error: str) -> None:
        job.status = "failed"
        job.error = error
        job.finished_at = self._clock.now_utc()
        db.commit()

    @staticmethod
    def _to_schema(job: MemoryCreateJob) -> MemoryCreateJobResponse:
        return MemoryCreateJobResponse(
            job_id=job.id,
            status=job.status,
            progress=int(job.progress or 0),
            result=job.result,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
