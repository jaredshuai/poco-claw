from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.hooks.base import ExecutionContext
from app.hooks.workspace import WorkspaceHook


@pytest.mark.asyncio
async def test_workspace_hook_uses_injected_clock_for_last_change() -> None:
    fixed_now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    clock = MagicMock()
    clock.now_utc.return_value = fixed_now
    hook = WorkspaceHook(clock=clock)
    hook._get_repository_url = MagicMock(return_value="https://example.test/repo.git")
    context = ExecutionContext(session_id="session-123", cwd="/workspace")
    git_status = SimpleNamespace(
        branch="main",
        modified=[],
        staged=[],
        untracked=[],
        deleted=[],
        renamed=[],
    )

    with (
        patch("app.hooks.workspace.is_repository", return_value=True),
        patch("app.hooks.workspace.get_status", return_value=git_status),
        patch("app.hooks.workspace.get_numstat", return_value={}),
    ):
        await hook.on_agent_response(context, message=None)

    assert context.current_state.workspace_state is not None
    assert context.current_state.workspace_state.last_change == fixed_now
    clock.now_utc.assert_called_once_with()
