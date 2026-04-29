from unittest.mock import MagicMock, patch

from app.services.pending_skill_creation_service import PendingSkillCreationService


def test_uses_injected_skill_workspace_service_without_constructing_default() -> None:
    storage_service = MagicMock()
    skill_workspace_service = MagicMock()

    with patch(
        "app.services.pending_skill_creation_service.SkillWorkspaceService",
        side_effect=AssertionError("skill workspace service should be injected"),
    ):
        service = PendingSkillCreationService(
            storage_service=storage_service,
            skill_workspace_service=skill_workspace_service,
        )

    assert service.storage_service is storage_service
    assert service.skill_workspace_service is skill_workspace_service


def test_storage_service_uses_injected_factory_without_constructing_s3() -> None:
    storage_service = MagicMock()
    skill_workspace_service = MagicMock()

    with patch(
        "app.services.pending_skill_creation_service.S3StorageService",
        side_effect=AssertionError("storage should be provided by factory"),
    ):
        service = PendingSkillCreationService(
            storage_service_factory=lambda: storage_service,
            skill_workspace_service=skill_workspace_service,
        )

        assert service._storage_service() is storage_service
        assert service._storage_service() is storage_service
