"""Tests for slash commands API actor boundary."""

import asyncio
from unittest.mock import MagicMock, patch

from app.api.v1 import slash_commands
from app.core.identity import Actor
from app.schemas.slash_command import (
    SlashCommandCreateRequest,
    SlashCommandUpdateRequest,
)


def test_list_slash_commands_uses_actor_user_id():
    """list_slash_commands should use actor.user_id when calling the service."""
    actor = Actor(user_id="test-user-123", auth_source="test")
    mock_db = MagicMock()
    mock_result = [{"id": 1, "name": "test-command"}]

    with (
        patch.object(
            slash_commands.service, "list_commands", return_value=mock_result
        ) as mock_list,
        patch.object(slash_commands.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            slash_commands.list_slash_commands(actor=actor, db=mock_db)
        )

        mock_list.assert_called_once()
        call_args = mock_list.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "test-user-123"
        mock_success.assert_called_once_with(
            data=mock_result, message="Slash commands retrieved"
        )
        assert result is not None


def test_list_suggestions_uses_actor_user_id():
    """list_slash_command_suggestions should use actor.user_id and call config_service."""
    actor = Actor(user_id="suggestion-user-456", auth_source="trusted_user_header")
    mock_db = MagicMock()
    mock_result = [{"name": "suggestion-1", "description": "A suggestion"}]

    with (
        patch.object(
            slash_commands.config_service, "list_suggestions", return_value=mock_result
        ) as mock_list,
        patch.object(slash_commands.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            slash_commands.list_slash_command_suggestions(actor=actor, db=mock_db)
        )

        mock_list.assert_called_once()
        call_args = mock_list.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "suggestion-user-456"
        mock_success.assert_called_once_with(
            data=mock_result, message="Slash command suggestions retrieved"
        )
        assert result is not None


def test_get_slash_command_uses_actor_user_id_preserves_command_id():
    """get_slash_command should use actor.user_id and preserve command_id."""
    actor = Actor(user_id="getter-user-789", auth_source="internal_token")
    mock_db = MagicMock()
    command_id = 42
    mock_result = {"id": 42, "name": "test-command"}

    with (
        patch.object(
            slash_commands.service, "get_command", return_value=mock_result
        ) as mock_get,
        patch.object(slash_commands.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            slash_commands.get_slash_command(
                command_id=command_id, actor=actor, db=mock_db
            )
        )

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "getter-user-789"
        assert call_args[1]["command_id"] == 42
        mock_success.assert_called_once_with(
            data=mock_result, message="Slash command retrieved"
        )
        assert result is not None


def test_create_slash_command_uses_actor_user_id_and_passes_request():
    """create_slash_command should use actor.user_id and pass request unchanged."""
    actor = Actor(user_id="creator-user-111", auth_source="default_user")
    mock_db = MagicMock()
    request = SlashCommandCreateRequest(name="new-command", description="Test command")
    mock_result = {
        "id": 1,
        "name": "new-command",
        "user_id": "creator-user-111",
    }

    with (
        patch.object(
            slash_commands.service, "create_command", return_value=mock_result
        ) as mock_create,
        patch.object(slash_commands.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            slash_commands.create_slash_command(
                request=request, actor=actor, db=mock_db
            )
        )

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "creator-user-111"
        assert call_args[1]["request"] is request
        mock_success.assert_called_once_with(
            data=mock_result, message="Slash command created"
        )
        assert result is not None


def test_update_slash_command_uses_actor_user_id_preserves_command_id_and_request():
    """update_slash_command should use actor.user_id, preserve command_id, and pass request."""
    actor = Actor(user_id="updater-user-222", auth_source="test")
    mock_db = MagicMock()
    request = SlashCommandUpdateRequest(name="updated-command")
    command_id = 42
    mock_result = {"id": 42, "name": "updated-command"}

    with (
        patch.object(
            slash_commands.service, "update_command", return_value=mock_result
        ) as mock_update,
        patch.object(slash_commands.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            slash_commands.update_slash_command(
                command_id=command_id, request=request, actor=actor, db=mock_db
            )
        )

        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "updater-user-222"
        assert call_args[1]["command_id"] == 42
        assert call_args[1]["request"] is request
        mock_success.assert_called_once_with(
            data=mock_result, message="Slash command updated"
        )
        assert result is not None


def test_delete_slash_command_uses_actor_user_id_preserves_id_and_returns_correct_response():
    """delete_slash_command should use actor.user_id, preserve command_id, and return correct response."""
    actor = Actor(user_id="deleter-user-333", auth_source="test")
    mock_db = MagicMock()
    command_id = 99

    with (
        patch.object(
            slash_commands.service, "delete_command", return_value=None
        ) as mock_delete,
        patch.object(slash_commands.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            slash_commands.delete_slash_command(
                command_id=command_id, actor=actor, db=mock_db
            )
        )

        mock_delete.assert_called_once()
        call_args = mock_delete.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "deleter-user-333"
        assert call_args[1]["command_id"] == 99
        mock_success.assert_called_once_with(
            data={"id": 99}, message="Slash command deleted"
        )
        assert result is not None
