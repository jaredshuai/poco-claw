import re
import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy.orm import Session

from app.models.deliverable_version import DeliverableVersion
from app.repositories.deliverable_repository import DeliverableRepository
from app.repositories.deliverable_version_repository import (
    DeliverableVersionRepository,
)

_DELIVERABLE_EXTENSIONS = {
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".pptx": "pptx",
    ".pdf": "pdf",
}
_TRAILING_SUFFIX_PATTERNS = (
    re.compile(r"([_\-\s]v\d+)$", re.IGNORECASE),
    re.compile(r"(v\d+)$", re.IGNORECASE),
    re.compile(r"([_\-\s]final(?:-\d+)?)$", re.IGNORECASE),
    re.compile(r"([_\-\s]修订版)$"),
    re.compile(r"([_\-\s]最终版)$"),
    re.compile(r"([_\-\s]?\d{8})$"),
    re.compile(r"([_\-\s]?\d{14})$"),
)


def normalize_logical_name(file_name: str) -> str:
    """Normalize a deliverable file name to a logical display name."""
    base_name = PurePosixPath(file_name or "").name
    stem = PurePosixPath(base_name).stem.lower().strip(" _-.")
    if not stem:
        return PurePosixPath(base_name).stem or base_name

    value = stem
    changed = True
    while changed and value:
        changed = False
        for pattern in _TRAILING_SUFFIX_PATTERNS:
            next_value = pattern.sub("", value).strip(" _-.")
            if next_value != value:
                value = next_value
                changed = True
                break

    value = re.sub(r"[_\-\s]+", " ", value).strip()
    return value or (PurePosixPath(base_name).stem or base_name)


@dataclass(slots=True)
class DeliverableCandidate:
    session_id: uuid.UUID
    run_id: uuid.UUID
    source_message_id: int | None
    kind: str
    logical_name: str
    file_path: str
    file_name: str
    confidence: float
    mime_type: str | None = None
    input_refs_json: dict[str, Any] | None = None
    related_tool_execution_ids_json: dict[str, Any] | None = None
    detection_metadata_json: dict[str, Any] | None = None


class DeliverableDetectionService:
    """Rule-based deliverable detection and persistence helpers."""

    @staticmethod
    def is_deliverable_candidate(
        *,
        file_path: str,
        mime_type: str | None = None,
    ) -> bool:
        ext = PurePosixPath(file_path or "").suffix.lower()
        if ext in _DELIVERABLE_EXTENSIONS:
            return True
        return bool(mime_type and mime_type.lower() == "application/pdf")

    @staticmethod
    def should_promote_reference_input(
        *,
        ref_type: str,
        materially_modified: bool,
        presented_as_result: bool,
    ) -> bool:
        return (
            ref_type == "upload"
            and materially_modified
            and presented_as_result
        )

    @staticmethod
    def select_primary_candidates(
        candidates: list[DeliverableCandidate],
    ) -> list[DeliverableCandidate]:
        grouped: dict[tuple[uuid.UUID, str, str], list[DeliverableCandidate]] = {}
        for candidate in candidates:
            key = (candidate.session_id, candidate.kind, candidate.logical_name)
            grouped.setdefault(key, []).append(candidate)

        selected: list[DeliverableCandidate] = []
        for items in grouped.values():
            ranked = sorted(
                items,
                key=lambda item: (item.confidence, item.file_name.lower()),
                reverse=True,
            )
            primary = ranked[0]
            others = ranked[1:]
            metadata = dict(primary.detection_metadata_json or {})
            if others:
                metadata["same_run_candidates"] = [
                    {
                        "file_path": item.file_path,
                        "confidence": item.confidence,
                    }
                    for item in others
                ]
            primary.detection_metadata_json = metadata or None
            selected.append(primary)
        return selected

    def persist_candidates(
        self,
        session_db: Session,
        candidates: list[DeliverableCandidate],
    ) -> list[DeliverableVersion]:
        selected = self.select_primary_candidates(candidates)
        persisted: list[DeliverableVersion] = []

        for candidate in selected:
            deliverable, _ = DeliverableRepository.get_or_create(
                session_db,
                session_id=candidate.session_id,
                kind=candidate.kind,
                logical_name=candidate.logical_name,
            )
            session_db.flush()

            existing = DeliverableVersionRepository.get_by_session_run_path(
                session_db,
                session_id=candidate.session_id,
                run_id=candidate.run_id,
                file_path=candidate.file_path,
            )
            if existing is not None:
                persisted.append(existing)
                continue

            latest_version = DeliverableVersionRepository.get_latest_by_deliverable(
                session_db,
                deliverable_id=deliverable.id,
            )
            next_version_no = (
                1 if latest_version is None else latest_version.version_no + 1
            )

            version = DeliverableVersionRepository.create(
                session_db,
                session_id=candidate.session_id,
                run_id=candidate.run_id,
                deliverable_id=deliverable.id,
                source_message_id=candidate.source_message_id,
                version_no=next_version_no,
                file_path=candidate.file_path,
                file_name=candidate.file_name,
                mime_type=candidate.mime_type,
                input_refs_json=candidate.input_refs_json,
                related_tool_execution_ids_json=candidate.related_tool_execution_ids_json,
                detection_metadata_json={
                    **(candidate.detection_metadata_json or {}),
                    "confidence": candidate.confidence,
                    "normalized_logical_name": candidate.logical_name,
                },
            )
            session_db.flush()

            if (
                deliverable.latest_version_id is None
                or next_version_no > (latest_version.version_no if latest_version else 0)
            ):
                deliverable.latest_version_id = version.id

            persisted.append(version)

        return persisted
