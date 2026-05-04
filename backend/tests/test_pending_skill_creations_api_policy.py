"""Tests for pending skill creations API actor boundary."""

import uuid
from unittest.mock import MagicMock, patch

from app.api.v1 import pending_skill_creations
from app.core.identity import Actor
from app.schemas.pending_skill_creation import (
    PendingSkillCreationCancelRequest,
    PendingSkillCreationConfirmRequest,
)


def test_list_pending_skill_creations_uses_actor_user_id():
    """list_pending_skill_creations should use actor.user_id when calling the service."""
    actor = Actor(user_id="test-user-123", auth_source="test")
    mock_db = MagicMock()
    mock_result = [{"id": uuid.uuid4(), "detected_name": "test-skill"}]

    with (
        patch.object(
            pending_skill_creations.service,
            "list_pending_for_user",
            return_value=mock_result,
        ) as mock_list,
        patch.object(pending_skill_creations.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = pending_skill_creations.list_pending_skill_creations(
            actor=actor, db=mock_db
        )

        mock_list.assert_called_once()
        call_args = mock_list.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "test-user-123"
        mock_success.assert_called_once_with(
            data=mock_result, message="Pending skill creations retrieved"
        )
        assert result is not None


def test_list_pending_skill_creations_passes_session_id_unchanged():
    """list_pending_skill_creations should pass session_id through unchanged."""
    actor = Actor(user_id="test-user-456", auth_source="test")
    mock_db = MagicMock()
    session_id = uuid.uuid4()
    mock_result = []

    with (
        patch.object(
            pending_skill_creations.service,
            "list_pending_for_user",
            return_value=mock_result,
        ) as mock_list,
        patch.object(pending_skill_creations.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = pending_skill_creations.list_pending_skill_creations(
            session_id=session_id, actor=actor, db=mock_db
        )

        mock_list.assert_called_once()
        call_args = mock_list.call_args
        assert call_args[1]["session_id"] == session_id
        assert result is not None


def test_get_pending_skill_creation_uses_actor_user_id_preserves_creation_id():
    """get_pending_skill_creation should use actor.user_id and preserve creation_id."""
    actor = Actor(user_id="getter-user-789", auth_source="trusted_user_header")
    mock_db = MagicMock()
    creation_id = uuid.uuid4()
    mock_result = {"id": creation_id, "detected_name": "test-skill"}

    with (
        patch.object(
            pending_skill_creations.service,
            "get_creation",
            return_value=mock_result,
        ) as mock_get,
        patch.object(pending_skill_creations.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = pending_skill_creations.get_pending_skill_creation(
            creation_id=creation_id, actor=actor, db=mock_db
        )

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "getter-user-789"
        assert call_args[1]["creation_id"] == creation_id
        mock_success.assert_called_once_with(
            data=mock_result, message="Pending skill creation retrieved"
        )
        assert result is not None


def test_confirm_pending_skill_creation_uses_actor_user_id_and_passes_request():
    """confirm_pending_skill_creation should use actor.user_id and pass request unchanged."""
    actor = Actor(user_id="confirmer-user-111", auth_source="internal_token")
    mock_db = MagicMock()
    creation_id = uuid.uuid4()
    request = PendingSkillCreationConfirmRequest(
        resolved_name="confirmed-skill", description="A confirmed skill"
    )
    mock_result = {"id": creation_id, "status": "confirmed"}

    with (
        patch.object(
            pending_skill_creations.service,
            "confirm",
            return_value=mock_result,
        ) as mock_confirm,
        patch.object(pending_skill_creations.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = pending_skill_creations.confirm_pending_skill_creation(
            creation_id=creation_id, request=request, actor=actor, db=mock_db
        )

        mock_confirm.assert_called_once()
        call_args = mock_confirm.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "confirmer-user-111"
        assert call_args[1]["creation_id"] == creation_id
        assert call_args[1]["request"] is request
        mock_success.assert_called_once_with(
            data=mock_result, message="Pending skill creation confirmed"
        )
        assert result is not None


def test_cancel_pending_skill_creation_uses_actor_user_id_and_passes_reason():
    """cancel_pending_skill_creation should use actor.user_id and pass request.reason to service.cancel."""
    actor = Actor(user_id="canceler-user-222", auth_source="default_user")
    mock_db = MagicMock()
    creation_id = uuid.uuid4()
    request = PendingSkillCreationCancelRequest(reason="Not needed anymore")
    mock_result = {"id": creation_id, "status": "canceled"}

    with (
        patch.object(
            pending_skill_creations.service,
            "cancel",
            return_value=mock_result,
        ) as mock_cancel,
        patch.object(pending_skill_creations.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = pending_skill_creations.cancel_pending_skill_creation(
            creation_id=creation_id, request=request, actor=actor, db=mock_db
        )

        mock_cancel.assert_called_once()
        call_args = mock_cancel.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "canceler-user-222"
        assert call_args[1]["creation_id"] == creation_id
        assert call_args[1]["reason"] == "Not needed anymore"
        mock_success.assert_called_once_with(
            data=mock_result, message="Pending skill creation canceled"
        )
        assert result is not None


def test_cancel_pending_skill_creation_with_none_reason():
    """cancel_pending_skill_creation should pass None reason when not provided."""
    actor = Actor(user_id="canceler-user-333", auth_source="test")
    mock_db = MagicMock()
    creation_id = uuid.uuid4()
    request = PendingSkillCreationCancelRequest(reason=None)
    mock_result = {"id": creation_id, "status": "canceled"}

    with (
        patch.object(
            pending_skill_creations.service,
            "cancel",
            return_value=mock_result,
        ) as mock_cancel,
        patch.object(pending_skill_creations.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = pending_skill_creations.cancel_pending_skill_creation(
            creation_id=creation_id, request=request, actor=actor, db=mock_db
        )

        mock_cancel.assert_called_once()
        call_args = mock_cancel.call_args
        assert call_args[1]["reason"] is None
        assert result is not None
