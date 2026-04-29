import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.callback import (
    AgentCallbackRequest,
    AgentCurrentState,
    FileChange,
    McpStatus,
    WorkspaceState,
)
from app.services.callback_service import CallbackService


def _load_callback_service_module_from_source():
    module_name = "_callback_service_import_probe"
    module_path = (
        Path(__file__).resolve().parents[1] / "app" / "services" / "callback_service.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)


def test_callback_service_module_import_does_not_initialize_concrete_adapters() -> None:
    with (
        patch(
            "app.services.backend_client.BackendClient",
            side_effect=AssertionError("backend client should be lazy"),
        ),
        patch(
            "app.services.workspace_export_service.WorkspaceExportService",
            side_effect=AssertionError("workspace export should be lazy"),
        ),
    ):
        module = _load_callback_service_module_from_source()

    assert module.CallbackService is not None


def test_callback_service_uses_injected_factories_without_constructing_defaults() -> (
    None
):
    backend = MagicMock()
    exporter = MagicMock()

    with (
        patch(
            "app.services.callback_service.BackendClient",
            side_effect=AssertionError("backend client should be provided by factory"),
        ),
        patch(
            "app.services.callback_service.WorkspaceExportService",
            side_effect=AssertionError(
                "workspace exporter should be provided by factory"
            ),
        ),
    ):
        service = CallbackService(
            backend_client_factory=lambda: backend,
            workspace_export_service_factory=lambda: exporter,
        )

        assert service._get_backend_client() is backend
        assert service._get_workspace_export_service() is exporter


class TestIsInternalMcpServer(unittest.TestCase):
    """Test CallbackService._is_internal_mcp_server."""

    def test_internal_mcp_server_with_poco_prefix(self) -> None:
        """Test that __poco_ prefix is detected as internal."""
        assert CallbackService._is_internal_mcp_server("__poco_mcp_server") is True

    def test_internal_mcp_server_with_whitespace(self) -> None:
        """Test that whitespace is trimmed before checking."""
        assert CallbackService._is_internal_mcp_server("  __poco_test  ") is True

    def test_not_internal_mcp_server(self) -> None:
        """Test that non-internal servers return False."""
        assert CallbackService._is_internal_mcp_server("my_mcp_server") is False
        assert CallbackService._is_internal_mcp_server("poco_server") is False
        assert CallbackService._is_internal_mcp_server("__poco") is False

    def test_empty_string(self) -> None:
        """Test empty string returns False."""
        assert CallbackService._is_internal_mcp_server("") is False

    def test_none_value(self) -> None:
        """Test None value returns False."""
        assert CallbackService._is_internal_mcp_server(None) is False  # type: ignore


class TestIsIgnoredWorkspacePath(unittest.TestCase):
    """Test CallbackService._is_ignored_workspace_path."""

    def _call_with_mock(
        self, path: str, ignore_names: set[str] | None = None, ignore_dot: bool = True
    ) -> bool:
        """Call _is_ignored_workspace_path with mocked workspace_manager."""
        mock_wm = MagicMock()
        mock_wm._ignore_names = (
            ignore_names if ignore_names is not None else {"node_modules", ".git"}
        )
        mock_wm.ignore_dot_files = ignore_dot

        with patch(
            "app.services.callback_service.workspace_manager",
            mock_wm,
        ):
            return CallbackService._is_ignored_workspace_path(path)

    def test_empty_path_is_ignored(self) -> None:
        """Test that empty path is ignored."""
        assert self._call_with_mock("") is True

    def test_none_path_is_ignored(self) -> None:
        """Test that None path is ignored."""
        assert self._call_with_mock(None) is True  # type: ignore

    def test_whitespace_only_is_ignored(self) -> None:
        """Test that whitespace only path is ignored."""
        assert self._call_with_mock("   ") is True

    def test_slash_only_is_ignored(self) -> None:
        """Test that slash only path is ignored."""
        assert self._call_with_mock("/") is True
        assert self._call_with_mock("//") is True

    def test_ignored_name_is_ignored(self) -> None:
        """Test that paths with ignored names are ignored."""
        assert (
            self._call_with_mock("node_modules", ignore_names={"node_modules"}) is True
        )
        assert (
            self._call_with_mock(
                "node_modules/package.json", ignore_names={"node_modules"}
            )
            is True
        )
        assert (
            self._call_with_mock("src/node_modules", ignore_names={"node_modules"})
            is True
        )
        assert self._call_with_mock(".git", ignore_names={".git"}) is True
        assert self._call_with_mock(".git/config", ignore_names={".git"}) is True

    def test_dot_file_is_ignored(self) -> None:
        """Test that dot files are ignored when ignore_dot_files is True."""
        assert self._call_with_mock(".env", ignore_dot=True) is True
        assert self._call_with_mock(".config", ignore_dot=True) is True
        assert self._call_with_mock("src/.hidden", ignore_dot=True) is True

    def test_dot_file_not_ignored_when_disabled(self) -> None:
        """Test that dot files are not ignored when ignore_dot_files is False."""
        assert self._call_with_mock(".env", ignore_dot=False) is False
        assert self._call_with_mock("src/.hidden", ignore_dot=False) is False

    def test_normal_path_not_ignored(self) -> None:
        """Test that normal paths are not ignored."""
        assert self._call_with_mock("src/main.py", ignore_names=set()) is False
        assert self._call_with_mock("README.md", ignore_names=set()) is False
        assert self._call_with_mock("app/services/test.py", ignore_names=set()) is False

    def test_path_traversal_is_ignored(self) -> None:
        """Test that path traversal attempts are ignored."""
        assert self._call_with_mock("../etc/passwd", ignore_names=set()) is True
        assert self._call_with_mock("./..", ignore_names=set()) is True
        assert self._call_with_mock("src/../..", ignore_names=set()) is True

    def test_normalizes_backslashes(self) -> None:
        """Test that backslashes are normalized to forward slashes."""
        assert (
            self._call_with_mock("src\\node_modules", ignore_names={"node_modules"})
            is True
        )
        assert self._call_with_mock("src\\.env", ignore_dot=True) is True

    def test_strips_leading_dot_slash(self) -> None:
        """Test that leading ./ is stripped."""
        assert self._call_with_mock("./src/main.py", ignore_names=set()) is False
        assert (
            self._call_with_mock("./node_modules", ignore_names={"node_modules"})
            is True
        )


class TestFilterStatePatch(unittest.TestCase):
    """Test CallbackService._filter_state_patch."""

    def _create_callback(
        self,
        mcp_status: list[McpStatus] | None = None,
        file_changes: list[FileChange] | None = None,
    ) -> AgentCallbackRequest:
        """Create a callback with given state."""
        workspace_state = None
        if file_changes is not None:
            workspace_state = WorkspaceState(
                file_changes=file_changes,
                last_change=datetime.now(timezone.utc),
            )

        state = AgentCurrentState(
            mcp_status=mcp_status or [],
            workspace_state=workspace_state,
        )

        return AgentCallbackRequest(
            session_id="test-session",
            status="running",
            progress=50,
            state_patch=state,
        )

    def test_filter_removes_internal_mcp_servers(self) -> None:
        """Test that internal MCP servers are filtered out."""
        callback = self._create_callback(
            mcp_status=[
                McpStatus(server_name="__poco_internal", status="running"),
                McpStatus(server_name="my_mcp", status="running"),
            ]
        )

        result = CallbackService._filter_state_patch(callback)

        assert result.state_patch is not None
        assert result.state_patch.mcp_status is not None
        assert len(result.state_patch.mcp_status) == 1
        assert result.state_patch.mcp_status[0].server_name == "my_mcp"

    def test_filter_preserves_all_external_mcp_servers(self) -> None:
        """Test that all external MCP servers are preserved."""
        callback = self._create_callback(
            mcp_status=[
                McpStatus(server_name="mcp1", status="running"),
                McpStatus(server_name="mcp2", status="stopped"),
            ]
        )

        result = CallbackService._filter_state_patch(callback)

        assert result.state_patch is not None
        assert result.state_patch.mcp_status is not None
        assert len(result.state_patch.mcp_status) == 2

    def test_filter_removes_ignored_file_changes(self) -> None:
        """Test that ignored file changes are filtered out."""
        mock_workspace_manager = MagicMock()
        mock_workspace_manager._ignore_names = {"node_modules"}
        mock_workspace_manager.ignore_dot_files = True

        with patch(
            "app.services.callback_service.workspace_manager",
            mock_workspace_manager,
        ):
            callback = self._create_callback(
                file_changes=[
                    FileChange(path="src/main.py", status="modified", added_lines=10),
                    FileChange(
                        path="node_modules/package.json",
                        status="added",
                        added_lines=5,
                    ),
                    FileChange(path=".env", status="added", added_lines=3),
                ]
            )

            result = CallbackService._filter_state_patch(callback)

            assert result.state_patch is not None
            assert result.state_patch.workspace_state is not None
            assert result.state_patch.workspace_state.file_changes is not None
            assert len(result.state_patch.workspace_state.file_changes) == 1
            assert (
                result.state_patch.workspace_state.file_changes[0].path == "src/main.py"
            )

    def test_filter_recalculates_line_counts_when_filtered(self) -> None:
        """Test that line counts are recalculated after filtering."""
        mock_workspace_manager = MagicMock()
        mock_workspace_manager._ignore_names = {"node_modules"}
        mock_workspace_manager.ignore_dot_files = False

        with patch(
            "app.services.callback_service.workspace_manager",
            mock_workspace_manager,
        ):
            # Include a file that will be filtered
            callback = self._create_callback(
                file_changes=[
                    FileChange(
                        path="file1.py",
                        status="modified",
                        added_lines=10,
                        deleted_lines=2,
                    ),
                    FileChange(
                        path="node_modules/file2.py",
                        status="modified",
                        added_lines=5,
                        deleted_lines=3,
                    ),
                ]
            )

            result = CallbackService._filter_state_patch(callback)

            assert result.state_patch is not None
            assert result.state_patch.workspace_state is not None
            # Only file1.py remains, so totals should match file1.py
            assert result.state_patch.workspace_state.total_added_lines == 10
            assert result.state_patch.workspace_state.total_deleted_lines == 2

    def test_filter_returns_same_callback_if_no_state(self) -> None:
        """Test that callback without state_patch is returned unchanged."""
        callback = AgentCallbackRequest(
            session_id="test-session",
            status="running",
            progress=50,
            state_patch=None,
        )

        result = CallbackService._filter_state_patch(callback)

        assert result is callback

    def test_filter_returns_same_callback_if_no_changes(self) -> None:
        """Test that callback is returned unchanged if no filtering needed."""
        mock_workspace_manager = MagicMock()
        mock_workspace_manager._ignore_names = set()
        mock_workspace_manager.ignore_dot_files = False

        with patch(
            "app.services.callback_service.workspace_manager",
            mock_workspace_manager,
        ):
            callback = self._create_callback(
                file_changes=[
                    FileChange(path="src/main.py", status="modified", added_lines=10),
                ]
            )

            result = CallbackService._filter_state_patch(callback)

            # When state is unchanged, should return original callback
            assert result.state_patch is not None
            assert result.state_patch.workspace_state is not None
            assert result.state_patch.workspace_state.file_changes is not None
            assert (
                result.state_patch.workspace_state.file_changes[0].path == "src/main.py"
            )


class TestProcessCallback(unittest.TestCase):
    """Test CallbackService.process_callback."""

    def _create_callback(
        self,
        status: str = "running",
        progress: int = 50,
        state_patch: AgentCurrentState | None = None,
    ) -> AgentCallbackRequest:
        """Create a test callback."""
        return AgentCallbackRequest(
            session_id="test-session",
            run_id="test-run",
            status=status,  # type: ignore
            progress=progress,
            state_patch=state_patch,
        )

    def test_process_callback_success(self) -> None:
        """Test successful callback processing."""
        mock_backend_client = MagicMock()
        mock_backend_client.forward_callback = AsyncMock(
            return_value={"status": "received"}
        )

        with patch("app.services.callback_service.backend_client", mock_backend_client):
            service = CallbackService()
            callback = self._create_callback()

            import asyncio

            result = asyncio.run(service.process_callback(callback))

            assert result.status == "received"
            assert result.session_id == "test-session"
            assert result.callback_status == "running"
            assert result.progress == 50

    def test_process_callback_completed_status(self) -> None:
        """Test callback processing with completed status."""
        mock_backend_client = MagicMock()
        mock_backend_client.forward_callback = AsyncMock(
            return_value={"status": "completed"}
        )

        mock_task_dispatcher = MagicMock()
        mock_task_dispatcher.on_task_complete = AsyncMock()

        with (
            patch("app.services.callback_service.backend_client", mock_backend_client),
            patch("app.scheduler.task_dispatcher.TaskDispatcher", mock_task_dispatcher),
            patch(
                "app.services.callback_service.asyncio.create_task"
            ) as mock_create_task,
        ):
            service = CallbackService()
            callback = self._create_callback(status="completed", progress=100)
            mock_create_task.side_effect = lambda coro: coro.close()

            import asyncio

            result = asyncio.run(service.process_callback(callback))

            assert result.callback_status == "completed"
            mock_create_task.assert_called_once()
            mock_task_dispatcher.on_task_complete.assert_called_once()

    def test_process_callback_failed_status(self) -> None:
        """Test callback processing with failed status."""
        mock_backend_client = MagicMock()
        mock_backend_client.forward_callback = AsyncMock(
            return_value={"status": "failed"}
        )

        mock_task_dispatcher = MagicMock()
        mock_task_dispatcher.on_task_complete = AsyncMock()

        with (
            patch("app.services.callback_service.backend_client", mock_backend_client),
            patch("app.scheduler.task_dispatcher.TaskDispatcher", mock_task_dispatcher),
            patch(
                "app.services.callback_service.asyncio.create_task"
            ) as mock_create_task,
        ):
            service = CallbackService()
            callback = self._create_callback(status="failed", progress=80)
            mock_create_task.side_effect = lambda coro: coro.close()

            import asyncio

            result = asyncio.run(service.process_callback(callback))

            assert result.callback_status == "failed"
            mock_create_task.assert_called_once()
            mock_task_dispatcher.on_task_complete.assert_called_once()

    def test_process_callback_deferred_cleanup(self) -> None:
        """Test callback with session still pending/running defers cleanup."""
        mock_backend_client = MagicMock()
        mock_backend_client.forward_callback = AsyncMock(
            return_value={"status": "pending"}
        )

        mock_task_dispatcher = MagicMock()
        mock_task_dispatcher.on_task_complete = AsyncMock()

        with (
            patch("app.services.callback_service.backend_client", mock_backend_client),
            patch("app.scheduler.task_dispatcher.TaskDispatcher", mock_task_dispatcher),
            patch(
                "app.services.callback_service.asyncio.create_task"
            ) as mock_create_task,
        ):
            service = CallbackService()
            callback = self._create_callback(status="completed", progress=100)
            mock_create_task.side_effect = lambda coro: coro.close()

            import asyncio

            asyncio.run(service.process_callback(callback))

            # on_task_complete should NOT be called when session is still pending
            mock_task_dispatcher.on_task_complete.assert_not_called()
            mock_create_task.assert_called_once()

    def test_process_callback_uses_injected_runtime_cleanup(self) -> None:
        """Test terminal callback cleanup uses the injected runtime boundary."""
        mock_backend_client = MagicMock()
        mock_backend_client.forward_callback = AsyncMock(
            return_value={"status": "completed"}
        )
        runtime_cleanup = MagicMock()
        runtime_cleanup.on_task_complete = AsyncMock()

        with (
            patch("app.scheduler.task_dispatcher.TaskDispatcher") as task_dispatcher,
            patch(
                "app.services.callback_service.asyncio.create_task"
            ) as mock_create_task,
        ):
            task_dispatcher.on_task_complete.side_effect = AssertionError(
                "runtime cleanup should be injected"
            )
            service = CallbackService(
                backend_client_factory=lambda: mock_backend_client,
                runtime_cleanup=runtime_cleanup,
            )
            callback = self._create_callback(status="completed", progress=100)
            mock_create_task.side_effect = lambda coro: coro.close()

            import asyncio

            result = asyncio.run(service.process_callback(callback))

        assert result.callback_status == "completed"
        runtime_cleanup.on_task_complete.assert_awaited_once_with("test-session")
        task_dispatcher.on_task_complete.assert_not_called()
        mock_create_task.assert_called_once()

    def test_process_callback_uses_injected_workspace_path_filter(self) -> None:
        """Test state patch filtering uses the injected workspace path boundary."""

        class ExplodingWorkspaceManager:
            def __getattr__(self, name: str) -> object:
                raise AssertionError("workspace path filter should be injected")

        mock_backend_client = MagicMock()
        mock_backend_client.forward_callback = AsyncMock(
            return_value={"status": "received"}
        )
        workspace_path_filter = MagicMock()
        workspace_path_filter.is_ignored.side_effect = lambda path: path == "hidden.txt"
        state = AgentCurrentState(
            workspace_state=WorkspaceState(
                file_changes=[
                    FileChange(path="src/main.py", status="modified", added_lines=10),
                    FileChange(path="hidden.txt", status="added", added_lines=5),
                ],
                last_change=datetime.now(timezone.utc),
            )
        )

        with patch(
            "app.services.callback_service.workspace_manager",
            ExplodingWorkspaceManager(),
        ):
            service = CallbackService(
                backend_client_factory=lambda: mock_backend_client,
                workspace_path_filter=workspace_path_filter,
            )
            callback = self._create_callback(state_patch=state)

            import asyncio

            result = asyncio.run(service.process_callback(callback))

        assert result.status == "received"
        payload = mock_backend_client.forward_callback.call_args.args[0]
        file_changes = payload["state_patch"]["workspace_state"]["file_changes"]
        assert [item["path"] for item in file_changes] == ["src/main.py"]
        assert payload["state_patch"]["workspace_state"]["total_added_lines"] == 10
        assert payload["state_patch"]["workspace_state"]["total_deleted_lines"] == 0
        workspace_path_filter.is_ignored.assert_any_call("src/main.py")
        workspace_path_filter.is_ignored.assert_any_call("hidden.txt")

    def test_process_callback_with_state_patch(self) -> None:
        """Test callback processing with state_patch data."""
        mock_backend_client = MagicMock()
        mock_backend_client.forward_callback = AsyncMock(
            return_value={"status": "received"}
        )

        mock_workspace_manager = MagicMock()
        mock_workspace_manager._ignore_names = set()
        mock_workspace_manager.ignore_dot_files = False

        state = AgentCurrentState(
            todos=[{"content": "Task 1", "status": "in_progress"}],  # type: ignore
            mcp_status=[McpStatus(server_name="test_mcp", status="running")],
        )

        with (
            patch("app.services.callback_service.backend_client", mock_backend_client),
            patch(
                "app.services.callback_service.workspace_manager",
                mock_workspace_manager,
            ),
        ):
            service = CallbackService()
            callback = self._create_callback(state_patch=state)

            import asyncio

            result = asyncio.run(service.process_callback(callback))

            assert result.status == "received"

    def test_process_callback_forward_failure(self) -> None:
        """Test callback processing when forward fails."""
        from app.core.errors.error_codes import ErrorCode
        from app.core.errors.exceptions import AppException

        mock_backend_client = MagicMock()
        mock_backend_client.forward_callback = AsyncMock(
            side_effect=Exception("Backend error")
        )

        with patch("app.services.callback_service.backend_client", mock_backend_client):
            service = CallbackService()
            callback = self._create_callback()

            import asyncio

            with self.assertRaises(AppException) as ctx:
                asyncio.run(service.process_callback(callback))

            assert ctx.exception.error_code == ErrorCode.CALLBACK_FORWARD_FAILED
            assert "Failed to forward callback" in ctx.exception.message


class TestExportAndForward(unittest.TestCase):
    """Test CallbackService._export_and_forward."""

    def test_export_and_forward_success(self) -> None:
        """Test successful export and forward."""
        from app.schemas.workspace import WorkspaceExportResult

        mock_export_result = WorkspaceExportResult(
            workspace_files_prefix="workspaces/user/session/files",
            workspace_manifest_key="workspaces/user/session/manifest.json",
            workspace_archive_key="workspaces/user/session/archive.zip",
            workspace_export_status="ready",
        )

        mock_workspace_export = MagicMock()
        mock_workspace_export.export_workspace = MagicMock(
            return_value=mock_export_result
        )

        mock_backend_client = MagicMock()
        mock_backend_client.forward_callback = AsyncMock(return_value={"status": "ok"})

        with (
            patch(
                "app.services.callback_service.workspace_export_service",
                mock_workspace_export,
            ),
            patch("app.services.callback_service.backend_client", mock_backend_client),
        ):
            service = CallbackService()
            callback = AgentCallbackRequest(
                session_id="test-session",
                run_id="test-run",
                status="completed",  # type: ignore
                progress=100,
            )

            import asyncio

            asyncio.run(service._export_and_forward(callback))

            mock_workspace_export.export_workspace.assert_called_once_with(
                "test-session"
            )
            mock_backend_client.forward_callback.assert_called_once()

    def test_export_and_forward_export_failure(self) -> None:
        """Test export failure is handled gracefully."""
        mock_workspace_export = MagicMock()
        mock_workspace_export.export_workspace = MagicMock(
            side_effect=Exception("Export failed")
        )

        mock_backend_client = MagicMock()
        mock_backend_client.forward_callback = AsyncMock(return_value={"status": "ok"})

        with (
            patch(
                "app.services.callback_service.workspace_export_service",
                mock_workspace_export,
            ),
            patch("app.services.callback_service.backend_client", mock_backend_client),
        ):
            service = CallbackService()
            callback = AgentCallbackRequest(
                session_id="test-session",
                run_id="test-run",
                status="completed",  # type: ignore
                progress=100,
            )

            import asyncio

            # Should not raise, just log and continue
            asyncio.run(service._export_and_forward(callback))

            # forward_callback should still be called with failed status
            assert mock_backend_client.forward_callback.called

    def test_export_and_forward_callback_failure(self) -> None:
        """Test callback forward failure is handled gracefully."""
        from app.schemas.workspace import WorkspaceExportResult

        mock_export_result = WorkspaceExportResult(
            workspace_files_prefix="workspaces/user/session/files",
            workspace_manifest_key="workspaces/user/session/manifest.json",
            workspace_archive_key="workspaces/user/session/archive.zip",
            workspace_export_status="ready",
        )

        mock_workspace_export = MagicMock()
        mock_workspace_export.export_workspace = MagicMock(
            return_value=mock_export_result
        )

        mock_backend_client = MagicMock()
        mock_backend_client.forward_callback = AsyncMock(
            side_effect=Exception("Callback failed")
        )

        with (
            patch(
                "app.services.callback_service.workspace_export_service",
                mock_workspace_export,
            ),
            patch("app.services.callback_service.backend_client", mock_backend_client),
        ):
            service = CallbackService()
            callback = AgentCallbackRequest(
                session_id="test-session",
                run_id="test-run",
                status="completed",  # type: ignore
                progress=100,
            )

            import asyncio

            # Should not raise, just log the error
            asyncio.run(service._export_and_forward(callback))

    def test_export_and_forward_with_failed_status(self) -> None:
        """Test export and forward with failed task status."""
        from app.schemas.workspace import WorkspaceExportResult

        mock_export_result = WorkspaceExportResult(
            workspace_files_prefix="workspaces/user/session/files",
            workspace_manifest_key="workspaces/user/session/manifest.json",
            workspace_archive_key="workspaces/user/session/archive.zip",
            workspace_export_status="ready",
        )

        mock_workspace_export = MagicMock()
        mock_workspace_export.export_workspace = MagicMock(
            return_value=mock_export_result
        )

        mock_backend_client = MagicMock()
        mock_backend_client.forward_callback = AsyncMock(return_value={"status": "ok"})

        with (
            patch(
                "app.services.callback_service.workspace_export_service",
                mock_workspace_export,
            ),
            patch("app.services.callback_service.backend_client", mock_backend_client),
        ):
            service = CallbackService()
            callback = AgentCallbackRequest(
                session_id="test-session",
                run_id="test-run",
                status="failed",  # type: ignore
                progress=80,
                error_message="Task failed",
            )

            import asyncio

            asyncio.run(service._export_and_forward(callback))

            # Verify forward_callback was called
            assert mock_backend_client.forward_callback.called
            # Get the call argument
            call_args = mock_backend_client.forward_callback.call_args
            assert call_args is not None
            payload = call_args[0][0]  # First positional argument
            assert payload["progress"] == 80

    def test_export_and_forward_uses_injected_clock(self) -> None:
        """Test exported callback time comes from injected clock."""
        from app.schemas.workspace import WorkspaceExportResult

        fixed_now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        clock = MagicMock()
        clock.now_utc.return_value = fixed_now
        mock_export_result = WorkspaceExportResult(
            workspace_files_prefix="workspaces/user/session/files",
            workspace_manifest_key="workspaces/user/session/manifest.json",
            workspace_archive_key="workspaces/user/session/archive.zip",
            workspace_export_status="ready",
        )
        mock_workspace_export = MagicMock()
        mock_workspace_export.export_workspace = MagicMock(
            return_value=mock_export_result
        )
        mock_backend_client = MagicMock()
        mock_backend_client.forward_callback = AsyncMock(return_value={"status": "ok"})

        with (
            patch(
                "app.services.callback_service.workspace_export_service",
                mock_workspace_export,
            ),
            patch("app.services.callback_service.backend_client", mock_backend_client),
        ):
            service = CallbackService(clock=clock)
            callback = AgentCallbackRequest(
                session_id="test-session",
                run_id="test-run",
                status="completed",  # type: ignore
                progress=100,
            )

            import asyncio

            asyncio.run(service._export_and_forward(callback))

            payload = mock_backend_client.forward_callback.call_args[0][0]
            assert payload["time"].startswith("2024-01-01T12:00:00")
            clock.now_utc.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
