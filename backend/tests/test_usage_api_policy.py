"""Tests for Usage Analytics API Actor boundary.

These tests verify the HTTP adapter boundary correctly:
- Uses Actor.user_id when calling the service
- Passes parsed month/day values unchanged
- Passes timezone unchanged
- Returns the expected success message
"""

from contextlib import contextmanager
from datetime import date
from typing import Any, Coroutine, Generator, TypeVar
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.usage import _parse_day, _parse_month, get_usage_analytics, router
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
def _mock_service(result: Any = None) -> Generator[MagicMock, None, None]:
    """Context manager to mock the usage_analytics_service."""
    with patch("app.api.v1.usage.usage_analytics_service") as mock_service:
        mock_service.get_user_usage_analytics.return_value = result
        yield mock_service


@contextmanager
def _mock_settings() -> Generator[MagicMock, None, None]:
    """Context manager to mock settings with internal_api_token."""
    mock_settings = MagicMock()
    mock_settings.internal_api_token = "test-token"
    mock_settings.trusted_user_header_token = ""
    mock_settings.allow_default_user = False
    with patch("app.core.deps.get_settings", return_value=mock_settings):
        yield mock_settings


class TestGetUsageAnalyticsActorBoundary:
    """Tests for get_usage_analytics endpoint Actor boundary."""

    def test_uses_actor_user_id(self) -> None:
        """Verify actor.user_id is passed to the service."""
        actor = Actor(user_id="test-user-123", auth_source="test")
        mock_db = MagicMock(spec=Session)
        expected_result = {"total_tokens": 100}

        with _mock_service(expected_result) as mock_service:
            response = _run(
                get_usage_analytics(
                    month=None,
                    day=None,
                    timezone="UTC",
                    actor=actor,
                    db=mock_db,
                )
            )

        mock_service.get_user_usage_analytics.assert_called_once()
        call_args = mock_service.get_user_usage_analytics.call_args
        assert call_args[0][1] == "test-user-123"
        assert response.status_code == 200

    def test_passes_parsed_month(self) -> None:
        """Verify parsed month value is passed to the service."""
        actor = Actor(user_id="test-user-456", auth_source="test")
        mock_db = MagicMock(spec=Session)

        with _mock_service() as mock_service:
            _run(
                get_usage_analytics(
                    month="2024-03",
                    day=None,
                    timezone="UTC",
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_service.get_user_usage_analytics.call_args
        assert call_args.kwargs["target_month"] == date(2024, 3, 1)

    def test_passes_parsed_day(self) -> None:
        """Verify parsed day value is passed to the service."""
        actor = Actor(user_id="test-user-789", auth_source="test")
        mock_db = MagicMock(spec=Session)

        with _mock_service() as mock_service:
            _run(
                get_usage_analytics(
                    month=None,
                    day="2024-03-15",
                    timezone="UTC",
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_service.get_user_usage_analytics.call_args
        assert call_args.kwargs["target_day"] == date(2024, 3, 15)

    def test_passes_timezone_unchanged(self) -> None:
        """Verify timezone is passed unchanged to the service."""
        actor = Actor(user_id="test-user-tz", auth_source="test")
        mock_db = MagicMock(spec=Session)

        with _mock_service() as mock_service:
            _run(
                get_usage_analytics(
                    month=None,
                    day=None,
                    timezone="America/New_York",
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_service.get_user_usage_analytics.call_args
        assert call_args.kwargs["timezone_name"] == "America/New_York"

    def test_returns_success_message(self) -> None:
        """Verify Response.success receives the exact message."""
        actor = Actor(user_id="test-user-msg", auth_source="test")
        mock_db = MagicMock(spec=Session)
        expected_result = {"total_tokens": 500}

        with _mock_service(expected_result):
            response = _run(
                get_usage_analytics(
                    month=None,
                    day=None,
                    timezone="UTC",
                    actor=actor,
                    db=mock_db,
                )
            )

        import json

        body = json.loads(bytes(response.body))
        assert body["message"] == "Usage analytics retrieved"
        assert body["data"] == expected_result


class TestParseMonth:
    """Tests for _parse_month helper."""

    def test_parses_valid_month(self) -> None:
        """Valid YYYY-MM format returns correct date."""
        result = _parse_month("2024-03")
        assert result == date(2024, 3, 1)

    def test_returns_none_for_none_input(self) -> None:
        """None input returns None."""
        result = _parse_month(None)
        assert result is None

    def test_raises_for_invalid_format(self) -> None:
        """Invalid format raises AppException."""
        from app.core.errors.exceptions import AppException

        with pytest.raises(AppException):
            _parse_month("invalid")


class TestParseDay:
    """Tests for _parse_day helper."""

    def test_parses_valid_day(self) -> None:
        """Valid YYYY-MM-DD format returns correct date."""
        result = _parse_day("2024-03-15")
        assert result == date(2024, 3, 15)

    def test_returns_none_for_none_input(self) -> None:
        """None input returns None."""
        result = _parse_day(None)
        assert result is None

    def test_raises_for_invalid_format(self) -> None:
        """Invalid format raises AppException."""
        from app.core.errors.exceptions import AppException

        with pytest.raises(AppException):
            _parse_day("invalid")


class TestUsageAnalyticsIntegration:
    """Integration tests via FastAPI test client."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a minimal FastAPI app with the usage router."""
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create a test client."""
        return TestClient(app)

    def test_endpoint_calls_service_with_actor_user_id(
        self, client: TestClient
    ) -> None:
        """Verify the endpoint uses Actor.user_id via the full request path."""
        with _mock_settings(), _mock_service({"total": 100}) as mock_service:
            response = client.get(
                "/usage/analytics",
                headers={
                    "X-User-Id": "integration-user",
                    "X-Internal-Token": "test-token",
                },
            )

        assert response.status_code == 200
        mock_service.get_user_usage_analytics.assert_called_once()
        call_args = mock_service.get_user_usage_analytics.call_args
        assert call_args[0][1] == "integration-user"

    def test_endpoint_passes_month_day_timezone(self, client: TestClient) -> None:
        """Verify month, day, and timezone are passed correctly."""
        with _mock_settings(), _mock_service({"total": 200}) as mock_service:
            response = client.get(
                "/usage/analytics?month=2024-06&day=2024-06-15&timezone=Asia/Tokyo",
                headers={
                    "X-User-Id": "params-user",
                    "X-Internal-Token": "test-token",
                },
            )

        assert response.status_code == 200
        call_args = mock_service.get_user_usage_analytics.call_args
        assert call_args.kwargs["target_month"] == date(2024, 6, 1)
        assert call_args.kwargs["target_day"] == date(2024, 6, 15)
        assert call_args.kwargs["timezone_name"] == "Asia/Tokyo"

    def test_endpoint_returns_expected_message(self, client: TestClient) -> None:
        """Verify the response message is exactly 'Usage analytics retrieved'."""
        with _mock_settings(), _mock_service({"tokens": 999}):
            response = client.get(
                "/usage/analytics",
                headers={
                    "X-User-Id": "message-user",
                    "X-Internal-Token": "test-token",
                },
            )

        assert response.json()["message"] == "Usage analytics retrieved"
