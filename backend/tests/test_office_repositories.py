"""Tests for OfficeEditSessionRepository and OfficeSaveRequestRepository.

Uses unittest + MagicMock, mirroring test_run_repository.py. Real DB integration
is left to the office service/API tests; these verify wiring and the
conditional-update contracts.
"""

import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.repositories.office_edit_session_repository import OfficeEditSessionRepository
from app.repositories.office_save_request_repository import OfficeSaveRequestRepository
from app.services.office_editing_service import (
    SAVE_STATUS_CALLBACK_RECEIVED,
    SAVE_STATUS_COMMITTING,
    SAVE_STATUS_FAILED,
    SAVE_STATUS_PENDING,
    SAVE_STATUS_SAVED,
    SAVE_STATUS_SAVING,
    SAVE_STATUS_STAGED,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# =============================================================================
# OfficeEditSessionRepository
# =============================================================================


class TestOfficeEditSessionRepositoryCreate(unittest.TestCase):
    def test_create_with_defaults(self) -> None:
        db = MagicMock()
        result = OfficeEditSessionRepository.create(
            db,
            session_id="session-1",
            user_id="user-1",
            file_path="report.docx",
            object_key="ws/abc/report.docx",
            mime_type="application/pdf",
            manifest_key="manifest.json",
            document_key="doc-key",
            callback_token="token-xyz",
            expires_at=_now() + timedelta(minutes=30),
        )

        self.assertEqual(result.session_id, "session-1")
        self.assertEqual(result.user_id, "user-1")
        self.assertEqual(result.file_path, "report.docx")
        self.assertEqual(result.object_key, "ws/abc/report.docx")
        self.assertFalse(result.discarded)
        db.add.assert_called_once_with(result)

    def test_create_with_explicit_id(self) -> None:
        db = MagicMock()
        explicit_id = uuid.uuid4()
        result = OfficeEditSessionRepository.create(
            db,
            session_id="session-1",
            user_id="user-1",
            file_path="report.docx",
            object_key="k",
            mime_type=None,
            manifest_key=None,
            document_key="dk",
            callback_token="t",
            expires_at=_now(),
            edit_session_id=explicit_id,
        )

        self.assertEqual(result.id, explicit_id)


class TestOfficeEditSessionRepositoryQueries(unittest.TestCase):
    def test_get_by_id(self) -> None:
        db = MagicMock()
        edit_session_id = uuid.uuid4()
        OfficeEditSessionRepository.get_by_id(db, edit_session_id)
        db.query.assert_called_once()

    def test_get_by_callback_token_filters_discarded(self) -> None:
        db = MagicMock()
        query_chain = MagicMock()
        db.query.return_value = query_chain
        query_chain.filter.return_value = query_chain
        query_chain.first.return_value = None

        OfficeEditSessionRepository.get_by_callback_token(db, "token")

        # Two filters: token match + discarded check
        self.assertEqual(query_chain.filter.call_count, 2)


class TestOfficeEditSessionRepositoryMutations(unittest.TestCase):
    def test_mark_discarded_returns_true_when_affected(self) -> None:
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.rowcount = 1
        db.execute.return_value = result_mock

        affected = OfficeEditSessionRepository.mark_discarded(db, uuid.uuid4())

        self.assertTrue(affected)

    def test_mark_discarded_returns_false_when_noop(self) -> None:
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.rowcount = 0
        db.execute.return_value = result_mock

        affected = OfficeEditSessionRepository.mark_discarded(db, uuid.uuid4())

        self.assertFalse(affected)

    def test_update_object_key_executes_update(self) -> None:
        db = MagicMock()
        OfficeEditSessionRepository.update_object_key(
            db, uuid.uuid4(), "new/key.docx"
        )
        db.execute.assert_called_once()

    def test_expire_discarded_and_expired_returns_rows(self) -> None:
        db = MagicMock()
        query_chain = MagicMock()
        db.query.return_value = query_chain
        query_chain.filter.return_value = query_chain
        rows = [MagicMock()]
        query_chain.all.return_value = rows

        result = OfficeEditSessionRepository.expire_discarded_and_expired(
            db, now=_now()
        )

        self.assertEqual(result, rows)


# =============================================================================
# OfficeSaveRequestRepository
# =============================================================================


class TestOfficeSaveRequestRepositoryCreate(unittest.TestCase):
    def test_create_defaults_to_pending(self) -> None:
        db = MagicMock()
        edit_session_id = uuid.uuid4()
        result = OfficeSaveRequestRepository.create(
            db,
            edit_session_id=edit_session_id,
            session_id="session-1",
            user_id="user-1",
            file_path="report.docx",
            document_key="dk",
            expires_at=_now() + timedelta(hours=1),
        )

        self.assertEqual(result.status, SAVE_STATUS_PENDING)
        self.assertEqual(result.edit_session_id, edit_session_id)
        db.add.assert_called_once_with(result)


class TestOfficeSaveRequestRepositoryStatusTransitions(unittest.TestCase):
    def test_mark_saving(self) -> None:
        db = MagicMock()
        OfficeSaveRequestRepository.mark_saving(db, uuid.uuid4())
        db.execute.assert_called_once()

    def test_mark_staged_writes_object_key(self) -> None:
        db = MagicMock()
        save_id = uuid.uuid4()
        OfficeSaveRequestRepository.mark_staged(db, save_id, "staged/key.docx")
        db.execute.assert_called_once()

    def test_mark_saved_sets_completed_at(self) -> None:
        db = MagicMock()
        now = _now()
        OfficeSaveRequestRepository.mark_saved(db, uuid.uuid4(), completed_at=now)
        db.execute.assert_called_once()

    def test_mark_failed_sets_error(self) -> None:
        db = MagicMock()
        now = _now()
        OfficeSaveRequestRepository.mark_failed(
            db, uuid.uuid4(), error_code="boom", error_message="oops", completed_at=now
        )
        db.execute.assert_called_once()


class TestOfficeSaveRequestRepositoryTryBeginCommit(unittest.TestCase):
    def test_returns_updated_row_on_success(self) -> None:
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.rowcount = 1
        db.execute.return_value = result_mock
        fetched = MagicMock()
        db.query.return_value = MagicMock()
        db.query.return_value.filter.return_value = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = fetched

        save_id = uuid.uuid4()
        edit_session_id = uuid.uuid4()
        result = OfficeSaveRequestRepository.try_begin_commit(
            db, save_id, edit_session_id
        )

        self.assertEqual(result, fetched)
        db.execute.assert_called_once()

    def test_returns_none_when_no_rows_affected(self) -> None:
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.rowcount = 0
        db.execute.return_value = result_mock

        result = OfficeSaveRequestRepository.try_begin_commit(
            db, uuid.uuid4(), uuid.uuid4()
        )

        self.assertIsNone(result)
        # Must not query when update affected nothing
        db.query.assert_not_called()


class TestOfficeSaveRequestRepositoryBulkOperations(unittest.TestCase):
    def test_fail_active_by_edit_session(self) -> None:
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.rowcount = 3
        db.execute.return_value = result_mock

        count = OfficeSaveRequestRepository.fail_active_by_edit_session(
            db, uuid.uuid4(), error_code="expired", completed_at=_now()
        )

        self.assertEqual(count, 3)

    def test_expire_old(self) -> None:
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.rowcount = 5
        db.execute.return_value = result_mock

        count = OfficeSaveRequestRepository.expire_old(db, now=_now())

        self.assertEqual(count, 5)

    def test_recover_staged_returns_rows(self) -> None:
        db = MagicMock()
        rows = [MagicMock(), MagicMock()]
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = rows
        db.scalars.return_value = scalars_mock

        result = OfficeSaveRequestRepository.recover_staged(db)

        self.assertEqual(result, rows)


if __name__ == "__main__":
    unittest.main()
