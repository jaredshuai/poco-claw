from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.hooks.base import ExecutionContext
from app.hooks.run_snapshot import RunSnapshotHook


def test_run_snapshot_hook_uses_injected_clock_for_generated_run_id() -> None:
    clock = MagicMock()
    clock.now_utc.return_value = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    hook = RunSnapshotHook(clock=clock)

    run_id = hook._resolve_run_id(
        ExecutionContext(session_id="session/with unsafe chars", cwd="/workspace")
    )

    assert run_id == "session_with_unsafe_chars_20240102T030405Z"
    clock.now_utc.assert_called_once_with()
