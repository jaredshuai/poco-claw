from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.user_input import UserInputClient


@pytest.mark.asyncio
async def test_wait_for_answer_uses_injected_clock_for_timeout() -> None:
    start = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    clock = MagicMock()
    clock.now_utc.side_effect = [
        start,
        start + timedelta(seconds=1),
        start + timedelta(seconds=3),
    ]
    client = UserInputClient("http://backend.test", poll_interval=0, clock=clock)
    client.get_request = AsyncMock(return_value={"status": "pending"})

    with patch("app.core.user_input.asyncio.sleep", new=AsyncMock()) as sleep:
        result = await client.wait_for_answer("request-123", timeout_seconds=2)

    assert result is None
    client.get_request.assert_awaited_once_with("request-123")
    sleep.assert_awaited_once_with(0)
