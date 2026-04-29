"""Tests for short-lived OnlyOffice editing state."""

import asyncio
from datetime import UTC, datetime, timedelta
import logging
import os
from unittest.mock import MagicMock, patch


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now_utc(self) -> datetime:
        return self._now


def _create_session(store):
    return store.create_edit_session(
        session_id="00000000-0000-0000-0000-000000000001",
        user_id="user-1",
        file_path="report.docx",
        object_key="ws/abc/report.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        manifest_key="manifest.json",
        document_key="doc-key",
    )


def _create_session_with_id(store, edit_session_id: str, document_key: str):
    return store.create_edit_session(
        session_id="00000000-0000-0000-0000-000000000001",
        user_id="user-1",
        file_path="report.docx",
        object_key="ws/abc/report.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        manifest_key="manifest.json",
        document_key=document_key,
        edit_session_id=edit_session_id,
    )


def test_edit_session_ttl_uses_settings():
    from app.core.settings import get_settings
    from app.services.office_editing_service import OfficeEditingStore

    now = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    with patch.dict(os.environ, {"OFFICE_EDIT_SESSION_TTL_SECONDS": "2"}, clear=False):
        get_settings.cache_clear()
        session = _create_session(OfficeEditingStore(clock=FixedClock(now)))
        get_settings.cache_clear()

    assert session.expires_at == now + timedelta(seconds=2)


def test_cleanup_expired_revokes_callback_token_and_fails_active_save_request():
    from app.services.office_editing_service import (
        OfficeEditingStore,
        SAVE_STATUS_FAILED,
    )

    store = OfficeEditingStore()
    session = _create_session(store)
    save_request = store.create_save_request(session)
    store.mark_saving(save_request.save_request_id)

    expired_at = session.expires_at + timedelta(seconds=1)
    result = store.cleanup_expired(now=expired_at)

    assert result["edit_sessions"] == 1
    assert store.get_edit_session(session.edit_session_id) is None
    assert store.resolve_by_token(session.callback_token) is None
    assert (
        store.get_save_request(save_request.save_request_id).status
        == SAVE_STATUS_FAILED
    )
    assert (
        store.get_save_request(save_request.save_request_id).error_code
        == "office_edit_session_expired"
    )


def test_cleanup_expired_uses_store_clock_when_now_is_omitted():
    from app.core.settings import get_settings
    from app.services.office_editing_service import OfficeEditingStore

    created_at = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    expired_at = datetime(2026, 4, 29, 12, 0, 3, tzinfo=UTC)
    clock = FixedClock(created_at)
    with patch.dict(os.environ, {"OFFICE_EDIT_SESSION_TTL_SECONDS": "2"}, clear=False):
        get_settings.cache_clear()
        store = OfficeEditingStore(clock=clock)
        session = _create_session(store)
        get_settings.cache_clear()

    clock._now = expired_at
    result = store.cleanup_expired()

    assert result["edit_sessions"] == 1
    assert store.get_edit_session(session.edit_session_id) is None
    assert store.resolve_by_token(session.callback_token) is None


def test_save_request_ttl_uses_store_clock():
    from app.core.settings import get_settings
    from app.services.office_editing_service import OfficeEditingStore

    now = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    with patch.dict(os.environ, {"OFFICE_SAVE_REQUEST_TTL_SECONDS": "7"}, clear=False):
        get_settings.cache_clear()
        store = OfficeEditingStore(clock=FixedClock(now))
        session = _create_session(store)
        save_request = store.create_save_request(session)
        get_settings.cache_clear()

    assert save_request.created_at == now
    assert save_request.updated_at == now
    assert save_request.expires_at == now + timedelta(seconds=7)


def test_recreating_edit_session_revokes_previous_callback_token():
    from app.services.office_editing_service import OfficeEditingStore

    store = OfficeEditingStore()
    first = _create_session(store)

    second = _create_session_with_id(
        store,
        edit_session_id=first.edit_session_id,
        document_key="doc-key-v2",
    )

    assert first.callback_token != second.callback_token
    assert store.resolve_by_token(first.callback_token) is None
    assert store.resolve_by_token(second.callback_token) == second


def test_cleanup_loop_runs_cleanup_before_sleep():
    from app.services.office_editing_service import run_office_editing_cleanup_loop

    store = MagicMock()

    async def stop_after_first_sleep(_interval):
        raise asyncio.CancelledError

    with patch(
        "app.services.office_editing_service.asyncio.sleep",
        side_effect=stop_after_first_sleep,
    ):
        try:
            asyncio.run(
                run_office_editing_cleanup_loop(store=store, interval_seconds=60)
            )
        except asyncio.CancelledError:
            pass

    store.cleanup_expired.assert_called_once()


def test_cleanup_loop_logs_expired_state_counts(caplog):
    from app.services.office_editing_service import run_office_editing_cleanup_loop

    store = MagicMock()
    store.cleanup_expired.return_value = {
        "edit_sessions": 2,
        "save_requests": 3,
    }

    async def stop_after_first_sleep(_interval):
        raise asyncio.CancelledError

    with (
        caplog.at_level(logging.INFO, logger="app.services.office_editing_service"),
        patch(
            "app.services.office_editing_service.asyncio.sleep",
            side_effect=stop_after_first_sleep,
        ),
    ):
        try:
            asyncio.run(
                run_office_editing_cleanup_loop(store=store, interval_seconds=60)
            )
        except asyncio.CancelledError:
            pass

    assert (
        "Office editing cleanup completed: edit_sessions=2, save_requests=3"
        in caplog.text
    )


def test_file_backed_store_restores_active_edit_session_and_save_request(tmp_path):
    from app.services.office_editing_service import (
        OfficeEditingStore,
        SAVE_STATUS_SAVING,
    )

    state_path = tmp_path / "office-editing-state.json"
    store = OfficeEditingStore(state_path=state_path)
    session = _create_session(store)
    save_request = store.create_save_request(session)
    store.mark_saving(save_request.save_request_id)

    restored = OfficeEditingStore(state_path=state_path)

    restored_session = restored.resolve_by_token(session.callback_token)
    restored_save_request = restored.get_save_request(save_request.save_request_id)
    assert restored_session is not None
    assert restored_session.edit_session_id == session.edit_session_id
    assert restored_session.callback_token == session.callback_token
    assert restored_save_request is not None
    assert restored_save_request.status == SAVE_STATUS_SAVING
    assert restored_save_request.edit_session_id == session.edit_session_id


def test_try_begin_commit_allows_only_one_active_committer():
    from app.services.office_editing_service import (
        OfficeEditingStore,
        SAVE_STATUS_COMMITTING,
    )

    store = OfficeEditingStore()
    session = _create_session(store)
    save_request = store.create_save_request(session)
    store.mark_saving(save_request.save_request_id)

    first = store.try_begin_commit(
        save_request.save_request_id,
        edit_session_id=session.edit_session_id,
    )
    second = store.try_begin_commit(
        save_request.save_request_id,
        edit_session_id=session.edit_session_id,
    )

    assert first is not None
    assert first.save_request_id == save_request.save_request_id
    assert second is None
    assert (
        store.get_save_request(save_request.save_request_id).status
        == SAVE_STATUS_COMMITTING
    )


def test_try_begin_commit_uses_store_clock_for_commit_start_time():
    from app.services.office_editing_service import OfficeEditingStore

    created_at = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    committing_at = datetime(2026, 4, 29, 12, 5, tzinfo=UTC)
    clock = FixedClock(created_at)
    store = OfficeEditingStore(clock=clock)
    session = _create_session(store)
    save_request = store.create_save_request(session)
    store.mark_saving(save_request.save_request_id)

    clock._now = committing_at
    store.try_begin_commit(
        save_request.save_request_id,
        edit_session_id=session.edit_session_id,
    )

    updated = store.get_save_request(save_request.save_request_id)
    assert updated.updated_at == committing_at
    assert updated.completed_at is None


def test_mark_saved_uses_store_clock_for_completion_time():
    from app.services.office_editing_service import OfficeEditingStore

    created_at = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    completed_at = datetime(2026, 4, 29, 12, 5, tzinfo=UTC)
    clock = FixedClock(created_at)
    store = OfficeEditingStore(clock=clock)
    session = _create_session(store)
    save_request = store.create_save_request(session)

    clock._now = completed_at
    store.mark_saved(save_request.save_request_id)

    updated = store.get_save_request(save_request.save_request_id)
    assert updated.updated_at == completed_at
    assert updated.completed_at == completed_at


def test_complete_save_request_uses_store_clock_for_completion_time():
    from app.services.office_editing_service import OfficeEditingStore

    created_at = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    completed_at = datetime(2026, 4, 29, 12, 5, tzinfo=UTC)
    clock = FixedClock(created_at)
    store = OfficeEditingStore(clock=clock)
    session = _create_session(store)
    save_request = store.create_save_request(session)

    clock._now = completed_at
    store.complete_save_request(
        save_request.save_request_id,
        edit_session_id=session.edit_session_id,
    )

    updated = store.get_save_request(save_request.save_request_id)
    assert updated.updated_at == completed_at
    assert updated.completed_at == completed_at


def test_file_backed_store_persists_discarded_callback_token_revocation(tmp_path):
    from app.services.office_editing_service import OfficeEditingStore

    state_path = tmp_path / "office-editing-state.json"
    store = OfficeEditingStore(state_path=state_path)
    session = _create_session(store)

    assert store.discard_edit_session(session.edit_session_id) is True

    restored = OfficeEditingStore(state_path=state_path)
    assert restored.resolve_by_token(session.callback_token) is None
    assert restored.get_edit_session(session.edit_session_id) is None
