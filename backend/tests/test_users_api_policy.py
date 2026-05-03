"""Tests for users API Actor boundary integration."""

import asyncio
from unittest.mock import MagicMock, patch

from app.api.v1 import users
from app.core.identity import Actor


def test_get_current_account_uses_actor_user_id():
    """Verify get_current_account uses actor.user_id for service call."""
    actor = Actor(user_id="test-user-123", auth_source="test")
    mock_payload = {"user_id": "test-user-123", "credits": 100}

    with (
        patch.object(users.user_account_service, "get_me", return_value=mock_payload),
        patch.object(users.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(users.get_current_account(actor=actor, db=MagicMock()))

        mock_success.assert_called_once_with(
            data=mock_payload, message="User account retrieved"
        )
        assert result is not None


def test_get_current_account_passes_actor_user_id_to_service():
    """Verify the exact actor.user_id value is passed to user_account_service.get_me."""
    actor = Actor(user_id="actor-boundary-test-user", auth_source="trusted_user_header")

    with (
        patch.object(users.user_account_service, "get_me") as mock_get_me,
        patch.object(users.Response, "success"),
    ):
        mock_get_me.return_value = {"user_id": "actor-boundary-test-user"}

        asyncio.run(users.get_current_account(actor=actor, db=MagicMock()))

        mock_get_me.assert_called_once()
        call_args = mock_get_me.call_args
        assert call_args[0][1] == "actor-boundary-test-user"


def test_get_current_account_preserves_success_message():
    """Verify the success message remains 'User account retrieved'."""
    actor = Actor(user_id="msg-test-user", auth_source="internal_token")

    with (
        patch.object(
            users.user_account_service,
            "get_me",
            return_value={"user_id": "msg-test-user"},
        ),
        patch.object(users.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        asyncio.run(users.get_current_account(actor=actor, db=MagicMock()))

        mock_success.assert_called_once()
        call_kwargs = mock_success.call_args[1]
        assert call_kwargs["message"] == "User account retrieved"


def test_get_current_account_passes_service_payload_unchanged():
    """Verify the service payload is passed unchanged to Response.success."""
    actor = Actor(user_id="payload-test-user", auth_source="default_user")
    expected_payload = {
        "user_id": "payload-test-user",
        "email": "test@example.com",
        "credits": 500,
        "created_at": "2026-01-01T00:00:00Z",
    }

    with (
        patch.object(
            users.user_account_service, "get_me", return_value=expected_payload
        ),
        patch.object(users.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        asyncio.run(users.get_current_account(actor=actor, db=MagicMock()))

        mock_success.assert_called_once()
        call_kwargs = mock_success.call_args[1]
        assert call_kwargs["data"] is expected_payload
