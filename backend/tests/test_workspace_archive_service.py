from unittest.mock import MagicMock, patch

from app.services.workspace_archive_service import WorkspaceArchiveService


def test_storage_service_uses_injected_factory_without_constructing_s3() -> None:
    storage_service = MagicMock()

    with patch(
        "app.services.workspace_archive_service.S3StorageService",
        side_effect=AssertionError("storage should be provided by factory"),
    ):
        service = WorkspaceArchiveService(
            storage_service_factory=lambda: storage_service,
        )

        assert service._storage_service() is storage_service
        assert service._storage_service() is storage_service
