import io
import zipfile
from pathlib import PurePosixPath
from unittest.mock import MagicMock, patch

from app.services.skill_import_service import SkillImportService


class FixedIdGenerator:
    def __init__(self, *ids: str) -> None:
        self._ids = list(ids)

    def new_id(self) -> str:
        return self._ids.pop(0)


def test_upload_archive_uses_injected_id_generator_for_archive_prefix():
    storage_service = MagicMock()
    service = SkillImportService(
        storage_service=storage_service,
        id_generator=FixedIdGenerator("archive-fixed"),
    )

    key = service._upload_archive(
        user_id="user-123",
        filename="skill.zip",
        source_path=None,
        source_bytes=io.BytesIO(b"zip-bytes"),
    )

    assert key == "skill-imports/user-123/archive-fixed/skill.zip"
    storage_service.upload_fileobj.assert_called_once()
    assert storage_service.upload_fileobj.call_args.kwargs["key"] == key


def test_upload_archive_uses_injected_storage_factory_without_constructing_s3():
    storage_service = MagicMock()

    with patch(
        "app.services.skill_import_service.S3StorageService",
        side_effect=AssertionError("storage should be provided by factory"),
    ):
        service = SkillImportService(
            storage_service_factory=lambda: storage_service,
            id_generator=FixedIdGenerator("archive-fixed"),
        )

        key = service._upload_archive(
            user_id="user-123",
            filename="skill.zip",
            source_path=None,
            source_bytes=io.BytesIO(b"zip-bytes"),
        )

    assert key == "skill-imports/user-123/archive-fixed/skill.zip"
    storage_service.upload_fileobj.assert_called_once()


def test_import_one_uses_injected_id_generator_for_skill_version_prefix():
    storage_service = MagicMock()
    service = SkillImportService(
        storage_service=storage_service,
        id_generator=FixedIdGenerator("version-fixed"),
    )
    db = MagicMock()
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, "w") as zipf:
        zipf.writestr(
            "skill/SKILL.md",
            "---\ndescription: Demo skill\n---\nBody",
        )
        zipf.writestr("skill/scripts/run.py", "print('ok')")
    zip_bytes.seek(0)

    with (
        zipfile.ZipFile(zip_bytes) as zipf,
        patch(
            "app.services.skill_import_service.SkillRepository.get_by_name",
            return_value=None,
        ),
        patch("app.services.skill_import_service.SkillRepository.create") as create,
        patch(
            "app.services.skill_import_service.UserSkillInstallRepository.get_by_user_and_skill",
            return_value=None,
        ),
        patch("app.services.skill_import_service.UserSkillInstallRepository.create"),
    ):

        def assign_skill_id(_db, skill):
            skill.id = 23
            return skill

        create.side_effect = assign_skill_id

        service._import_one(
            db=db,
            user_id="user-123",
            zipf=zipf,
            candidate_by_path={
                ".": {
                    "relative_path": ".",
                    "skill_name": "demo-skill",
                    "requires_name": False,
                }
            },
            candidate_dirs=[PurePosixPath(".")],
            relative_path=".",
            name_override=None,
            archive_key="skill-imports/user-123/archive-fixed/skill.zip",
            archive_source={"kind": "zip", "filename": "skill.zip"},
        )

    expected_prefix = "skills/user-123/demo-skill/version-fixed/"
    uploaded_keys = [
        call.kwargs["key"] for call in storage_service.upload_fileobj.call_args_list
    ]
    assert "skills/user-123/demo-skill/version-fixed/SKILL.md" in uploaded_keys
    assert "skills/user-123/demo-skill/version-fixed/scripts/run.py" in uploaded_keys
    created_skill = create.call_args.args[1]
    assert created_skill.description == "Demo skill"
    assert created_skill.entry == {
        "s3_key": expected_prefix,
        "is_prefix": True,
        "source": {
            "archive_key": "skill-imports/user-123/archive-fixed/skill.zip",
            "relative_path": ".",
        },
    }
