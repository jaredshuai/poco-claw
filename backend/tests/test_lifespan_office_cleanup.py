"""Tests for Office editing lifecycle cleanup wiring."""

import asyncio
import os
from unittest.mock import MagicMock, patch

from fastapi import FastAPI


def test_lifespan_starts_and_stops_office_cleanup_task():
    from app.core.settings import get_settings
    from app.lifecycle.lifespan import lifespan

    cleanup_task = MagicMock()
    cleanup_coro = object()
    cleanup_loop_mock = MagicMock(return_value=cleanup_coro)

    class DisabledService:
        enabled = False

    async def fake_gather(*_tasks, **_kwargs):
        return []

    async def run_lifespan_once():
        async with lifespan(FastAPI()):
            pass

    with patch.dict(
        os.environ,
        {
            "BOOTSTRAP_ON_STARTUP": "false",
            "OFFICE_EDITING_CLEANUP_INTERVAL_SECONDS": "5",
        },
        clear=False,
    ):
        get_settings.cache_clear()
        with (
            patch(
                "app.lifecycle.lifespan.ImEventDispatcher",
                return_value=DisabledService(),
            ),
            patch(
                "app.lifecycle.lifespan.DingTalkStreamService",
                return_value=DisabledService(),
            ),
            patch(
                "app.lifecycle.lifespan.FeishuStreamService",
                return_value=DisabledService(),
            ),
            patch(
                "app.lifecycle.lifespan.run_office_editing_cleanup_loop",
                new=cleanup_loop_mock,
            ) as mock_cleanup_loop,
            patch(
                "app.lifecycle.lifespan.asyncio.create_task",
                return_value=cleanup_task,
            ) as mock_create_task,
            patch("app.lifecycle.lifespan.asyncio.gather", side_effect=fake_gather),
            patch("app.lifecycle.lifespan.engine") as mock_engine,
        ):
            asyncio.run(run_lifespan_once())
        get_settings.cache_clear()

    mock_cleanup_loop.assert_called_once()
    assert mock_cleanup_loop.call_args.kwargs["interval_seconds"] == 5
    mock_create_task.assert_called_once_with(cleanup_coro)
    cleanup_task.cancel.assert_called_once()
    mock_engine.dispose.assert_called_once()
