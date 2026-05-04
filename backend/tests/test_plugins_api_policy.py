"""Tests for plugins API actor boundary."""

import asyncio
from unittest.mock import MagicMock, patch

from app.api.v1 import plugins
from app.core.identity import Actor
from app.schemas.plugin import PluginCreateRequest, PluginUpdateRequest


def test_list_plugins_uses_actor_user_id():
    """list_plugins should use actor.user_id when calling the service."""
    actor = Actor(user_id="test-user-123", auth_source="test")
    mock_db = MagicMock()
    mock_result = [{"id": 1, "name": "test-plugin"}]

    with (
        patch.object(
            plugins.service, "list_plugins", return_value=mock_result
        ) as mock_list,
        patch.object(plugins.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(plugins.list_plugins(actor=actor, db=mock_db))

        mock_list.assert_called_once()
        call_args = mock_list.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "test-user-123"
        mock_success.assert_called_once_with(
            data=mock_result, message="Plugins retrieved"
        )
        assert result is not None


def test_get_plugin_uses_actor_user_id_preserves_plugin_id():
    """get_plugin should use actor.user_id and preserve plugin_id."""
    actor = Actor(user_id="getter-user-456", auth_source="trusted_user_header")
    mock_db = MagicMock()
    plugin_id = 42
    mock_result = {"id": 42, "name": "test-plugin"}

    with (
        patch.object(
            plugins.service, "get_plugin", return_value=mock_result
        ) as mock_get,
        patch.object(plugins.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            plugins.get_plugin(plugin_id=plugin_id, actor=actor, db=mock_db)
        )

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "getter-user-456"
        assert call_args[0][2] == 42
        mock_success.assert_called_once_with(
            data=mock_result, message="Plugin retrieved"
        )
        assert result is not None


def test_create_plugin_uses_actor_user_id_and_passes_request():
    """create_plugin should use actor.user_id and pass request unchanged."""
    actor = Actor(user_id="creator-user-789", auth_source="internal_token")
    mock_db = MagicMock()
    request = PluginCreateRequest(
        name="new-plugin", entry={"url": "https://example.com"}
    )
    mock_result = {"id": 1, "name": "new-plugin", "owner_user_id": "creator-user-789"}

    with (
        patch.object(
            plugins.service, "create_plugin", return_value=mock_result
        ) as mock_create,
        patch.object(plugins.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            plugins.create_plugin(request=request, actor=actor, db=mock_db)
        )

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "creator-user-789"
        assert call_args[0][2] is request
        mock_success.assert_called_once_with(data=mock_result, message="Plugin created")
        assert result is not None


def test_update_plugin_uses_actor_user_id_preserves_plugin_id_and_request():
    """update_plugin should use actor.user_id, preserve plugin_id, and pass request."""
    actor = Actor(user_id="updater-user-999", auth_source="default_user")
    mock_db = MagicMock()
    request = PluginUpdateRequest(name="updated-plugin")
    plugin_id = 42
    mock_result = {"id": 42, "name": "updated-plugin"}

    with (
        patch.object(
            plugins.service, "update_plugin", return_value=mock_result
        ) as mock_update,
        patch.object(plugins.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            plugins.update_plugin(
                plugin_id=plugin_id, request=request, actor=actor, db=mock_db
            )
        )

        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "updater-user-999"
        assert call_args[0][2] == 42
        assert call_args[0][3] is request
        mock_success.assert_called_once_with(data=mock_result, message="Plugin updated")
        assert result is not None


def test_delete_plugin_uses_actor_user_id_preserves_id_and_returns_correct_response():
    """delete_plugin should use actor.user_id, preserve plugin_id, and return correct response."""
    actor = Actor(user_id="deleter-user-111", auth_source="test")
    mock_db = MagicMock()
    plugin_id = 99

    with (
        patch.object(
            plugins.service, "delete_plugin", return_value=None
        ) as mock_delete,
        patch.object(plugins.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            plugins.delete_plugin(plugin_id=plugin_id, actor=actor, db=mock_db)
        )

        mock_delete.assert_called_once()
        call_args = mock_delete.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "deleter-user-111"
        assert call_args[0][2] == 99
        mock_success.assert_called_once_with(data={"id": 99}, message="Plugin deleted")
        assert result is not None
