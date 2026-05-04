"""Route-level tests for the skill marketplace API module."""

import asyncio
import importlib.util
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.v1 import skill_marketplace
from app.core.identity import Actor
from app.schemas.skill_marketplace import (
    SkillsMpImportDiscoverRequest,
    SkillsMpSkillItem,
)


def _load_skill_marketplace_module_from_source():
    module_name = "_skill_marketplace_api_import_probe"
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "api"
        / "v1"
        / "skill_marketplace.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)


def test_skill_marketplace_module_import_does_not_initialize_storage_service() -> None:
    with patch(
        "app.services.storage_service.S3StorageService",
        side_effect=AssertionError("storage should be lazy"),
    ):
        module = _load_skill_marketplace_module_from_source()

    assert module.discover_skills_marketplace_import is not None


def test_get_skills_marketplace_status_uses_actor_user_id():
    """get_skills_marketplace_status should use actor.user_id when calling the service."""
    actor = Actor(user_id="status-user-123", auth_source="test")
    mock_db = MagicMock()
    mock_result = {"status": "ok"}

    with (
        patch.object(
            skill_marketplace,
            "get_skillsmp_service",
        ) as mock_get_service,
        patch.object(skill_marketplace.Response, "success") as mock_success,
    ):
        mock_service = MagicMock()
        mock_service.get_marketplace_status.return_value = mock_result
        mock_get_service.return_value = mock_service
        mock_success.return_value = object()

        result = asyncio.run(
            skill_marketplace.get_skills_marketplace_status(actor=actor, db=mock_db)
        )

        mock_service.get_marketplace_status.assert_called_once()
        call_args = mock_service.get_marketplace_status.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "status-user-123"
        mock_success.assert_called_once_with(
            data=mock_result, message="SkillsMP marketplace status loaded"
        )
        assert result is not None


def test_search_skills_marketplace_uses_actor_user_id_and_preserves_query_params():
    """search_skills_marketplace should use actor.user_id and preserve query params."""
    actor = Actor(user_id="search-user-456", auth_source="trusted_user_header")
    mock_db = MagicMock()
    mock_result = {"results": [], "total": 0}

    with (
        patch.object(
            skill_marketplace,
            "get_skillsmp_service",
        ) as mock_get_service,
        patch.object(skill_marketplace.Response, "success") as mock_success,
    ):
        mock_service = MagicMock()
        mock_service.search = AsyncMock(return_value=mock_result)
        mock_get_service.return_value = mock_service
        mock_success.return_value = object()

        result = asyncio.run(
            skill_marketplace.search_skills_marketplace(
                q="test query",
                page=2,
                page_size=25,
                semantic=True,
                actor=actor,
                db=mock_db,
            )
        )

        mock_service.search.assert_called_once()
        call_args = mock_service.search.call_args
        assert call_args[1]["db"] is mock_db
        assert call_args[1]["user_id"] == "search-user-456"
        assert call_args[1]["query"] == "test query"
        assert call_args[1]["page"] == 2
        assert call_args[1]["page_size"] == 25
        assert call_args[1]["semantic"] is True
        mock_success.assert_called_once_with(
            data=mock_result, message="SkillsMP search completed successfully"
        )
        assert result is not None


def test_list_skills_marketplace_recommendations_uses_actor_user_id_and_limit():
    """list_skills_marketplace_recommendations should use actor.user_id and preserve limit."""
    actor = Actor(user_id="recs-user-789", auth_source="internal_token")
    mock_db = MagicMock()
    mock_result = {"recommendations": []}

    with (
        patch.object(
            skill_marketplace,
            "get_skillsmp_service",
        ) as mock_get_service,
        patch.object(skill_marketplace.Response, "success") as mock_success,
    ):
        mock_service = MagicMock()
        mock_service.list_recommendations = AsyncMock(return_value=mock_result)
        mock_get_service.return_value = mock_service
        mock_success.return_value = object()

        result = asyncio.run(
            skill_marketplace.list_skills_marketplace_recommendations(
                limit=15, actor=actor, db=mock_db
            )
        )

        mock_service.list_recommendations.assert_called_once()
        call_args = mock_service.list_recommendations.call_args
        assert call_args[1]["db"] is mock_db
        assert call_args[1]["user_id"] == "recs-user-789"
        assert call_args[1]["limit"] == 15
        mock_success.assert_called_once_with(
            data=mock_result,
            message="SkillsMP recommendations completed successfully",
        )
        assert result is not None


def test_discover_skills_marketplace_import_uses_actor_user_id():
    """discover_skills_marketplace_import should use actor.user_id when calling importer."""
    actor = Actor(user_id="import-user-111", auth_source="default_user")
    mock_db = MagicMock()
    mock_discover_result = MagicMock()
    mock_discover_result.candidates = []
    mock_discover_result.model_copy.return_value = {"discovered": True}
    request = SkillsMpImportDiscoverRequest(
        item=SkillsMpSkillItem(
            external_id="test-id",
            name="test-skill",
            skillsmp_url="https://example.com/skill",
            relative_skill_path="skills/test.md",
        )
    )

    with (
        patch.object(
            skill_marketplace,
            "get_skillsmp_service",
        ) as mock_get_service,
        patch.object(
            skill_marketplace,
            "get_import_service",
        ) as mock_get_importer,
        patch.object(skill_marketplace.Response, "success") as mock_success,
    ):
        mock_service = MagicMock()
        mock_service.build_import_github_url.return_value = "https://github.com/test"
        mock_service.build_import_source.return_value = "archive-source"
        mock_service.match_preselected_relative_path.return_value = "skills/test.md"
        mock_get_service.return_value = mock_service

        mock_importer = MagicMock()
        mock_importer.discover.return_value = mock_discover_result
        mock_get_importer.return_value = mock_importer

        mock_success.return_value = object()

        result = skill_marketplace.discover_skills_marketplace_import(
            request=request, actor=actor, db=mock_db
        )

        mock_importer.discover.assert_called_once()
        call_args = mock_importer.discover.call_args
        assert call_args[0][0] is mock_db
        assert call_args[1]["user_id"] == "import-user-111"
        assert call_args[1]["file"] is None
        assert call_args[1]["github_url"] == "https://github.com/test"
        assert call_args[1]["archive_source_override"] == "archive-source"
        assert result is not None


def test_discover_skills_marketplace_import_preserves_model_copy_shape():
    """discover_skills_marketplace_import should preserve model_copy update shape."""
    actor = Actor(user_id="import-copy-user-222", auth_source="test")
    mock_db = MagicMock()
    mock_discover_result = MagicMock()
    mock_discover_result.candidates = [{"path": "skill.md"}]
    mock_discover_result.model_copy.return_value = {"copied": True}
    request = SkillsMpImportDiscoverRequest(
        item=SkillsMpSkillItem(
            external_id="test-id-2",
            name="another-skill",
            skillsmp_url="https://example.com/skill2",
            relative_skill_path="path/to/skill.md",
        )
    )

    with (
        patch.object(
            skill_marketplace,
            "get_skillsmp_service",
        ) as mock_get_service,
        patch.object(
            skill_marketplace,
            "get_import_service",
        ) as mock_get_importer,
        patch.object(skill_marketplace.Response, "success") as mock_success,
    ):
        mock_service = MagicMock()
        mock_service.build_import_github_url.return_value = "url"
        mock_service.build_import_source.return_value = "source"
        mock_service.match_preselected_relative_path.return_value = "matched/path.md"
        mock_get_service.return_value = mock_service

        mock_importer = MagicMock()
        mock_importer.discover.return_value = mock_discover_result
        mock_get_importer.return_value = mock_importer

        mock_success.return_value = object()

        skill_marketplace.discover_skills_marketplace_import(
            request=request, actor=actor, db=mock_db
        )

        mock_discover_result.model_copy.assert_called_once()
        update_arg = mock_discover_result.model_copy.call_args[1]["update"]
        assert update_arg["preselected_relative_path"] == "matched/path.md"
        assert update_arg["skillsmp_item"] is request.item

        mock_success.assert_called_once_with(
            data={"copied": True}, message="SkillsMP import discovered"
        )
