import logging
import uuid
from collections.abc import Callable
from typing import Protocol

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.models.agent_message import AgentMessage
from app.models.agent_run import AgentRun
from app.repositories.message_feedback_repository import MessageFeedbackRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.run_repository import RunRepository
from app.schemas.input_file import InputFile
from app.schemas.message import (
    InputFileWithUrl,
    MessageAttachmentsDeltaResponse,
    MessageAttachmentsResponse,
    MessageDeltaResponse,
    MessageResponse,
    MessageWithFilesDeltaResponse,
    MessageWithFilesResponse,
)
from app.services.storage_service import S3StorageService

logger = logging.getLogger(__name__)


class MessageStorage(Protocol):
    def presign_get(
        self,
        key: str,
        *,
        response_content_disposition: str | None = None,
        response_content_type: str | None = None,
    ) -> str: ...


def build_message_storage() -> MessageStorage:
    return S3StorageService()


class MessageService:
    """Service layer for message queries."""

    def __init__(
        self,
        *,
        storage_service_factory: Callable[[], MessageStorage] | None = None,
    ) -> None:
        self.storage_service_factory = storage_service_factory or build_message_storage

    def _get_storage_service(self) -> MessageStorage:
        return self.storage_service_factory()

    @staticmethod
    def _collect_message_attachments(
        runs: list[AgentRun],
    ) -> dict[int, list[InputFile]]:
        message_id_to_attachments: dict[int, list[InputFile]] = {}
        for run in runs:
            snapshot = run.config_snapshot or {}
            if not isinstance(snapshot, dict):
                continue

            uploaded = snapshot.get("input_files")
            if not isinstance(uploaded, list) or not uploaded:
                continue

            parsed: list[InputFile] = []
            for item in uploaded:
                if not isinstance(item, dict):
                    continue
                try:
                    parsed.append(InputFile.model_validate(item))
                except ValidationError:
                    continue

            if parsed:
                message_id_to_attachments[run.user_message_id] = parsed

        return message_id_to_attachments

    @staticmethod
    def _to_input_files_with_urls(
        raw_attachments: list[InputFile],
        *,
        user_id: str,
        storage_service: MessageStorage,
    ) -> list[InputFileWithUrl]:
        key_prefix = f"attachments/{user_id}/"

        attachments: list[InputFileWithUrl] = []
        for file in raw_attachments:
            key = (file.source or "").strip()
            url = None
            if key and key.startswith(key_prefix):
                try:
                    url = storage_service.presign_get(
                        key,
                        response_content_disposition="inline",
                        response_content_type=file.content_type,
                    )
                except Exception:
                    url = None
            attachments.append(
                InputFileWithUrl(
                    **file.model_dump(mode="json"),
                    url=url,
                )
            )
        return attachments

    def _build_messages_with_files(
        self,
        db: Session,
        messages: list[AgentMessage],
        *,
        user_id: str,
        message_id_to_attachments: dict[int, list[InputFile]],
    ) -> list[MessageWithFilesResponse]:
        storage_service = self._get_storage_service()
        base_messages = self._build_message_responses(db, messages, user_id=user_id)

        result: list[MessageWithFilesResponse] = []
        for msg, base in zip(messages, base_messages, strict=False):
            raw_attachments = message_id_to_attachments.get(msg.id) or []
            attachments = self._to_input_files_with_urls(
                raw_attachments,
                user_id=user_id,
                storage_service=storage_service,
            )
            result.append(
                MessageWithFilesResponse(
                    **base.model_dump(mode="json"),
                    attachments=attachments,
                )
            )
        return result

    def _build_message_responses(
        self,
        db: Session,
        messages: list[AgentMessage],
        *,
        user_id: str | None = None,
    ) -> list[MessageResponse]:
        vote_by_message_id: dict[int, str] = {}
        if user_id and messages:
            vote_by_message_id = (
                MessageFeedbackRepository.list_votes_by_user_and_message_ids(
                    db,
                    user_id=user_id,
                    message_ids=[message.id for message in messages],
                )
            )
        result: list[MessageResponse] = []
        for message in messages:
            result.append(
                MessageResponse(
                    id=message.id,
                    role=message.role,
                    content=message.content,
                    text_preview=message.text_preview,
                    feedback_vote=vote_by_message_id.get(message.id, "none"),
                    created_at=message.created_at,
                    updated_at=message.updated_at,
                )
            )
        return result

    def get_message_response(
        self,
        db: Session,
        message_id: int,
        *,
        user_id: str | None = None,
    ) -> MessageResponse:
        """Gets a single message serialized for API responses."""
        message = self.get_message(db, message_id)
        return self._build_message_responses(db, [message], user_id=user_id)[0]

    def get_message_responses(
        self,
        db: Session,
        session_id: uuid.UUID,
        *,
        user_id: str | None = None,
    ) -> list[MessageResponse]:
        """Gets serialized messages for a session."""
        messages = self.get_messages(db, session_id)
        return self._build_message_responses(db, messages, user_id=user_id)

    def get_messages(self, db: Session, session_id: uuid.UUID) -> list[AgentMessage]:
        """Gets all messages for a session.

        Args:
            db: Database session
            session_id: Session ID

        Returns:
            List of messages ordered by creation time
        """
        messages = MessageRepository.list_by_session(db, session_id)
        logger.debug(f"Retrieved {len(messages)} messages for session {session_id}")
        return messages

    def get_message(self, db: Session, message_id: int) -> AgentMessage:
        """Gets a message by ID.

        Args:
            db: Database session
            message_id: Message ID

        Returns:
            The message

        Raises:
            AppException: If message not found
        """
        message = MessageRepository.get_by_id(db, message_id)
        if not message:
            raise AppException(
                error_code=ErrorCode.NOT_FOUND,
                message=f"Message not found: {message_id}",
            )
        return message

    def get_messages_with_files(
        self, db: Session, session_id: uuid.UUID, *, user_id: str
    ) -> list[MessageWithFilesResponse]:
        """Gets messages for a session and attaches per-run uploaded files.

        Attachments are derived from the run snapshot to avoid coupling the
        message content schema to any upstream agent SDK format.
        """
        messages = MessageRepository.list_by_session(db, session_id, limit=1000)
        message_id_to_attachments = self._build_message_id_to_attachments(
            db, session_id
        )
        result = self._build_messages_with_files(
            db,
            messages,
            user_id=user_id,
            message_id_to_attachments=message_id_to_attachments,
        )

        logger.debug(
            "messages_with_files_retrieved",
            extra={
                "session_id": str(session_id),
                "message_count": len(messages),
                "attachments_mapped": len(message_id_to_attachments),
            },
        )
        return result

    def get_messages_with_files_delta(
        self,
        db: Session,
        session_id: uuid.UUID,
        *,
        user_id: str,
        after_message_id: int = 0,
        limit: int = 200,
    ) -> MessageWithFilesDeltaResponse:
        """Gets incremental message-with-files updates for polling."""
        safe_limit = max(1, min(int(limit), 1000))
        safe_after_id = max(0, int(after_message_id))

        fetched = MessageRepository.list_by_session_after_id(
            db,
            session_id,
            after_id=safe_after_id,
            limit=safe_limit + 1,
        )
        has_more = len(fetched) > safe_limit
        messages = fetched[:safe_limit]

        message_ids = [message.id for message in messages]
        runs = RunRepository.list_by_session_and_user_message_ids(
            db, session_id, message_ids
        )
        message_id_to_attachments = self._collect_message_attachments(runs)
        items = self._build_messages_with_files(
            db,
            messages,
            user_id=user_id,
            message_id_to_attachments=message_id_to_attachments,
        )

        next_after_message_id = items[-1].id if items else safe_after_id or None
        return MessageWithFilesDeltaResponse(
            items=items,
            next_after_message_id=next_after_message_id,
            has_more=has_more,
        )

    def get_messages_delta(
        self,
        db: Session,
        session_id: uuid.UUID,
        *,
        user_id: str | None = None,
        after_message_id: int = 0,
        limit: int = 200,
    ) -> MessageDeltaResponse:
        """Gets incremental message updates for polling without attachments."""
        safe_limit = max(1, min(int(limit), 1000))
        safe_after_id = max(0, int(after_message_id))

        fetched = MessageRepository.list_by_session_after_id(
            db,
            session_id,
            after_id=safe_after_id,
            limit=safe_limit + 1,
        )
        has_more = len(fetched) > safe_limit
        messages = fetched[:safe_limit]
        items = self._build_message_responses(db, messages, user_id=user_id)

        next_after_message_id = items[-1].id if items else safe_after_id or None
        return MessageDeltaResponse(
            items=items,
            next_after_message_id=next_after_message_id,
            has_more=has_more,
        )

    def get_message_attachments(
        self, db: Session, session_id: uuid.UUID, *, user_id: str
    ) -> list[MessageAttachmentsResponse]:
        """Gets per-message attachments for a session."""

        message_id_to_attachments = self._build_message_id_to_attachments(
            db, session_id
        )
        storage_service = self._get_storage_service()
        result: list[MessageAttachmentsResponse] = []
        for message_id, attachments in sorted(message_id_to_attachments.items()):
            result.append(
                MessageAttachmentsResponse(
                    message_id=message_id,
                    attachments=self._to_input_files_with_urls(
                        attachments,
                        user_id=user_id,
                        storage_service=storage_service,
                    ),
                )
            )
        return result

    def get_message_attachments_delta(
        self,
        db: Session,
        session_id: uuid.UUID,
        *,
        user_id: str,
        after_message_id: int = 0,
        limit: int = 200,
    ) -> MessageAttachmentsDeltaResponse:
        """Gets incremental message attachments for polling."""
        safe_limit = max(1, min(int(limit), 1000))
        safe_after_id = max(0, int(after_message_id))

        fetched_message_ids = MessageRepository.list_ids_by_session_after_id(
            db,
            session_id,
            after_id=safe_after_id,
            limit=safe_limit + 1,
        )
        has_more = len(fetched_message_ids) > safe_limit
        page_message_ids = fetched_message_ids[:safe_limit]

        if not page_message_ids:
            return MessageAttachmentsDeltaResponse(
                items=[],
                next_after_message_id=safe_after_id or None,
                has_more=False,
            )

        runs = RunRepository.list_by_session_and_user_message_ids(
            db,
            session_id,
            page_message_ids,
        )
        message_id_to_attachments = self._collect_message_attachments(runs)
        storage_service = self._get_storage_service()
        items: list[MessageAttachmentsResponse] = []
        for message_id in page_message_ids:
            attachments = message_id_to_attachments.get(message_id) or []
            if not attachments:
                continue
            items.append(
                MessageAttachmentsResponse(
                    message_id=message_id,
                    attachments=self._to_input_files_with_urls(
                        attachments,
                        user_id=user_id,
                        storage_service=storage_service,
                    ),
                )
            )

        return MessageAttachmentsDeltaResponse(
            items=items,
            next_after_message_id=page_message_ids[-1],
            has_more=has_more,
        )

    def _build_message_id_to_attachments(
        self, db: Session, session_id: uuid.UUID
    ) -> dict[int, list[InputFile]]:
        runs = RunRepository.list_by_session(db, session_id, limit=1000)
        return self._collect_message_attachments(runs)
