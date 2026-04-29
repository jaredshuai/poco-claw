from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

from app.models.agent_session import AgentSession
from app.services.skill_workspace_service import SkillWorkspaceService


class FixedIdGenerator:
    def __init__(self, *ids: str) -> None:
        self._ids = list(ids)

    def new_id(self) -> str:
        return self._ids.pop(0)


def test_create_skill_from_workspace_uses_injected_id_generator_for_version_prefix():
    storage_service = MagicMock()
    storage_service.exists.return_value = True
    storage_service.get_text.side_effect = [
        "---\nname: generated-skill\ndescription: Generated skill\n---\nBody",
        "---\nname: generated-skill\n---\nBody",
    ]
    storage_service.copy_prefix.return_value = 2
    db = MagicMock()
    user_id = "user-123"
    session = cast(
        AgentSession,
        SimpleNamespace(
            id="session-123",
            workspace_files_prefix="workspace/session-123/files",
            workspace_export_status="ready",
            workspace_manifest_key="workspace/session-123/manifest.json",
        ),
    )
    service = SkillWorkspaceService(
        storage_service=storage_service,
        id_generator=FixedIdGenerator("version-fixed"),
    )

    with (
        patch(
            "app.services.skill_workspace_service.SkillRepository.get_by_name",
            return_value=None,
        ),
        patch("app.services.skill_workspace_service.SkillRepository.create") as create,
        patch(
            "app.services.skill_workspace_service.UserSkillInstallRepository.get_by_user_and_skill",
            return_value=None,
        ),
        patch("app.services.skill_workspace_service.UserSkillInstallRepository.create"),
    ):

        def assign_skill_id(_db, skill):
            skill.id = 7
            return skill

        create.side_effect = assign_skill_id

        service.create_skill_from_workspace(
            db,
            user_id=user_id,
            session=session,
            folder_path="skills/generated-skill",
        )

    destination_prefix = "skills/user-123/generated-skill/version-fixed"
    storage_service.copy_prefix.assert_called_once_with(
        source_prefix="workspace/session-123/files/skills/generated-skill",
        destination_prefix=destination_prefix,
    )
    created_skill = create.call_args.args[1]
    assert created_skill.entry == {
        "s3_key": f"{destination_prefix}/",
        "is_prefix": True,
    }
