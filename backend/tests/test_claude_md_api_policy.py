"""Tests for CLAUDE.md API actor boundary."""

import asyncio
from collections.abc import Coroutine
from datetime import datetime
from typing import Any, TypeVar
from unittest.mock import MagicMock, patch

from app.api.v1.claude_md import delete_claude_md, get_claude_md, upsert_claude_md
from app.core.identity import Actor
from app.schemas.claude_md import ClaudeMdResponse, ClaudeMdUpsertRequest

T = TypeVar("T")


def _run(coro: Coroutine[Any, Any, T]) -> T:
    """Run async coroutine synchronously."""
    return asyncio.run(coro)


class TestGetClaudeMd:
    """Tests for get_claude_md endpoint."""

    def test_uses_actor_user_id(self) -> None:
        """get_claude_md uses actor.user_id when calling service.get_settings."""
        mock_db = MagicMock()
        mock_actor = Actor(user_id="test-user-123", auth_source="test")
        sample_response = ClaudeMdResponse(
            enabled=True,
            content="# Test CLAUDE.md",
            updated_at=datetime(2026, 5, 3, 12, 0, 0),
        )

        with patch("app.api.v1.claude_md.service") as mock_service:
            mock_service.get_settings.return_value = sample_response

            with patch("app.api.v1.claude_md.Response.success") as mock_success:
                mock_success.return_value = MagicMock()

                _run(get_claude_md(actor=mock_actor, db=mock_db))

                mock_service.get_settings.assert_called_once_with(
                    mock_db, user_id=mock_actor.user_id
                )

    def test_returns_success_response(self) -> None:
        """get_claude_md returns success response with correct message."""
        mock_db = MagicMock()
        mock_actor = Actor(user_id="test-user-123", auth_source="test")
        sample_response = ClaudeMdResponse(
            enabled=True,
            content="# Test CLAUDE.md",
            updated_at=datetime(2026, 5, 3, 12, 0, 0),
        )

        with patch("app.api.v1.claude_md.service") as mock_service:
            mock_service.get_settings.return_value = sample_response

            with patch("app.api.v1.claude_md.Response.success") as mock_success:
                mock_success.return_value = MagicMock()

                _run(get_claude_md(actor=mock_actor, db=mock_db))

                mock_success.assert_called_once_with(
                    data=sample_response, message="CLAUDE.md retrieved"
                )


class TestUpsertClaudeMd:
    """Tests for upsert_claude_md endpoint."""

    def test_uses_actor_user_id(self) -> None:
        """upsert_claude_md uses actor.user_id when calling service.upsert_settings."""
        mock_db = MagicMock()
        mock_actor = Actor(user_id="test-user-123", auth_source="test")
        sample_response = ClaudeMdResponse(
            enabled=True,
            content="# Test CLAUDE.md",
            updated_at=datetime(2026, 5, 3, 12, 0, 0),
        )
        request = ClaudeMdUpsertRequest(enabled=True, content="# Updated")

        with patch("app.api.v1.claude_md.service") as mock_service:
            mock_service.upsert_settings.return_value = sample_response

            with patch("app.api.v1.claude_md.Response.success") as mock_success:
                mock_success.return_value = MagicMock()

                _run(upsert_claude_md(request=request, actor=mock_actor, db=mock_db))

                mock_service.upsert_settings.assert_called_once_with(
                    mock_db, user_id=mock_actor.user_id, request=request
                )

    def test_passes_request_unchanged(self) -> None:
        """upsert_claude_md passes the request object unchanged to service."""
        mock_db = MagicMock()
        mock_actor = Actor(user_id="test-user-123", auth_source="test")
        sample_response = ClaudeMdResponse(
            enabled=True,
            content="# Test CLAUDE.md",
            updated_at=datetime(2026, 5, 3, 12, 0, 0),
        )
        request = ClaudeMdUpsertRequest(enabled=False, content="# New content")

        with patch("app.api.v1.claude_md.service") as mock_service:
            mock_service.upsert_settings.return_value = sample_response

            with patch("app.api.v1.claude_md.Response.success") as mock_success:
                mock_success.return_value = MagicMock()

                _run(upsert_claude_md(request=request, actor=mock_actor, db=mock_db))

                # Verify the exact request object was passed
                call_args = mock_service.upsert_settings.call_args
                assert call_args.kwargs["request"] is request

    def test_returns_success_response(self) -> None:
        """upsert_claude_md returns success response with correct message."""
        mock_db = MagicMock()
        mock_actor = Actor(user_id="test-user-123", auth_source="test")
        sample_response = ClaudeMdResponse(
            enabled=True,
            content="# Test CLAUDE.md",
            updated_at=datetime(2026, 5, 3, 12, 0, 0),
        )
        request = ClaudeMdUpsertRequest(enabled=True, content="# Test")

        with patch("app.api.v1.claude_md.service") as mock_service:
            mock_service.upsert_settings.return_value = sample_response

            with patch("app.api.v1.claude_md.Response.success") as mock_success:
                mock_success.return_value = MagicMock()

                _run(upsert_claude_md(request=request, actor=mock_actor, db=mock_db))

                mock_success.assert_called_once_with(
                    data=sample_response, message="CLAUDE.md updated"
                )


class TestDeleteClaudeMd:
    """Tests for delete_claude_md endpoint."""

    def test_uses_actor_user_id(self) -> None:
        """delete_claude_md uses actor.user_id when calling service.delete_settings."""
        mock_db = MagicMock()
        mock_actor = Actor(user_id="test-user-123", auth_source="test")

        with patch("app.api.v1.claude_md.service") as mock_service:
            mock_service.delete_settings.return_value = None

            with patch("app.api.v1.claude_md.Response.success") as mock_success:
                mock_success.return_value = MagicMock()

                _run(delete_claude_md(actor=mock_actor, db=mock_db))

                mock_service.delete_settings.assert_called_once_with(
                    mock_db, user_id=mock_actor.user_id
                )

    def test_returns_deleted_true(self) -> None:
        """delete_claude_md returns {"deleted": True}."""
        mock_db = MagicMock()
        mock_actor = Actor(user_id="test-user-123", auth_source="test")

        with patch("app.api.v1.claude_md.service") as mock_service:
            mock_service.delete_settings.return_value = None

            with patch("app.api.v1.claude_md.Response.success") as mock_success:
                mock_success.return_value = MagicMock()

                _run(delete_claude_md(actor=mock_actor, db=mock_db))

                mock_success.assert_called_once_with(
                    data={"deleted": True}, message="CLAUDE.md deleted"
                )

    def test_preserves_exact_success_message(self) -> None:
        """delete_claude_md preserves the exact success message."""
        mock_db = MagicMock()
        mock_actor = Actor(user_id="test-user-123", auth_source="test")

        with patch("app.api.v1.claude_md.service") as mock_service:
            mock_service.delete_settings.return_value = None

            with patch("app.api.v1.claude_md.Response.success") as mock_success:
                mock_success.return_value = MagicMock()

                _run(delete_claude_md(actor=mock_actor, db=mock_db))

                call_args = mock_success.call_args
                assert call_args.kwargs["message"] == "CLAUDE.md deleted"
                assert call_args.kwargs["data"] == {"deleted": True}
