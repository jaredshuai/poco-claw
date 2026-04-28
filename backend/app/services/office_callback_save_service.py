"""OnlyOffice callback save use case."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any

import httpx

from app.core.errors.exceptions import AppException
from app.schemas.office import OfficeCallbackRequest
from app.services.office_editing_service import (
    OfficeEditSession,
    SAVE_STATUS_COMMITTING,
    SAVE_STATUS_FAILED,
    SAVE_STATUS_PENDING,
    SAVE_STATUS_SAVED,
    SAVE_STATUS_SAVING,
)
from app.services.office_writeback_service import (
    OfficeSaveWritebackService,
    OfficeWritebackStateCommitError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OfficeDownloadedContent:
    content: bytes
    content_type: str | None


class OfficeCallbackContentDownloader:
    """Download saved callback content from the trusted Document Server."""

    async def download(self, url: str) -> OfficeDownloadedContent:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return OfficeDownloadedContent(
                content=response.content,
                content_type=response.headers.get("content-type"),
            )


class OfficeCallbackSaveUseCase:
    """Handle OnlyOffice status=6 callback writeback and save state transitions."""

    def __init__(
        self,
        *,
        storage_service: Any,
        editing_store: Any,
        validate_download_url: Callable[[str], None],
        downloader: OfficeCallbackContentDownloader | None = None,
    ) -> None:
        self.storage_service = storage_service
        self.editing_store = editing_store
        self.validate_download_url = validate_download_url
        self.downloader = downloader or OfficeCallbackContentDownloader()

    async def handle_callback(
        self,
        *,
        edit_session: OfficeEditSession,
        callback: OfficeCallbackRequest,
    ) -> None:
        if callback.status == 6:
            await self.handle_saved_callback(
                edit_session=edit_session,
                callback=callback,
            )
        elif callback.status == 7:
            await self.handle_failed_callback(
                edit_session=edit_session,
                callback=callback,
            )

    async def handle_saved_callback(
        self,
        *,
        edit_session: OfficeEditSession,
        callback: OfficeCallbackRequest,
    ) -> None:
        if not callback.userdata:
            return
        save_request = self.editing_store.get_save_request(callback.userdata)
        if (
            save_request is None
            or save_request.edit_session_id != edit_session.edit_session_id
        ):
            return
        if save_request.status in {
            SAVE_STATUS_COMMITTING,
            SAVE_STATUS_SAVED,
            SAVE_STATUS_FAILED,
        }:
            return
        if not callback.url:
            self.editing_store.mark_failed(
                save_request.save_request_id,
                error_code="office_callback_missing_url",
            )
            return

        try:
            self.validate_download_url(callback.url)
        except AppException:
            self.editing_store.mark_failed(
                save_request.save_request_id,
                error_code="untrusted_callback_download_url",
            )
            raise

        try:
            claimed_save_request = self.editing_store.try_begin_commit(
                save_request.save_request_id,
                edit_session_id=edit_session.edit_session_id,
            )
            if claimed_save_request is None:
                return
            save_request = claimed_save_request

            downloaded = await self.downloader.download(callback.url)
            content_type = (
                downloaded.content_type
                or edit_session.mime_type
                or "application/octet-stream"
            )
            OfficeSaveWritebackService(
                storage_service=self.storage_service,
                editing_store=self.editing_store,
            ).commit_saved_content(
                edit_session=edit_session,
                save_request=save_request,
                content=downloaded.content,
                content_type=content_type,
            )
        except OfficeWritebackStateCommitError:
            logger.exception(
                "Office writeback committed but save state commit failed",
                extra={
                    "save_request_id": save_request.save_request_id,
                    "edit_session_id": edit_session.edit_session_id,
                    "session_id": edit_session.session_id,
                },
            )
            raise
        except Exception as exc:
            self.editing_store.mark_failed(
                save_request.save_request_id,
                error_code="writeback_failed",
                error_message=str(exc),
            )
            raise

    async def handle_failed_callback(
        self,
        *,
        edit_session: OfficeEditSession,
        callback: OfficeCallbackRequest,
    ) -> None:
        if not callback.userdata:
            return
        save_request = self.editing_store.get_save_request(callback.userdata)
        if (
            save_request is None
            or save_request.edit_session_id != edit_session.edit_session_id
        ):
            return
        if save_request.status not in {SAVE_STATUS_PENDING, SAVE_STATUS_SAVING}:
            return

        self.editing_store.mark_failed(
            save_request.save_request_id,
            error_code="office_forcesave_failed",
            error_message=str(callback.error) if callback.error is not None else None,
        )
