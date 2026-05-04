"""Tests for skills API actor boundary."""

import asyncio
from unittest.mock import MagicMock, patch

from app.api.v1 import skills
from app.core.identity import Actor
from app.schemas.skill import SkillCreateRequest, SkillUpdateRequest


def test_list_skills_uses_actor_user_id():
    """list_skills should use actor.user_id when calling the service."""
    actor = Actor(user_id="test-user-123", auth_source="test")
    mock_db = MagicMock()
    mock_result = [{"id": 1, "name": "test-skill"}]

    with (
        patch.object(
            skills.service, "list_skills", return_value=mock_result
        ) as mock_list,
        patch.object(skills.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(skills.list_skills(actor=actor, db=mock_db))

        mock_list.assert_called_once()
        call_args = mock_list.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "test-user-123"
        mock_success.assert_called_once_with(
            data=mock_result, message="Skills retrieved"
        )
        assert result is not None


def test_get_skill_uses_actor_user_id_preserves_skill_id():
    """get_skill should use actor.user_id and preserve skill_id."""
    actor = Actor(user_id="getter-user-456", auth_source="trusted_user_header")
    mock_db = MagicMock()
    skill_id = 42
    mock_result = {"id": 42, "name": "test-skill"}

    with (
        patch.object(skills.service, "get_skill", return_value=mock_result) as mock_get,
        patch.object(skills.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            skills.get_skill(skill_id=skill_id, actor=actor, db=mock_db)
        )

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "getter-user-456"
        assert call_args[0][2] == 42
        mock_success.assert_called_once_with(
            data=mock_result, message="Skill retrieved"
        )
        assert result is not None


def test_list_skill_files_uses_actor_user_id_preserves_skill_id():
    """list_skill_files should use actor.user_id and preserve skill_id."""
    actor = Actor(user_id="files-user-789", auth_source="internal_token")
    mock_db = MagicMock()
    skill_id = 10
    mock_result = [{"name": "file1.py", "type": "file"}]

    with (
        patch.object(
            skills.service, "list_skill_files", return_value=mock_result
        ) as mock_list_files,
        patch.object(skills.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            skills.list_skill_files(skill_id=skill_id, actor=actor, db=mock_db)
        )

        mock_list_files.assert_called_once()
        call_args = mock_list_files.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "files-user-789"
        assert call_args[0][2] == 10
        mock_success.assert_called_once_with(
            data=mock_result, message="Skill files retrieved"
        )
        assert result is not None


def test_create_skill_uses_actor_user_id_and_passes_request():
    """create_skill should use actor.user_id and pass request unchanged."""
    actor = Actor(user_id="creator-user-111", auth_source="default_user")
    mock_db = MagicMock()
    request = SkillCreateRequest(name="new-skill", entry={"type": "function"})
    mock_result = {
        "id": 1,
        "name": "new-skill",
        "owner_user_id": "creator-user-111",
    }

    with (
        patch.object(
            skills.service, "create_skill", return_value=mock_result
        ) as mock_create,
        patch.object(skills.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            skills.create_skill(request=request, actor=actor, db=mock_db)
        )

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "creator-user-111"
        assert call_args[0][2] is request
        mock_success.assert_called_once_with(data=mock_result, message="Skill created")
        assert result is not None


def test_update_skill_uses_actor_user_id_preserves_skill_id_and_request():
    """update_skill should use actor.user_id, preserve skill_id, and pass request."""
    actor = Actor(user_id="updater-user-222", auth_source="test")
    mock_db = MagicMock()
    request = SkillUpdateRequest(name="updated-skill")
    skill_id = 42
    mock_result = {"id": 42, "name": "updated-skill"}

    with (
        patch.object(
            skills.service, "update_skill", return_value=mock_result
        ) as mock_update,
        patch.object(skills.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            skills.update_skill(
                skill_id=skill_id, request=request, actor=actor, db=mock_db
            )
        )

        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "updater-user-222"
        assert call_args[0][2] == 42
        assert call_args[0][3] is request
        mock_success.assert_called_once_with(data=mock_result, message="Skill updated")
        assert result is not None


def test_delete_skill_uses_actor_user_id_preserves_id_and_returns_correct_response():
    """delete_skill should use actor.user_id, preserve skill_id, and return correct response."""
    actor = Actor(user_id="deleter-user-333", auth_source="test")
    mock_db = MagicMock()
    skill_id = 99

    with (
        patch.object(skills.service, "delete_skill", return_value=None) as mock_delete,
        patch.object(skills.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            skills.delete_skill(skill_id=skill_id, actor=actor, db=mock_db)
        )

        mock_delete.assert_called_once()
        call_args = mock_delete.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "deleter-user-333"
        assert call_args[0][2] == 99
        mock_success.assert_called_once_with(data={"id": 99}, message="Skill deleted")
        assert result is not None


def test_validate_manifest_uses_actor_user_id_preserves_skill_id():
    """validate_skill_manifest should use actor.user_id and preserve skill_id."""
    actor = Actor(user_id="validator-user-444", auth_source="trusted_user_header")
    mock_db = MagicMock()
    skill_id = 55
    mock_result = {"valid": True, "errors": []}

    with (
        patch.object(
            skills.service, "validate_manifest", return_value=mock_result
        ) as mock_validate,
        patch.object(skills.Response, "success") as mock_success,
    ):
        mock_success.return_value = object()

        result = asyncio.run(
            skills.validate_skill_manifest(skill_id=skill_id, actor=actor, db=mock_db)
        )

        mock_validate.assert_called_once()
        call_args = mock_validate.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "validator-user-444"
        assert call_args[0][2] == 55
        mock_success.assert_called_once_with(
            data=mock_result, message="Skill manifest validated"
        )
        assert result is not None
