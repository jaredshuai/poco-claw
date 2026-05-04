"""Tests for MCP servers API actor boundary."""

import asyncio
from unittest.mock import MagicMock, patch

from app.api.v1 import mcp_servers
from app.core.identity import Actor
from app.schemas.mcp_server import McpServerCreateRequest, McpServerUpdateRequest


def test_list_mcp_servers_uses_actor_user_id():
    """list_mcp_servers should use actor.user_id when calling the service."""
    actor = Actor(user_id="test-user-123", auth_source="test")
    mock_db = MagicMock()
    mock_result = [{"id": 1, "name": "test-server"}]

    with (
        patch.object(
            mcp_servers.service, "list_servers", return_value=mock_result
        ) as mock_list,
        patch.object(mcp_servers.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(mcp_servers.list_mcp_servers(actor=actor, db=mock_db))

        mock_list.assert_called_once()
        call_args = mock_list.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "test-user-123"
        mock_success.assert_called_once_with(
            data=mock_result, message="MCP servers retrieved"
        )
        assert result is not None


def test_get_mcp_server_uses_actor_user_id_preserves_server_id():
    """get_mcp_server should use actor.user_id and preserve server_id."""
    actor = Actor(user_id="getter-user-456", auth_source="trusted_user_header")
    mock_db = MagicMock()
    server_id = 42
    mock_result = {"id": 42, "name": "test-server"}

    with (
        patch.object(
            mcp_servers.service, "get_server", return_value=mock_result
        ) as mock_get,
        patch.object(mcp_servers.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            mcp_servers.get_mcp_server(server_id=server_id, actor=actor, db=mock_db)
        )

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "getter-user-456"
        assert call_args[0][2] == 42
        mock_success.assert_called_once_with(
            data=mock_result, message="MCP server retrieved"
        )
        assert result is not None


def test_create_mcp_server_uses_actor_user_id_and_passes_request():
    """create_mcp_server should use actor.user_id and pass request unchanged."""
    actor = Actor(user_id="creator-user-789", auth_source="internal_token")
    mock_db = MagicMock()
    request = McpServerCreateRequest(
        name="new-server", server_config={"url": "https://example.com"}
    )
    mock_result = {
        "id": 1,
        "name": "new-server",
        "owner_user_id": "creator-user-789",
    }

    with (
        patch.object(
            mcp_servers.service, "create_server", return_value=mock_result
        ) as mock_create,
        patch.object(mcp_servers.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            mcp_servers.create_mcp_server(request=request, actor=actor, db=mock_db)
        )

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "creator-user-789"
        assert call_args[0][2] is request
        mock_success.assert_called_once_with(
            data=mock_result, message="MCP server created"
        )
        assert result is not None


def test_update_mcp_server_uses_actor_user_id_preserves_server_id_and_request():
    """update_mcp_server should use actor.user_id, preserve server_id, and pass request."""
    actor = Actor(user_id="updater-user-999", auth_source="default_user")
    mock_db = MagicMock()
    request = McpServerUpdateRequest(name="updated-server")
    server_id = 42
    mock_result = {"id": 42, "name": "updated-server"}

    with (
        patch.object(
            mcp_servers.service, "update_server", return_value=mock_result
        ) as mock_update,
        patch.object(mcp_servers.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            mcp_servers.update_mcp_server(
                server_id=server_id, request=request, actor=actor, db=mock_db
            )
        )

        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "updater-user-999"
        assert call_args[0][2] == 42
        assert call_args[0][3] is request
        mock_success.assert_called_once_with(
            data=mock_result, message="MCP server updated"
        )
        assert result is not None


def test_delete_mcp_server_uses_actor_user_id_preserves_id_and_returns_correct_response():
    """delete_mcp_server should use actor.user_id, preserve server_id, and return correct response."""
    actor = Actor(user_id="deleter-user-111", auth_source="test")
    mock_db = MagicMock()
    server_id = 99

    with (
        patch.object(
            mcp_servers.service, "delete_server", return_value=None
        ) as mock_delete,
        patch.object(mcp_servers.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            mcp_servers.delete_mcp_server(server_id=server_id, actor=actor, db=mock_db)
        )

        mock_delete.assert_called_once()
        call_args = mock_delete.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "deleter-user-111"
        assert call_args[0][2] == 99
        mock_success.assert_called_once_with(
            data={"id": 99}, message="MCP server deleted"
        )
        assert result is not None
