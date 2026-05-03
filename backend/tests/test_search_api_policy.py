"""Tests for Search API Actor boundary.

These tests verify the HTTP adapter boundary correctly:
- Uses Actor.user_id when calling SearchService.search
- Passes query parameters unchanged (q, limit_tasks, limit_projects, limit_messages, project_id)
- Returns the expected success message
"""

import uuid
from contextlib import contextmanager
from typing import Any, Coroutine, Generator, TypeVar
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.api.v1.search import global_search
from app.core.identity import Actor

T = TypeVar("T")


def _run(coro: Coroutine[Any, Any, T]) -> T:
    """Execute a coroutine synchronously without asyncio deprecation warnings."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@contextmanager
def _mock_search_service(
    result: Any = None,
) -> Generator[MagicMock, None, None]:
    """Context manager to mock the search_service."""
    with patch("app.api.v1.search.search_service") as mock_service:
        mock_service.search.return_value = result
        yield mock_service


@contextmanager
def _mock_response_success() -> Generator[MagicMock, None, None]:
    """Context manager to mock Response.success."""
    with patch("app.api.v1.search.Response.success") as mock_success:
        mock_success.return_value = MagicMock(status_code=200, body=b'{"data":{}}')
        yield mock_success


class TestGlobalSearchActorBoundary:
    """Tests for global_search endpoint Actor boundary."""

    def test_uses_actor_user_id(self) -> None:
        """Verify actor.user_id is passed to SearchService.search."""
        actor = Actor(user_id="test-user-123", auth_source="test")
        mock_db = MagicMock(spec=Session)
        mock_result = MagicMock()

        with _mock_search_service(mock_result) as mock_service:
            _run(
                global_search(
                    q="test query",
                    limit_tasks=10,
                    limit_projects=5,
                    limit_messages=10,
                    project_id=None,
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_service.search.call_args
        assert call_args[1]["user_id"] == "test-user-123"

    def test_passes_query_parameter_unchanged(self) -> None:
        """Verify q parameter is passed as query unchanged."""
        actor = Actor(user_id="test-user-456", auth_source="test")
        mock_db = MagicMock(spec=Session)
        mock_result = MagicMock()

        with _mock_search_service(mock_result) as mock_service:
            _run(
                global_search(
                    q="search term",
                    limit_tasks=10,
                    limit_projects=5,
                    limit_messages=10,
                    project_id=None,
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_service.search.call_args
        assert call_args[1]["query"] == "search term"

    def test_passes_limit_parameters_unchanged(self) -> None:
        """Verify all limit parameters are passed unchanged."""
        actor = Actor(user_id="test-user-789", auth_source="test")
        mock_db = MagicMock(spec=Session)
        mock_result = MagicMock()

        with _mock_search_service(mock_result) as mock_service:
            _run(
                global_search(
                    q="test",
                    limit_tasks=15,
                    limit_projects=8,
                    limit_messages=12,
                    project_id=None,
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_service.search.call_args
        assert call_args[1]["limit_tasks"] == 15
        assert call_args[1]["limit_projects"] == 8
        assert call_args[1]["limit_messages"] == 12

    def test_passes_project_id_unchanged(self) -> None:
        """Verify project_id is passed unchanged."""
        actor = Actor(user_id="test-user-project", auth_source="test")
        mock_db = MagicMock(spec=Session)
        mock_result = MagicMock()
        project_id = uuid.UUID("12345678-1234-5678-1234-567812345678")

        with _mock_search_service(mock_result) as mock_service:
            _run(
                global_search(
                    q="test",
                    limit_tasks=10,
                    limit_projects=5,
                    limit_messages=10,
                    project_id=project_id,
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_service.search.call_args
        assert call_args[1]["project_id"] == project_id

    def test_returns_success_message(self) -> None:
        """Verify Response.success receives the exact message."""
        actor = Actor(user_id="test-user-msg", auth_source="test")
        mock_db = MagicMock(spec=Session)
        mock_result = MagicMock()

        with _mock_search_service(mock_result):
            with _mock_response_success() as mock_success:
                _run(
                    global_search(
                        q="message test",
                        limit_tasks=10,
                        limit_projects=5,
                        limit_messages=10,
                        project_id=None,
                        actor=actor,
                        db=mock_db,
                    )
                )

        call_kwargs = mock_success.call_args[1]
        assert call_kwargs["message"] == "Search completed successfully"
        assert call_kwargs["data"] is mock_result
