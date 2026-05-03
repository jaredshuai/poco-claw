"""Tests for Capability Recommendations API Actor boundary.

These tests verify the HTTP adapter boundary correctly:
- Uses Actor.user_id when calling CapabilityRecommendationService.recommend
- Passes request parameters unchanged (query, limit)
- Returns the expected success message
"""

from contextlib import contextmanager
from typing import Any, Coroutine, Generator, TypeVar
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.orm import Session

from app.api.v1.capability_recommendations import recommend_capabilities
from app.core.identity import Actor
from app.schemas.capability_recommendation import CapabilityRecommendationRequest

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
def _mock_recommend_service(
    result: Any = None,
) -> Generator[MagicMock, None, None]:
    """Context manager to mock the service.recommend."""
    with patch("app.api.v1.capability_recommendations.service") as mock_service:
        mock_service.recommend = AsyncMock(return_value=result)
        yield mock_service


@contextmanager
def _mock_response_success() -> Generator[MagicMock, None, None]:
    """Context manager to mock Response.success."""
    with patch(
        "app.api.v1.capability_recommendations.Response.success"
    ) as mock_success:
        mock_success.return_value = MagicMock(status_code=200, body=b'{"data":{}}')
        yield mock_success


class TestRecommendCapabilitiesActorBoundary:
    """Tests for recommend_capabilities endpoint Actor boundary."""

    def test_uses_actor_user_id(self) -> None:
        """Verify actor.user_id is passed to CapabilityRecommendationService.recommend."""
        actor = Actor(user_id="test-user-123", auth_source="test")
        mock_db = MagicMock(spec=Session)
        mock_result = MagicMock()
        request = CapabilityRecommendationRequest(query="test query", limit=5)

        with _mock_recommend_service(mock_result) as mock_service:
            _run(
                recommend_capabilities(
                    request=request,
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_service.recommend.call_args
        assert call_args[1]["user_id"] == "test-user-123"

    def test_passes_query_parameter_unchanged(self) -> None:
        """Verify request.query is passed as query unchanged."""
        actor = Actor(user_id="test-user-456", auth_source="test")
        mock_db = MagicMock(spec=Session)
        mock_result = MagicMock()
        request = CapabilityRecommendationRequest(query="search capabilities", limit=3)

        with _mock_recommend_service(mock_result) as mock_service:
            _run(
                recommend_capabilities(
                    request=request,
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_service.recommend.call_args
        assert call_args[1]["query"] == "search capabilities"

    def test_passes_limit_parameter_unchanged(self) -> None:
        """Verify request.limit is passed unchanged."""
        actor = Actor(user_id="test-user-789", auth_source="test")
        mock_db = MagicMock(spec=Session)
        mock_result = MagicMock()
        request = CapabilityRecommendationRequest(query="test", limit=7)

        with _mock_recommend_service(mock_result) as mock_service:
            _run(
                recommend_capabilities(
                    request=request,
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_service.recommend.call_args
        assert call_args[1]["limit"] == 7

    def test_passes_db_unchanged(self) -> None:
        """Verify db session is passed unchanged."""
        actor = Actor(user_id="test-user-db", auth_source="test")
        mock_db = MagicMock(spec=Session)
        mock_result = MagicMock()
        request = CapabilityRecommendationRequest(query="test", limit=3)

        with _mock_recommend_service(mock_result) as mock_service:
            _run(
                recommend_capabilities(
                    request=request,
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_service.recommend.call_args
        assert call_args[1]["db"] is mock_db

    def test_returns_success_message(self) -> None:
        """Verify Response.success receives the exact message."""
        actor = Actor(user_id="test-user-msg", auth_source="test")
        mock_db = MagicMock(spec=Session)
        mock_result = MagicMock()
        request = CapabilityRecommendationRequest(query="message test", limit=5)

        with _mock_recommend_service(mock_result):
            with _mock_response_success() as mock_success:
                _run(
                    recommend_capabilities(
                        request=request,
                        actor=actor,
                        db=mock_db,
                    )
                )

        call_kwargs = mock_success.call_args[1]
        assert call_kwargs["message"] == "Capability recommendations retrieved"
        assert call_kwargs["data"] is mock_result
