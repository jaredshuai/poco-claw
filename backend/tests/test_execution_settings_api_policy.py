"""Tests for execution settings API actor boundary."""

import asyncio
from unittest.mock import MagicMock, patch

from app.api.v1 import execution_settings
from app.core.identity import Actor
from app.schemas.execution_settings import ExecutionSettings
from app.schemas.permission_policy import (
    PermissionPolicy,
    PermissionPolicyUpdateRequest,
    PermissionRule,
)


def test_get_execution_settings_uses_actor_user_id():
    """get_execution_settings should use actor.user_id when calling service.get_or_create."""
    actor = Actor(user_id="test-user-123", auth_source="test")
    mock_db = MagicMock()
    mock_result = ExecutionSettings()

    with (
        patch.object(
            execution_settings.service, "get_or_create", return_value=mock_result
        ) as mock_get_or_create,
        patch.object(execution_settings.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            execution_settings.get_execution_settings(actor=actor, db=mock_db)
        )

        mock_get_or_create.assert_called_once()
        call_args = mock_get_or_create.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "test-user-123"
        mock_success.assert_called_once_with(
            data=mock_result, message="Execution settings retrieved"
        )
        assert result is not None


def test_update_execution_settings_uses_actor_user_id_and_passes_request():
    """update_execution_settings should use actor.user_id and pass request.settings unchanged."""
    actor = Actor(user_id="updater-user-456", auth_source="trusted_user_header")
    mock_db = MagicMock()
    mock_settings = ExecutionSettings()
    mock_result = ExecutionSettings()

    # Create a request-like object with a settings attribute
    mock_request = MagicMock()
    mock_request.settings = mock_settings

    with (
        patch.object(
            execution_settings.service, "update", return_value=mock_result
        ) as mock_update,
        patch.object(execution_settings.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            execution_settings.update_execution_settings(
                request=mock_request, actor=actor, db=mock_db
            )
        )

        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "updater-user-456"
        assert call_args[0][2] is mock_settings
        mock_success.assert_called_once_with(
            data=mock_result, message="Execution settings updated"
        )
        assert result is not None


def test_get_permission_policy_uses_actor_user_id_and_resolves_policy():
    """get_permission_policy should use actor.user_id, call _resolve_permission_policy, and preserve message."""
    actor = Actor(user_id="policy-user-789", auth_source="internal_token")
    mock_db = MagicMock()
    mock_policy = PermissionPolicy(mode="enforce", default_action="deny")
    mock_result = ExecutionSettings(permissions=mock_policy)

    with (
        patch.object(
            execution_settings.service, "get_or_create", return_value=mock_result
        ) as mock_get_or_create,
        patch.object(execution_settings.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            execution_settings.get_permission_policy(actor=actor, db=mock_db)
        )

        mock_get_or_create.assert_called_once()
        call_args = mock_get_or_create.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "policy-user-789"
        mock_success.assert_called_once_with(
            data=mock_policy, message="Permission policy retrieved"
        )
        assert result is not None


def test_update_permission_policy_uses_actor_user_id_for_both_service_calls():
    """update_permission_policy should use actor.user_id for both get_or_create and update."""
    actor = Actor(user_id="policy-updater-999", auth_source="default_user")
    mock_db = MagicMock()

    # Create real objects to exercise merge logic
    current_policy = PermissionPolicy(
        mode="audit",
        default_action="allow",
        rules=[PermissionRule(id="rule-1", action="allow")],
    )
    current_settings = ExecutionSettings(permissions=current_policy)

    update_request = PermissionPolicyUpdateRequest(mode="enforce")

    updated_policy = PermissionPolicy(
        mode="enforce",
        default_action="allow",
        rules=[PermissionRule(id="rule-1", action="allow")],
    )
    updated_settings = ExecutionSettings(permissions=updated_policy)

    with (
        patch.object(
            execution_settings.service, "get_or_create", return_value=current_settings
        ) as mock_get_or_create,
        patch.object(
            execution_settings.service, "update", return_value=updated_settings
        ) as mock_update,
        patch.object(execution_settings.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            execution_settings.update_permission_policy(
                request=update_request, actor=actor, db=mock_db
            )
        )

        # Verify get_or_create was called with actor.user_id
        mock_get_or_create.assert_called_once()
        get_call_args = mock_get_or_create.call_args
        assert get_call_args[0][0] is mock_db
        assert get_call_args[0][1] == "policy-updater-999"

        # Verify update was called with actor.user_id
        mock_update.assert_called_once()
        update_call_args = mock_update.call_args
        assert update_call_args[0][0] is mock_db
        assert update_call_args[0][1] == "policy-updater-999"

        # Verify success message is preserved
        mock_success.assert_called_once_with(
            data=updated_policy, message="Permission policy updated"
        )
        assert result is not None
