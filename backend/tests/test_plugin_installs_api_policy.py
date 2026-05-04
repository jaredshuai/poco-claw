"""Tests for plugin installs API actor boundary."""

import asyncio
from unittest.mock import MagicMock, patch

from app.api.v1 import plugin_installs
from app.core.identity import Actor
from app.schemas.user_plugin_install import (
    UserPluginInstallBulkUpdateRequest,
    UserPluginInstallBulkUpdateResponse,
    UserPluginInstallCreateRequest,
    UserPluginInstallUpdateRequest,
)


def test_list_plugin_installs_uses_actor_user_id():
    """list_plugin_installs should use actor.user_id when calling the service."""
    actor = Actor(user_id="test-user-123", auth_source="test")
    mock_db = MagicMock()
    mock_result = [{"id": 1, "plugin_id": 42, "enabled": True}]

    with (
        patch.object(
            plugin_installs.service, "list_installs", return_value=mock_result
        ) as mock_list,
        patch.object(plugin_installs.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            plugin_installs.list_plugin_installs(actor=actor, db=mock_db)
        )

        mock_list.assert_called_once()
        call_args = mock_list.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "test-user-123"
        mock_success.assert_called_once_with(
            data=mock_result, message="Plugin installs retrieved"
        )
        assert result is not None


def test_create_plugin_install_uses_actor_user_id_and_passes_request():
    """create_plugin_install should use actor.user_id and pass request unchanged."""
    actor = Actor(user_id="creator-user-456", auth_source="trusted_user_header")
    mock_db = MagicMock()
    request = UserPluginInstallCreateRequest(plugin_id=42, enabled=True)
    mock_result = {
        "id": 1,
        "user_id": "creator-user-456",
        "plugin_id": 42,
        "enabled": True,
    }

    with (
        patch.object(
            plugin_installs.service, "create_install", return_value=mock_result
        ) as mock_create,
        patch.object(plugin_installs.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            plugin_installs.create_plugin_install(
                request=request, actor=actor, db=mock_db
            )
        )

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "creator-user-456"
        assert call_args[0][2] is request
        mock_success.assert_called_once_with(
            data=mock_result, message="Plugin install created"
        )
        assert result is not None


def test_bulk_update_plugin_installs_uses_actor_user_id_and_passes_request():
    """bulk_update_plugin_installs should use actor.user_id and pass request unchanged."""
    actor = Actor(user_id="bulk-user-789", auth_source="internal_token")
    mock_db = MagicMock()
    request = UserPluginInstallBulkUpdateRequest(enabled=False, install_ids=[1, 2, 3])
    mock_result = UserPluginInstallBulkUpdateResponse(updated_count=3)

    with (
        patch.object(
            plugin_installs.service, "bulk_update_installs", return_value=mock_result
        ) as mock_bulk,
        patch.object(plugin_installs.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            plugin_installs.bulk_update_plugin_installs(
                request=request, actor=actor, db=mock_db
            )
        )

        mock_bulk.assert_called_once()
        call_args = mock_bulk.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "bulk-user-789"
        assert call_args[0][2] is request
        mock_success.assert_called_once_with(
            data=mock_result, message="Plugin installs updated"
        )
        assert result is not None


def test_update_plugin_install_uses_actor_user_id_preserves_install_id_and_request():
    """update_plugin_install should use actor.user_id, preserve install_id, and pass request."""
    actor = Actor(user_id="updater-user-999", auth_source="default_user")
    mock_db = MagicMock()
    request = UserPluginInstallUpdateRequest(enabled=False)
    install_id = 42
    mock_result = {
        "id": 42,
        "user_id": "updater-user-999",
        "plugin_id": 1,
        "enabled": False,
    }

    with (
        patch.object(
            plugin_installs.service, "update_install", return_value=mock_result
        ) as mock_update,
        patch.object(plugin_installs.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            plugin_installs.update_plugin_install(
                install_id=install_id, request=request, actor=actor, db=mock_db
            )
        )

        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "updater-user-999"
        assert call_args[0][2] == 42
        assert call_args[0][3] is request
        mock_success.assert_called_once_with(
            data=mock_result, message="Plugin install updated"
        )
        assert result is not None


def test_delete_plugin_install_uses_actor_user_id_preserves_id_and_returns_correct_response():
    """delete_plugin_install should use actor.user_id, preserve install_id, and return correct response."""
    actor = Actor(user_id="deleter-user-111", auth_source="test")
    mock_db = MagicMock()
    install_id = 99

    with (
        patch.object(
            plugin_installs.service, "delete_install", return_value=None
        ) as mock_delete,
        patch.object(plugin_installs.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            plugin_installs.delete_plugin_install(
                install_id=install_id, actor=actor, db=mock_db
            )
        )

        mock_delete.assert_called_once()
        call_args = mock_delete.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "deleter-user-111"
        assert call_args[0][2] == 99
        mock_success.assert_called_once_with(
            data={"id": 99}, message="Plugin install deleted"
        )
        assert result is not None
