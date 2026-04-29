import io
import zipfile
from pathlib import PurePosixPath
from unittest.mock import MagicMock, patch

from app.services.plugin_import_service import PluginImportService


class FixedIdGenerator:
    def __init__(self, *ids: str) -> None:
        self._ids = list(ids)

    def new_id(self) -> str:
        return self._ids.pop(0)


def test_upload_archive_uses_injected_id_generator_for_archive_prefix():
    storage_service = MagicMock()
    service = PluginImportService(
        storage_service=storage_service,
        id_generator=FixedIdGenerator("archive-fixed"),
    )

    key = service._upload_archive(
        user_id="user-123",
        filename="plugin.zip",
        source_path=None,
        source_bytes=io.BytesIO(b"zip-bytes"),
    )

    assert key == "plugin-imports/user-123/archive-fixed/plugin.zip"
    storage_service.upload_fileobj.assert_called_once()
    assert storage_service.upload_fileobj.call_args.kwargs["key"] == key


def test_import_one_uses_injected_id_generator_for_plugin_version_prefix():
    storage_service = MagicMock()
    service = PluginImportService(
        storage_service=storage_service,
        id_generator=FixedIdGenerator("version-fixed"),
    )
    db = MagicMock()
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, "w") as zipf:
        zipf.writestr(
            "plugin/.claude-plugin/plugin.json",
            '{"name": "demo-plugin", "version": "1.0.0"}',
        )
        zipf.writestr("plugin/index.js", "export default {}")
    zip_bytes.seek(0)

    with (
        zipfile.ZipFile(zip_bytes) as zipf,
        patch(
            "app.services.plugin_import_service.PluginRepository.get_by_name",
            return_value=None,
        ),
        patch("app.services.plugin_import_service.PluginRepository.create") as create,
        patch(
            "app.services.plugin_import_service.UserPluginInstallRepository.get_by_user_and_plugin",
            return_value=None,
        ),
        patch("app.services.plugin_import_service.UserPluginInstallRepository.create"),
    ):

        def assign_plugin_id(_db, plugin):
            plugin.id = 17
            return plugin

        create.side_effect = assign_plugin_id

        service._import_one(
            db=db,
            user_id="user-123",
            zipf=zipf,
            candidate_by_path={
                ".": {
                    "relative_path": ".",
                    "plugin_name": "demo-plugin",
                    "requires_name": False,
                }
            },
            candidate_dirs=[PurePosixPath(".")],
            relative_path=".",
            name_override=None,
            archive_key="plugin-imports/user-123/archive-fixed/plugin.zip",
            archive_source={"kind": "zip", "filename": "plugin.zip"},
        )

    expected_prefix = "plugins/user-123/demo-plugin/version-fixed/"
    uploaded_keys = [
        call.kwargs["key"] for call in storage_service.upload_fileobj.call_args_list
    ]
    assert "plugins/user-123/demo-plugin/version-fixed/index.js" in uploaded_keys
    created_plugin = create.call_args.args[1]
    assert created_plugin.entry == {
        "s3_key": expected_prefix,
        "is_prefix": True,
        "source": {
            "archive_key": "plugin-imports/user-123/archive-fixed/plugin.zip",
            "relative_path": ".",
        },
    }
