"""Tests for env vars API actor boundary."""

import asyncio
from unittest.mock import MagicMock, patch

from app.api.v1 import env_vars
from app.core.identity import Actor
from app.schemas.env_var import EnvVarCreateRequest, EnvVarUpdateRequest


def test_list_env_vars_uses_actor_user_id():
    """list_env_vars should use actor.user_id when calling the service."""
    actor = Actor(user_id="test-user-123", auth_source="test")
    mock_db = MagicMock()
    mock_result = [{"id": 1, "key": "API_KEY", "is_public": True}]

    with (
        patch.object(
            env_vars.env_var_service, "list_public_env_vars", return_value=mock_result
        ) as mock_list,
        patch.object(env_vars.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(env_vars.list_env_vars(actor=actor, db=mock_db))

        mock_list.assert_called_once()
        call_args = mock_list.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "test-user-123"
        mock_success.assert_called_once_with(
            data=mock_result, message="Env vars retrieved"
        )
        assert result is not None


def test_create_env_var_uses_actor_user_id_and_passes_request():
    """create_env_var should use actor.user_id and pass request unchanged."""
    actor = Actor(user_id="creator-user-456", auth_source="trusted_user_header")
    mock_db = MagicMock()
    request = EnvVarCreateRequest(key="API_KEY", value="secret123")
    mock_result = {"id": 1, "key": "API_KEY", "is_public": False}

    with (
        patch.object(
            env_vars.env_var_service, "create_user_env_var", return_value=mock_result
        ) as mock_create,
        patch.object(env_vars.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            env_vars.create_env_var(request=request, actor=actor, db=mock_db)
        )

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "creator-user-456"
        assert call_args[0][2] is request
        mock_success.assert_called_once_with(
            data=mock_result, message="Env var created"
        )
        assert result is not None


def test_update_env_var_uses_actor_user_id_preserves_env_var_id_and_request():
    """update_env_var should use actor.user_id, preserve env_var_id, and pass request."""
    actor = Actor(user_id="updater-user-789", auth_source="internal_token")
    mock_db = MagicMock()
    request = EnvVarUpdateRequest(value="newvalue")
    env_var_id = 42
    mock_result = {"id": 42, "key": "API_KEY", "is_public": False}

    with (
        patch.object(
            env_vars.env_var_service, "update_user_env_var", return_value=mock_result
        ) as mock_update,
        patch.object(env_vars.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            env_vars.update_env_var(
                env_var_id=env_var_id, request=request, actor=actor, db=mock_db
            )
        )

        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "updater-user-789"
        assert call_args[0][2] == 42
        assert call_args[0][3] is request
        mock_success.assert_called_once_with(
            data=mock_result, message="Env var updated"
        )
        assert result is not None


def test_delete_env_var_uses_actor_user_id_preserves_id_and_returns_correct_response():
    """delete_env_var should use actor.user_id, preserve env_var_id, and return correct response."""
    actor = Actor(user_id="deleter-user-999", auth_source="default_user")
    mock_db = MagicMock()
    env_var_id = 99

    with (
        patch.object(
            env_vars.env_var_service, "delete_user_env_var", return_value=None
        ) as mock_delete,
        patch.object(env_vars.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            env_vars.delete_env_var(env_var_id=env_var_id, actor=actor, db=mock_db)
        )

        mock_delete.assert_called_once()
        call_args = mock_delete.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "deleter-user-999"
        assert call_args[0][2] == 99
        mock_success.assert_called_once_with(data={"id": 99}, message="Env var deleted")
        assert result is not None
