import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.schemas.callback import AgentCallbackRequest, CallbackStatus
from app.services.callback_service import CallbackService


def create_callback_request(
    session_id: str = "session-1",
    status: CallbackStatus = CallbackStatus.COMPLETED,
    **kwargs: object,
) -> AgentCallbackRequest:
    """Helper to create AgentCallbackRequest with required fields."""
    return AgentCallbackRequest(
        session_id=session_id,
        status=status,
        time=kwargs.pop("time", datetime.now(timezone.utc)),
        progress=kwargs.pop("progress", 0),
        **kwargs,  # type: ignore[arg-type]
    )


class TestCallbackServiceParseRunId(unittest.TestCase):
    """Test _parse_run_id method."""

    def test_none_input(self) -> None:
        service = CallbackService()
        result = service._parse_run_id(None)
        self.assertIsNone(result)

    def test_empty_string(self) -> None:
        service = CallbackService()
        result = service._parse_run_id("")
        self.assertIsNone(result)

    def test_invalid_uuid(self) -> None:
        service = CallbackService()
        result = service._parse_run_id("not-a-uuid")
        self.assertIsNone(result)

    def test_valid_uuid(self) -> None:
        service = CallbackService()
        test_uuid = uuid.uuid4()
        result = service._parse_run_id(str(test_uuid))
        self.assertEqual(result, test_uuid)

    def test_whitespace_string(self) -> None:
        service = CallbackService()
        result = service._parse_run_id("   ")
        self.assertIsNone(result)


class TestCallbackServiceIsFinalWorkspaceExport(unittest.TestCase):
    """Test _is_final_workspace_export method."""

    def test_none_status(self) -> None:
        service = CallbackService()
        callback = create_callback_request(workspace_export_status=None)
        result = service._is_final_workspace_export(callback)
        self.assertFalse(result)

    def test_empty_status(self) -> None:
        service = CallbackService()
        callback = create_callback_request(workspace_export_status="")
        result = service._is_final_workspace_export(callback)
        self.assertFalse(result)

    def test_pending_status(self) -> None:
        service = CallbackService()
        callback = create_callback_request(workspace_export_status="pending")
        result = service._is_final_workspace_export(callback)
        self.assertFalse(result)

    def test_ready_status(self) -> None:
        service = CallbackService()
        callback = create_callback_request(workspace_export_status="ready")
        result = service._is_final_workspace_export(callback)
        self.assertTrue(result)

    def test_failed_status(self) -> None:
        service = CallbackService()
        callback = create_callback_request(workspace_export_status="failed")
        result = service._is_final_workspace_export(callback)
        self.assertTrue(result)

    def test_case_insensitive(self) -> None:
        service = CallbackService()
        callback = create_callback_request(workspace_export_status="READY")
        result = service._is_final_workspace_export(callback)
        self.assertTrue(result)


class TestCallbackServiceExtractSdkSessionIdFromMessage(unittest.TestCase):
    """Test _extract_sdk_session_id_from_message method."""

    def test_result_message_with_session_id(self) -> None:
        service = CallbackService()
        message = {
            "_type": "ResultMessage",
            "session_id": "sdk-session-123",
        }
        result = service._extract_sdk_session_id_from_message(message)
        self.assertEqual(result, "sdk-session-123")

    def test_result_message_without_session_id(self) -> None:
        service = CallbackService()
        message = {
            "_type": "ResultMessage",
        }
        result = service._extract_sdk_session_id_from_message(message)
        self.assertIsNone(result)

    def test_result_message_non_string_session_id(self) -> None:
        service = CallbackService()
        message = {
            "_type": "ResultMessage",
            "session_id": 123,
        }
        result = service._extract_sdk_session_id_from_message(message)
        self.assertIsNone(result)

    def test_system_message_init_with_nested_data(self) -> None:
        service = CallbackService()
        message = {
            "_type": "SystemMessage",
            "subtype": "init",
            "data": {
                "data": {
                    "session_id": "nested-session-456",
                }
            },
        }
        result = service._extract_sdk_session_id_from_message(message)
        self.assertEqual(result, "nested-session-456")

    def test_system_message_init_with_direct_session_id(self) -> None:
        service = CallbackService()
        message = {
            "_type": "SystemMessage",
            "subtype": "init",
            "data": {
                "session_id": "direct-session-789",
            },
        }
        result = service._extract_sdk_session_id_from_message(message)
        self.assertEqual(result, "direct-session-789")

    def test_system_message_non_init_subtype(self) -> None:
        service = CallbackService()
        message = {
            "_type": "SystemMessage",
            "subtype": "other",
            "data": {
                "session_id": "session-xxx",
            },
        }
        result = service._extract_sdk_session_id_from_message(message)
        self.assertIsNone(result)

    def test_system_message_init_invalid_data(self) -> None:
        service = CallbackService()
        message = {
            "_type": "SystemMessage",
            "subtype": "init",
            "data": "not a dict",
        }
        result = service._extract_sdk_session_id_from_message(message)
        self.assertIsNone(result)

    def test_unknown_message_type(self) -> None:
        service = CallbackService()
        message = {
            "_type": "UnknownMessage",
            "session_id": "session-xxx",
        }
        result = service._extract_sdk_session_id_from_message(message)
        self.assertIsNone(result)


class TestCallbackServiceExtractRoleFromMessage(unittest.TestCase):
    """Test _extract_role_from_message method."""

    def test_assistant_message(self) -> None:
        service = CallbackService()
        message = {"_type": "AssistantMessage"}
        result = service._extract_role_from_message(message)
        self.assertEqual(result, "assistant")

    def test_user_message(self) -> None:
        service = CallbackService()
        message = {"_type": "UserMessage"}
        result = service._extract_role_from_message(message)
        self.assertEqual(result, "user")

    def test_system_message(self) -> None:
        service = CallbackService()
        message = {"_type": "SystemMessage"}
        result = service._extract_role_from_message(message)
        self.assertEqual(result, "system")

    def test_unknown_message_type(self) -> None:
        service = CallbackService()
        message = {"_type": "UnknownMessage"}
        result = service._extract_role_from_message(message)
        self.assertEqual(result, "assistant")

    def test_no_type(self) -> None:
        service = CallbackService()
        message = {}
        result = service._extract_role_from_message(message)
        self.assertEqual(result, "assistant")


class TestCallbackServiceShouldSkipActiveRunFallback(unittest.TestCase):
    """Test _should_skip_active_run_fallback method."""

    def test_with_run_id(self) -> None:
        service = CallbackService()
        callback = create_callback_request(run_id="run-1")
        result = service._should_skip_active_run_fallback(callback)
        self.assertFalse(result)

    def test_non_terminal_status(self) -> None:
        service = CallbackService()
        callback = create_callback_request(status=CallbackStatus.RUNNING)
        result = service._should_skip_active_run_fallback(callback)
        self.assertFalse(result)

    def test_with_new_message(self) -> None:
        service = CallbackService()
        callback = create_callback_request(new_message={"_type": "AssistantMessage"})
        result = service._should_skip_active_run_fallback(callback)
        self.assertFalse(result)

    def test_terminal_without_workspace_export(self) -> None:
        service = CallbackService()
        callback = create_callback_request()
        result = service._should_skip_active_run_fallback(callback)
        self.assertFalse(result)

    def test_terminal_with_pending_workspace_export(self) -> None:
        service = CallbackService()
        callback = create_callback_request(workspace_export_status="pending")
        result = service._should_skip_active_run_fallback(callback)
        self.assertFalse(result)

    def test_terminal_with_ready_workspace_export(self) -> None:
        service = CallbackService()
        callback = create_callback_request(workspace_export_status="ready")
        result = service._should_skip_active_run_fallback(callback)
        self.assertTrue(result)

    def test_failed_with_ready_workspace_export(self) -> None:
        service = CallbackService()
        callback = create_callback_request(
            status=CallbackStatus.FAILED, workspace_export_status="ready"
        )
        result = service._should_skip_active_run_fallback(callback)
        self.assertTrue(result)


class TestCallbackServiceShouldPreserveExistingReadyWorkspace(unittest.TestCase):
    """Test _should_preserve_existing_ready_workspace method."""

    def test_no_existing_ready_workspace(self) -> None:
        service = CallbackService()
        db_session = MagicMock()
        db_session.workspace_export_status = None
        db_session.workspace_files_prefix = None

        callback = create_callback_request()
        result = service._should_preserve_existing_ready_workspace(db_session, callback)
        self.assertFalse(result)

    def test_existing_ready_workspace_with_incoming_artifacts(self) -> None:
        service = CallbackService()
        db_session = MagicMock()
        db_session.workspace_export_status = "ready"
        db_session.workspace_files_prefix = "files/prefix"
        db_session.workspace_manifest_key = "manifest.json"
        db_session.workspace_archive_key = None

        callback = create_callback_request(
            workspace_export_status="pending",
            workspace_files_prefix="new/prefix",
        )
        result = service._should_preserve_existing_ready_workspace(db_session, callback)
        self.assertFalse(result)

    def test_existing_ready_workspace_incoming_status_ready(self) -> None:
        service = CallbackService()
        db_session = MagicMock()
        db_session.workspace_export_status = "ready"
        db_session.workspace_files_prefix = "files/prefix"

        callback = create_callback_request(workspace_export_status="ready")
        result = service._should_preserve_existing_ready_workspace(db_session, callback)
        self.assertFalse(result)

    def test_existing_ready_workspace_should_preserve(self) -> None:
        service = CallbackService()
        db_session = MagicMock()
        db_session.workspace_export_status = "ready"
        db_session.workspace_files_prefix = "files/prefix"
        db_session.workspace_manifest_key = "manifest.json"
        db_session.workspace_archive_key = None

        callback = create_callback_request(workspace_export_status="pending")
        result = service._should_preserve_existing_ready_workspace(db_session, callback)
        self.assertTrue(result)


class TestCallbackServiceExtractToolExecutions(unittest.TestCase):
    """Test _extract_tool_executions method."""

    def test_non_list_content(self) -> None:
        db = MagicMock()
        service = CallbackService()
        message = {"content": "not a list"}
        service._extract_tool_executions(db, message, uuid.uuid4(), 1)
        # Should not raise

    def test_empty_content(self) -> None:
        db = MagicMock()
        service = CallbackService()
        message = {"content": []}
        service._extract_tool_executions(db, message, uuid.uuid4(), 1)
        # Should not raise

    def test_tool_use_block_missing_id(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        service = CallbackService()
        message = {
            "content": [
                {"_type": "ToolUseBlock", "name": "test_tool"},
            ]
        }
        with patch(
            "app.services.callback_service.ToolExecutionRepository"
        ) as mock_repo:
            service._extract_tool_executions(db, message, session_id, 1)
            mock_repo.create.assert_not_called()

    def test_tool_use_block_missing_name(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        service = CallbackService()
        message = {
            "content": [
                {"_type": "ToolUseBlock", "id": "tool-1"},
            ]
        }
        with patch(
            "app.services.callback_service.ToolExecutionRepository"
        ) as mock_repo:
            service._extract_tool_executions(db, message, session_id, 1)
            mock_repo.create.assert_not_called()

    def test_tool_use_block_creates_new(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        service = CallbackService()
        message = {
            "content": [
                {"_type": "ToolUseBlock", "id": "tool-1", "name": "read_file", "input": {"path": "/tmp"}},
            ]
        }
        with patch(
            "app.services.callback_service.ToolExecutionRepository"
        ) as mock_repo:
            mock_repo.get_by_session_and_tool_use_id.return_value = None
            service._extract_tool_executions(db, message, session_id, 1)
            mock_repo.create.assert_called_once()

    def test_tool_use_block_updates_existing(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        service = CallbackService()
        message = {
            "content": [
                {"_type": "ToolUseBlock", "id": "tool-1", "name": "read_file", "input": {"path": "/tmp"}},
            ]
        }
        with patch(
            "app.services.callback_service.ToolExecutionRepository"
        ) as mock_repo:
            existing = MagicMock()
            mock_repo.get_by_session_and_tool_use_id.return_value = existing
            service._extract_tool_executions(db, message, session_id, 1)
            self.assertEqual(existing.tool_name, "read_file")
            mock_repo.create.assert_not_called()

    def test_tool_result_block_missing_tool_use_id(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        service = CallbackService()
        message = {
            "content": [
                {"_type": "ToolResultBlock", "content": "result"},
            ]
        }
        with patch(
            "app.services.callback_service.ToolExecutionRepository"
        ) as mock_repo:
            service._extract_tool_executions(db, message, session_id, 1)
            mock_repo.create.assert_not_called()

    def test_tool_result_block_creates_new(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        service = CallbackService()
        message = {
            "content": [
                {"_type": "ToolResultBlock", "tool_use_id": "tool-1", "content": "result", "is_error": False},
            ]
        }
        with patch(
            "app.services.callback_service.ToolExecutionRepository"
        ) as mock_repo:
            mock_repo.get_by_session_and_tool_use_id.return_value = None
            service._extract_tool_executions(db, message, session_id, 1)
            mock_repo.create.assert_called_once()

    def test_tool_result_block_updates_existing(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        service = CallbackService()
        message = {
            "content": [
                {"_type": "ToolResultBlock", "tool_use_id": "tool-1", "content": "result", "is_error": True},
            ]
        }
        with patch(
            "app.services.callback_service.ToolExecutionRepository"
        ) as mock_repo:
            existing = MagicMock()
            existing.created_at = datetime.now(timezone.utc)
            mock_repo.get_by_session_and_tool_use_id.return_value = existing
            service._extract_tool_executions(db, message, session_id, 1)
            self.assertEqual(existing.is_error, True)

    def test_non_dict_block(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        service = CallbackService()
        message = {
            "content": ["not a dict", {"_type": "TextBlock", "text": "hello"}],
        }
        service._extract_tool_executions(db, message, session_id, 1)
        # Should not raise


class TestCallbackServiceExtractAndPersistUsage(unittest.TestCase):
    """Test _extract_and_persist_usage method."""

    def test_non_result_message(self) -> None:
        db = MagicMock()
        db_session = MagicMock()
        service = CallbackService()
        message = {"_type": "AssistantMessage"}
        service._extract_and_persist_usage(db, db_session, None, message)
        # Should not persist

    def test_result_message_without_usage(self) -> None:
        db = MagicMock()
        db_session = MagicMock()
        service = CallbackService()
        message = {"_type": "ResultMessage"}
        service._extract_and_persist_usage(db, db_session, None, message)
        # Should not persist

    def test_result_message_with_usage(self) -> None:
        db = MagicMock()
        db_session = MagicMock()
        db_session.id = uuid.uuid4()
        service = CallbackService()
        message = {
            "_type": "ResultMessage",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "total_cost_usd": 0.05,
            "duration_ms": 1000,
        }
        with patch("app.services.callback_service.UsageLogRepository") as mock_repo:
            with patch("app.services.callback_service.normalize_usage_payload") as mock_normalize:
                mock_normalize.return_value = {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "total_tokens": 150,
                }
                service._extract_and_persist_usage(db, db_session, None, message)
                mock_repo.create.assert_called_once()

    def test_result_message_with_run(self) -> None:
        db = MagicMock()
        db_session = MagicMock()
        db_session.id = uuid.uuid4()
        db_run = MagicMock()
        db_run.id = uuid.uuid4()
        service = CallbackService()
        message = {
            "_type": "ResultMessage",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        with patch("app.services.callback_service.UsageLogRepository") as mock_repo:
            with patch("app.services.callback_service.normalize_usage_payload") as mock_normalize:
                mock_normalize.return_value = {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "total_tokens": 150,
                }
                service._extract_and_persist_usage(db, db_session, db_run, message)
                mock_repo.create.assert_called_once()


class TestCallbackServiceShouldSkipDuplicateResultMessage(unittest.TestCase):
    """Test _should_skip_duplicate_result_message method."""

    def test_non_result_message(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        service = CallbackService()
        message = {"_type": "AssistantMessage"}
        result = service._should_skip_duplicate_result_message(db, session_id, message)
        self.assertFalse(result)

    def test_result_message_with_structured_output(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        service = CallbackService()
        message = {
            "_type": "ResultMessage",
            "structured_output": {"key": "value"},
        }
        result = service._should_skip_duplicate_result_message(db, session_id, message)
        self.assertFalse(result)

    def test_result_message_empty_text(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        service = CallbackService()
        message = {
            "_type": "ResultMessage",
            "content": [],
        }
        result = service._should_skip_duplicate_result_message(db, session_id, message)
        self.assertFalse(result)

    def test_no_latest_message(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        service = CallbackService()
        message = {
            "_type": "ResultMessage",
            "content": [{"_type": "TextBlock", "text": "Hello"}],
        }
        with patch("app.services.callback_service.MessageRepository") as mock_repo:
            mock_repo.get_latest_by_session.return_value = None
            result = service._should_skip_duplicate_result_message(db, session_id, message)
            self.assertFalse(result)

    def test_latest_message_not_assistant(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        service = CallbackService()
        message = {
            "_type": "ResultMessage",
            "content": [{"_type": "TextBlock", "text": "Hello"}],
        }
        latest = MagicMock()
        latest.role = "user"
        with patch("app.services.callback_service.MessageRepository") as mock_repo:
            mock_repo.get_latest_by_session.return_value = latest
            result = service._should_skip_duplicate_result_message(db, session_id, message)
            self.assertFalse(result)


class TestCallbackServicePersistMessageAndTools(unittest.TestCase):
    """Test _persist_message_and_tools method."""

    def test_persists_assistant_message(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        service = CallbackService()
        message = {
            "_type": "AssistantMessage",
            "content": [{"_type": "TextBlock", "text": "Hello"}],
        }
        with patch("app.services.callback_service.MessageRepository") as mock_repo:
            mock_message = MagicMock()
            mock_message.id = 1
            mock_repo.create.return_value = mock_message
            result = service._persist_message_and_tools(db, session_id, message)
            self.assertIsNotNone(result)

    def test_truncates_text_preview(self) -> None:
        db = MagicMock()
        session_id = uuid.uuid4()
        service = CallbackService()
        long_text = "x" * 1000
        message = {
            "_type": "AssistantMessage",
            "content": [{"_type": "TextBlock", "text": long_text}],
        }
        with patch("app.services.callback_service.MessageRepository") as mock_repo:
            mock_message = MagicMock()
            mock_message.id = 1
            mock_repo.create.return_value = mock_message
            service._persist_message_and_tools(db, session_id, message)
            # Check that text_preview was truncated
            call_kwargs = mock_repo.create.call_args.kwargs
            self.assertLessEqual(len(call_kwargs["text_preview"] or ""), 500)


class TestCallbackServiceShouldApplyWorkspaceExport(unittest.TestCase):
    """Test _should_apply_workspace_export method."""

    def test_no_workspace_export_payload(self) -> None:
        db = MagicMock()
        db_session = MagicMock()
        service = CallbackService()
        callback = create_callback_request(
            workspace_files_prefix=None,
            workspace_manifest_key=None,
            workspace_archive_key=None,
            workspace_export_status=None,
        )
        result = service._should_apply_workspace_export(db, db_session, None, callback)
        self.assertTrue(result)

    def test_with_workspace_payload_no_run(self) -> None:
        db = MagicMock()
        db_session = MagicMock()
        service = CallbackService()
        callback = create_callback_request(workspace_files_prefix="files/")
        result = service._should_apply_workspace_export(db, db_session, None, callback)
        self.assertTrue(result)

    def test_with_run_no_terminal_run(self) -> None:
        db = MagicMock()
        db_session = MagicMock()
        db_session.id = uuid.uuid4()
        db_run = MagicMock()
        db_run.id = uuid.uuid4()
        service = CallbackService()
        callback = create_callback_request(workspace_files_prefix="files/")
        with patch("app.services.callback_service.RunRepository") as mock_repo:
            mock_repo.get_latest_terminal_by_session.return_value = None
            result = service._should_apply_workspace_export(db, db_session, db_run, callback)
            self.assertTrue(result)

    def test_with_run_same_as_terminal(self) -> None:
        db = MagicMock()
        db_session = MagicMock()
        db_session.id = uuid.uuid4()
        db_run = MagicMock()
        db_run.id = uuid.uuid4()
        service = CallbackService()
        callback = create_callback_request(workspace_files_prefix="files/")
        with patch("app.services.callback_service.RunRepository") as mock_repo:
            mock_repo.get_latest_terminal_by_session.return_value = db_run
            result = service._should_apply_workspace_export(db, db_session, db_run, callback)
            self.assertTrue(result)

    def test_ready_status_with_stale_run(self) -> None:
        db = MagicMock()
        db_session = MagicMock()
        db_session.id = uuid.uuid4()
        db_session.workspace_export_status = "pending"  # Not "ready"
        db_run = MagicMock()
        db_run.id = uuid.uuid4()
        terminal_run = MagicMock()
        terminal_run.id = uuid.uuid4()  # Different from db_run
        service = CallbackService()
        callback = create_callback_request(
            workspace_files_prefix="files/",
            workspace_export_status="ready",
        )
        with patch("app.services.callback_service.RunRepository") as mock_repo:
            mock_repo.get_latest_terminal_by_session.return_value = terminal_run
            result = service._should_apply_workspace_export(db, db_session, db_run, callback)
            # Should return True because status is "ready" and session doesn't have "ready" yet
            self.assertTrue(result)

    def test_stale_run_non_ready_status(self) -> None:
        db = MagicMock()
        db_session = MagicMock()
        db_session.id = uuid.uuid4()
        db_session.workspace_export_status = "ready"  # Already has ready
        db_run = MagicMock()
        db_run.id = uuid.uuid4()
        terminal_run = MagicMock()
        terminal_run.id = uuid.uuid4()  # Different from db_run
        service = CallbackService()
        callback = create_callback_request(
            workspace_files_prefix="files/",
            workspace_export_status="pending",
        )
        with patch("app.services.callback_service.RunRepository") as mock_repo:
            mock_repo.get_latest_terminal_by_session.return_value = terminal_run
            result = service._should_apply_workspace_export(db, db_session, db_run, callback)
            # Should return False - stale run and not a "ready" status upgrade
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()