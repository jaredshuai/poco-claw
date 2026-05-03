"""Tests for user MCP installs API actor boundary."""

import asyncio
from unittest.mock import MagicMock, patch

from app.api.v1 import user_mcp_installs
from app.core.identity import Actor
from app.schemas.user_mcp_install import (
    UserMcpInstallBulkUpdateRequest,
    UserMcpInstallBulkUpdateResponse,
    UserMcpInstallCreateRequest,
    UserMcpInstallUpdateRequest,
)


def test_list_user_mcp_installs_uses_actor_user_id():
    """list_user_mcp_installs should use actor.user_id when calling the service."""
    actor = Actor(user_id="test-user-123", auth_source="test")
    mock_db = MagicMock()
    mock_result = [{"id": 1, "server_id": 42, "enabled": True}]

    with (
        patch.object(
            user_mcp_installs.service, "list_installs", return_value=mock_result
        ) as mock_list,
        patch.object(user_mcp_installs.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            user_mcp_installs.list_user_mcp_installs(actor=actor, db=mock_db)
        )

        mock_list.assert_called_once()
        call_args = mock_list.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "test-user-123"
        mock_success.assert_called_once_with(
            data=mock_result, message="MCP installs retrieved"
        )
        assert result is not None


def test_create_user_mcp_install_uses_actor_user_id_and_passes_request():
    """create_user_mcp_install should use actor.user_id and pass request unchanged."""
    actor = Actor(user_id="creator-user-456", auth_source="trusted_user_header")
    mock_db = MagicMock()
    request = UserMcpInstallCreateRequest(server_id=42, enabled=True)
    mock_result = {
        "id": 1,
        "user_id": "creator-user-456",
        "server_id": 42,
        "enabled": True,
    }

    with (
        patch.object(
            user_mcp_installs.service, "create_install", return_value=mock_result
        ) as mock_create,
        patch.object(user_mcp_installs.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            user_mcp_installs.create_user_mcp_install(
                request=request, actor=actor, db=mock_db
            )
        )

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "creator-user-456"
        assert call_args[0][2] is request
        mock_success.assert_called_once_with(
            data=mock_result, message="MCP install created"
        )
        assert result is not None


def test_bulk_update_user_mcp_installs_uses_actor_user_id_and_passes_request():
    """bulk_update_user_mcp_installs should use actor.user_id and pass request unchanged."""
    actor = Actor(user_id="bulk-user-789", auth_source="internal_token")
    mock_db = MagicMock()
    request = UserMcpInstallBulkUpdateRequest(enabled=False, install_ids=[1, 2, 3])
    mock_result = UserMcpInstallBulkUpdateResponse(updated_count=3)

    with (
        patch.object(
            user_mcp_installs.service, "bulk_update_installs", return_value=mock_result
        ) as mock_bulk,
        patch.object(user_mcp_installs.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            user_mcp_installs.bulk_update_user_mcp_installs(
                request=request, actor=actor, db=mock_db
            )
        )

        mock_bulk.assert_called_once()
        call_args = mock_bulk.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "bulk-user-789"
        assert call_args[0][2] is request
        mock_success.assert_called_once_with(
            data=mock_result, message="MCP installs updated"
        )
        assert result is not None


def test_update_user_mcp_install_uses_actor_user_id_preserves_install_id_and_request():
    """update_user_mcp_install should use actor.user_id, preserve install_id, and pass request."""
    actor = Actor(user_id="updater-user-999", auth_source="default_user")
    mock_db = MagicMock()
    request = UserMcpInstallUpdateRequest(enabled=False)
    install_id = 42
    mock_result = {
        "id": 42,
        "user_id": "updater-user-999",
        "server_id": 1,
        "enabled": False,
    }

    with (
        patch.object(
            user_mcp_installs.service, "update_install", return_value=mock_result
        ) as mock_update,
        patch.object(user_mcp_installs.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            user_mcp_installs.update_user_mcp_install(
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
            data=mock_result, message="MCP install updated"
        )
        assert result is not None


def test_delete_user_mcp_install_uses_actor_user_id_preserves_id_and_returns_correct_response():
    """delete_user_mcp_install should use actor.user_id, preserve install_id, and return correct response."""
    actor = Actor(user_id="deleter-user-111", auth_source="test")
    mock_db = MagicMock()
    install_id = 99

    with (
        patch.object(
            user_mcp_installs.service, "delete_install", return_value=None
        ) as mock_delete,
        patch.object(user_mcp_installs.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            user_mcp_installs.delete_user_mcp_install(
                install_id=install_id, actor=actor, db=mock_db
            )
        )

        mock_delete.assert_called_once()
        call_args = mock_delete.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "deleter-user-111"
        assert call_args[0][2] == 99
        mock_success.assert_called_once_with(
            data={"id": 99}, message="MCP install deleted"
        )
        assert result is not None
