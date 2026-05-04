"""Tests for subagents API actor boundary."""

import asyncio
from unittest.mock import MagicMock, patch

from app.api.v1 import subagents
from app.core.identity import Actor
from app.schemas.sub_agent import SubAgentCreateRequest, SubAgentUpdateRequest


def test_list_subagents_uses_actor_user_id():
    """list_subagents should use actor.user_id when calling the service."""
    actor = Actor(user_id="test-user-123", auth_source="test")
    mock_db = MagicMock()
    mock_result = [{"id": 1, "name": "test-subagent"}]

    with (
        patch.object(
            subagents.service, "list_subagents", return_value=mock_result
        ) as mock_list,
        patch.object(subagents.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(subagents.list_subagents(actor=actor, db=mock_db))

        mock_list.assert_called_once()
        call_args = mock_list.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "test-user-123"
        mock_success.assert_called_once_with(
            data=mock_result, message="Subagents retrieved"
        )
        assert result is not None


def test_get_subagent_uses_actor_user_id_preserves_subagent_id():
    """get_subagent should use actor.user_id and preserve subagent_id."""
    actor = Actor(user_id="getter-user-456", auth_source="trusted_user_header")
    mock_db = MagicMock()
    subagent_id = 42
    mock_result = {"id": 42, "name": "test-subagent"}

    with (
        patch.object(
            subagents.service, "get_subagent", return_value=mock_result
        ) as mock_get,
        patch.object(subagents.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            subagents.get_subagent(subagent_id=subagent_id, actor=actor, db=mock_db)
        )

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "getter-user-456"
        assert call_args[1]["subagent_id"] == 42
        mock_success.assert_called_once_with(
            data=mock_result, message="Subagent retrieved"
        )
        assert result is not None


def test_create_subagent_uses_actor_user_id_and_passes_request():
    """create_subagent should use actor.user_id and pass request unchanged."""
    actor = Actor(user_id="creator-user-789", auth_source="internal_token")
    mock_db = MagicMock()
    request = SubAgentCreateRequest(name="new-subagent", description="Test agent")
    mock_result = {
        "id": 1,
        "name": "new-subagent",
        "user_id": "creator-user-789",
    }

    with (
        patch.object(
            subagents.service, "create_subagent", return_value=mock_result
        ) as mock_create,
        patch.object(subagents.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            subagents.create_subagent(request=request, actor=actor, db=mock_db)
        )

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "creator-user-789"
        assert call_args[1]["request"] is request
        mock_success.assert_called_once_with(
            data=mock_result, message="Subagent created"
        )
        assert result is not None


def test_update_subagent_uses_actor_user_id_preserves_subagent_id_and_request():
    """update_subagent should use actor.user_id, preserve subagent_id, and pass request."""
    actor = Actor(user_id="updater-user-999", auth_source="default_user")
    mock_db = MagicMock()
    request = SubAgentUpdateRequest(name="updated-subagent")
    subagent_id = 42
    mock_result = {"id": 42, "name": "updated-subagent"}

    with (
        patch.object(
            subagents.service, "update_subagent", return_value=mock_result
        ) as mock_update,
        patch.object(subagents.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            subagents.update_subagent(
                subagent_id=subagent_id, request=request, actor=actor, db=mock_db
            )
        )

        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "updater-user-999"
        assert call_args[1]["subagent_id"] == 42
        assert call_args[1]["request"] is request
        mock_success.assert_called_once_with(
            data=mock_result, message="Subagent updated"
        )
        assert result is not None


def test_delete_subagent_uses_actor_user_id_preserves_id_and_returns_correct_response():
    """delete_subagent should use actor.user_id, preserve subagent_id, and return correct response."""
    actor = Actor(user_id="deleter-user-111", auth_source="test")
    mock_db = MagicMock()
    subagent_id = 99

    with (
        patch.object(
            subagents.service, "delete_subagent", return_value=None
        ) as mock_delete,
        patch.object(subagents.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            subagents.delete_subagent(subagent_id=subagent_id, actor=actor, db=mock_db)
        )

        mock_delete.assert_called_once()
        call_args = mock_delete.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "deleter-user-111"
        assert call_args[1]["subagent_id"] == 99
        mock_success.assert_called_once_with(
            data={"id": 99}, message="Subagent deleted"
        )
        assert result is not None
