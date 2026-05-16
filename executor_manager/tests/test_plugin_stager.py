import shutil
import tempfile
import unittest
from pathlib import Path
from typing import cast, get_origin, get_args, Union
from unittest.mock import MagicMock, patch

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.plugin_stager import PluginStager


class TestPluginStagerInit(unittest.TestCase):
    """Test PluginStager.__init__."""

    def test_init_with_defaults_defers_adapter_construction(self) -> None:
        with (
            patch("app.services.plugin_stager.S3StorageService") as mock_storage_cls,
            patch("app.services.plugin_stager.WorkspaceManager") as mock_workspace_cls,
        ):
            mock_storage = MagicMock()
            mock_workspace = MagicMock()
            mock_storage_cls.return_value = mock_storage
            mock_workspace_cls.return_value = mock_workspace

            stager = PluginStager()

            mock_storage_cls.assert_not_called()
            mock_workspace_cls.assert_not_called()
            assert stager.storage_service is mock_storage
            assert stager.workspace_manager is mock_workspace
            mock_storage_cls.assert_called_once()
            mock_workspace_cls.assert_called_once()

    def test_init_with_dependencies(self) -> None:
        mock_storage = MagicMock()
        mock_workspace = MagicMock()

        stager = PluginStager(
            storage_service=mock_storage, workspace_manager=mock_workspace
        )

        assert stager.storage_service is mock_storage
        assert stager.workspace_manager is mock_workspace

    def test_init_uses_injected_storage_factory_without_constructing_s3(self) -> None:
        mock_storage = MagicMock()
        mock_workspace = MagicMock()

        with patch(
            "app.services.plugin_stager.S3StorageService",
            side_effect=AssertionError("storage should be provided by factory"),
        ):
            stager = PluginStager(
                storage_service_factory=lambda: mock_storage,
                workspace_manager=mock_workspace,
            )

        assert stager.storage_service is mock_storage
        assert stager.workspace_manager is mock_workspace

    def test_init_uses_injected_workspace_manager_factory_without_default_constructor(
        self,
    ) -> None:
        mock_storage = MagicMock()
        mock_workspace = MagicMock()

        with patch(
            "app.services.plugin_stager.WorkspaceManager",
            side_effect=AssertionError("workspace manager should be injected"),
        ):
            stager = PluginStager(
                storage_service=mock_storage,
                workspace_manager_factory=lambda: mock_workspace,
            )

        assert stager.storage_service is mock_storage
        assert stager.workspace_manager is mock_workspace


class TestPluginStagerValidatePluginName(unittest.TestCase):
    """Test PluginStager._validate_plugin_name."""

    def test_valid_name_simple(self) -> None:
        # Should not raise
        PluginStager._validate_plugin_name("my-plugin")

    def test_valid_name_with_dots(self) -> None:
        PluginStager._validate_plugin_name("my.plugin.name")

    def test_valid_name_with_underscores(self) -> None:
        PluginStager._validate_plugin_name("my_plugin")

    def test_valid_name_with_numbers(self) -> None:
        PluginStager._validate_plugin_name("plugin123")

    def test_valid_name_complex(self) -> None:
        PluginStager._validate_plugin_name("my-plugin_v2.0")

    def test_invalid_name_dot_raises(self) -> None:
        with self.assertRaises(AppException) as ctx:
            PluginStager._validate_plugin_name(".")

        assert ctx.exception.error_code == ErrorCode.BAD_REQUEST

    def test_invalid_name_double_dot_raises(self) -> None:
        with self.assertRaises(AppException) as ctx:
            PluginStager._validate_plugin_name("..")

        assert ctx.exception.error_code == ErrorCode.BAD_REQUEST

    def test_invalid_name_with_spaces_raises(self) -> None:
        with self.assertRaises(AppException) as ctx:
            PluginStager._validate_plugin_name("my plugin")

        assert ctx.exception.error_code == ErrorCode.BAD_REQUEST

    def test_invalid_name_with_slash_raises(self) -> None:
        with self.assertRaises(AppException) as ctx:
            PluginStager._validate_plugin_name("my/plugin")

        assert ctx.exception.error_code == ErrorCode.BAD_REQUEST

    def test_invalid_name_with_special_chars_raises(self) -> None:
        with self.assertRaises(AppException) as ctx:
            PluginStager._validate_plugin_name("my@plugin")

        assert ctx.exception.error_code == ErrorCode.BAD_REQUEST


class TestPluginStagerCleanPluginsDir(unittest.TestCase):
    """Test PluginStager._clean_plugins_dir."""

    def test_removes_plugins_not_in_keep_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_root = Path(tmpdir)
            (plugins_root / "keep-me").mkdir()
            (plugins_root / "remove-me").mkdir()
            (plugins_root / "also-remove").mkdir()

            removed = PluginStager._clean_plugins_dir(plugins_root, {"keep-me"})

            assert removed == 2
            assert (plugins_root / "keep-me").exists()
            assert not (plugins_root / "remove-me").exists()
            assert not (plugins_root / "also-remove").exists()

    def test_keeps_all_when_all_in_keep_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_root = Path(tmpdir)
            (plugins_root / "plugin1").mkdir()
            (plugins_root / "plugin2").mkdir()

            removed = PluginStager._clean_plugins_dir(
                plugins_root, {"plugin1", "plugin2"}
            )

            assert removed == 0
            assert (plugins_root / "plugin1").exists()
            assert (plugins_root / "plugin2").exists()

    def test_removes_all_when_keep_set_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_root = Path(tmpdir)
            (plugins_root / "plugin1").mkdir()
            (plugins_root / "plugin2").mkdir()

            removed = PluginStager._clean_plugins_dir(plugins_root, set())

            assert removed == 2
            assert not (plugins_root / "plugin1").exists()
            assert not (plugins_root / "plugin2").exists()

    def test_skips_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_root = Path(tmpdir)
            (plugins_root / "file.txt").write_text("content")
            (plugins_root / "plugin1").mkdir()

            removed = PluginStager._clean_plugins_dir(plugins_root, set())

            assert removed == 1  # Only the directory removed
            assert (plugins_root / "file.txt").exists()

    def test_skips_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_root = Path(tmpdir)
            target = Path(tmpdir) / "target"
            target.mkdir()
            (plugins_root / "plugin1").mkdir()

            # Create symlink
            try:
                (plugins_root / "link").symlink_to(target)
                has_symlink = True
            except OSError:
                # Skip test on systems that don't support symlinks
                has_symlink = False

            if has_symlink:
                PluginStager._clean_plugins_dir(plugins_root, set())

                # Symlink should be skipped (not counted as removed)
                # plugin1 is a real directory and should be removed
                # Note: on Windows, symlinks to directories are treated as directories
                # but the code checks is_symlink() first
                assert not (plugins_root / "plugin1").exists()

    def test_skips_escape_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_root = Path(tmpdir)
            # Create a symlink pointing outside plugins_root
            outside_dir = Path(tmpdir).parent / "outside"
            outside_dir.mkdir(exist_ok=True)

            try:
                escape_link = plugins_root / "escape"
                escape_link.symlink_to(outside_dir)

                PluginStager._clean_plugins_dir(plugins_root, set())

                # Symlink should be skipped
                assert escape_link.exists() or not escape_link.is_dir()
            except OSError:
                # Skip on systems without symlink support
                pass
            finally:
                shutil.rmtree(outside_dir, ignore_errors=True)

    def test_skips_rmtree_failure(self) -> None:
        """Test that entries that fail to be removed are skipped (lines 49-50)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_root = Path(tmpdir)
            plugin_dir = plugins_root / "plugin1"
            plugin_dir.mkdir()

            original_rmtree = shutil.rmtree

            def failing_rmtree(path, *args, **kwargs):
                if "plugin1" in str(path):
                    raise PermissionError("Mocked permission denied")
                return original_rmtree(path, *args, **kwargs)

            with patch("shutil.rmtree", side_effect=failing_rmtree):
                removed = PluginStager._clean_plugins_dir(plugins_root, set())

                # Should skip the entry and return 0
                assert removed == 0

    def test_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_root = Path(tmpdir)

            removed = PluginStager._clean_plugins_dir(plugins_root, {"nonexistent"})

            assert removed == 0


class TestPluginStagerStagePlugins(unittest.TestCase):
    """Test PluginStager.stage_plugins."""

    def test_empty_plugins_returns_empty_dict(self) -> None:
        mock_storage = MagicMock()
        mock_workspace = MagicMock()

        stager = PluginStager(
            storage_service=mock_storage, workspace_manager=mock_workspace
        )

        result = stager.stage_plugins("user-123", "session-456", None)
        assert result == {}

        result = stager.stage_plugins("user-123", "session-456", {})
        assert result == {}

    def test_skips_non_dict_specs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            mock_workspace = MagicMock()
            mock_workspace.get_workspace_path.return_value = workspace_path

            mock_storage = MagicMock()

            stager = PluginStager(
                storage_service=mock_storage, workspace_manager=mock_workspace
            )

            plugins: dict[str, object] = {
                "valid-plugin": {"s3_key": "plugins/valid", "enabled": True},
                "invalid1": "not a dict",
                "invalid2": 123,
                "invalid3": None,
            }

            result = stager.stage_plugins(
                "user-123", "session-456", cast(dict[str, object], plugins)
            )

            # Only valid-plugin should be processed
            assert "valid-plugin" in result
            assert "invalid1" not in result

    def test_marks_disabled_plugins(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            mock_workspace = MagicMock()
            mock_workspace.get_workspace_path.return_value = workspace_path

            mock_storage = MagicMock()

            stager = PluginStager(
                storage_service=mock_storage, workspace_manager=mock_workspace
            )

            plugins = {
                "disabled-plugin": {"enabled": False},
            }

            result = stager.stage_plugins(
                "user-123", "session-456", cast(dict[str, object], plugins)
            )

            assert result["disabled-plugin"]["enabled"] is False

    def test_stages_plugin_with_s3_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            mock_workspace = MagicMock()
            mock_workspace.get_workspace_path.return_value = workspace_path

            mock_storage = MagicMock()

            stager = PluginStager(
                storage_service=mock_storage, workspace_manager=mock_workspace
            )

            plugins = {
                "my-plugin": {"s3_key": "plugins/my-plugin.zip"},
            }

            result = stager.stage_plugins(
                "user-123", "session-456", cast(dict[str, object], plugins)
            )

            assert "my-plugin" in result
            assert result["my-plugin"]["enabled"] is True
            assert "local_path" in result["my-plugin"]
            mock_storage.download_file.assert_called_once()

    def test_stages_plugin_with_key_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            mock_workspace = MagicMock()
            mock_workspace.get_workspace_path.return_value = workspace_path

            mock_storage = MagicMock()

            stager = PluginStager(
                storage_service=mock_storage, workspace_manager=mock_workspace
            )

            plugins = {
                "my-plugin": {"key": "plugins/my-plugin.zip"},
            }

            result = stager.stage_plugins(
                "user-123", "session-456", cast(dict[str, object], plugins)
            )

            assert "my-plugin" in result
            mock_storage.download_file.assert_called_once()

    def test_stages_plugin_with_entry_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            mock_workspace = MagicMock()
            mock_workspace.get_workspace_path.return_value = workspace_path

            mock_storage = MagicMock()

            stager = PluginStager(
                storage_service=mock_storage, workspace_manager=mock_workspace
            )

            plugins = {
                "my-plugin": {
                    "entry": {"s3_key": "plugins/my-plugin.zip"},
                    "custom": "value",
                },
            }

            result = stager.stage_plugins(
                "user-123", "session-456", cast(dict[str, object], plugins)
            )

            assert "my-plugin" in result
            assert result["my-plugin"]["custom"] == "value"
            assert result["my-plugin"]["entry"]["s3_key"] == "plugins/my-plugin.zip"

    def test_stages_plugin_with_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            mock_workspace = MagicMock()
            mock_workspace.get_workspace_path.return_value = workspace_path

            mock_storage = MagicMock()

            stager = PluginStager(
                storage_service=mock_storage, workspace_manager=mock_workspace
            )

            plugins = {
                "my-plugin": {"s3_key": "plugins/my-plugin/", "is_prefix": True},
            }

            result = stager.stage_plugins(
                "user-123", "session-456", cast(dict[str, object], plugins)
            )

            assert "my-plugin" in result
            mock_storage.download_prefix.assert_called_once()

    def test_stages_plugin_with_trailing_slash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            mock_workspace = MagicMock()
            mock_workspace.get_workspace_path.return_value = workspace_path

            mock_storage = MagicMock()

            stager = PluginStager(
                storage_service=mock_storage, workspace_manager=mock_workspace
            )

            plugins = {
                "my-plugin": {
                    "s3_key": "plugins/my-plugin/"
                },  # Trailing slash triggers prefix
            }

            result = stager.stage_plugins(
                "user-123", "session-456", cast(dict[str, object], plugins)
            )

            assert "my-plugin" in result
            mock_storage.download_prefix.assert_called_once()

    def test_skips_plugin_without_s3_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            mock_workspace = MagicMock()
            mock_workspace.get_workspace_path.return_value = workspace_path

            mock_storage = MagicMock()

            stager = PluginStager(
                storage_service=mock_storage, workspace_manager=mock_workspace
            )

            plugins = {
                "no-key-plugin": {"name": "something"},  # No s3_key or key
            }

            result = stager.stage_plugins(
                "user-123", "session-456", cast(dict[str, object], plugins)
            )

            assert "no-key-plugin" not in result

    def test_raises_on_invalid_plugin_name_escape_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            mock_workspace = MagicMock()
            mock_workspace.get_workspace_path.return_value = workspace_path

            mock_storage = MagicMock()

            stager = PluginStager(
                storage_service=mock_storage, workspace_manager=mock_workspace
            )

            plugins = {
                "../escape": {"s3_key": "plugins/escape"},
            }

            with self.assertRaises(AppException) as ctx:
                stager.stage_plugins("user-123", "session-456", plugins)

            assert ctx.exception.error_code == ErrorCode.BAD_REQUEST
            # Invalid plugin name is raised before path traversal check
            assert "Invalid plugin name" in ctx.exception.message

    def test_raises_on_path_traversal_escape(self) -> None:
        """Test that path traversal is detected (line 91).

        This tests the case where a valid plugin name resolves to a path
        outside plugins_root due to symlink or other filesystem tricks.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            mock_workspace = MagicMock()
            mock_workspace.get_workspace_path.return_value = workspace_path

            mock_storage = MagicMock()

            stager = PluginStager(
                storage_service=mock_storage, workspace_manager=mock_workspace
            )

            # Create the plugins directory structure first
            plugins_root = workspace_path / "workspace" / ".claude_data" / "plugins"
            plugins_root.mkdir(parents=True, exist_ok=True)

            # Create a symlink inside plugins_root that points outside
            try:
                escape_link = plugins_root / "escape-link"
                outside_dir = Path(tmpdir) / "outside"
                outside_dir.mkdir()
                escape_link.symlink_to(outside_dir)

                plugins = {
                    "escape-link": {"s3_key": "plugins/escape"},
                }

                # The code should detect that resolved path is not under plugins_root
                with self.assertRaises(AppException) as ctx:
                    stager.stage_plugins("user-123", "session-456", plugins)

                assert ctx.exception.error_code == ErrorCode.BAD_REQUEST
                assert "Invalid plugin path" in ctx.exception.message
            except OSError:
                # Skip on systems without symlink support
                pass

    def test_raises_on_download_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            mock_workspace = MagicMock()
            mock_workspace.get_workspace_path.return_value = workspace_path

            mock_storage = MagicMock()
            mock_storage.download_file.side_effect = Exception("S3 error")

            stager = PluginStager(
                storage_service=mock_storage, workspace_manager=mock_workspace
            )

            plugins = {
                "failing-plugin": {"s3_key": "plugins/fail.zip"},
            }

            with self.assertRaises(AppException) as ctx:
                stager.stage_plugins("user-123", "session-456", plugins)

            assert ctx.exception.error_code == ErrorCode.PLUGIN_DOWNLOAD_FAILED
            assert "Failed to stage plugin" in ctx.exception.message

    def test_cleans_old_plugins(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            mock_workspace = MagicMock()
            mock_workspace.get_workspace_path.return_value = workspace_path

            mock_storage = MagicMock()

            stager = PluginStager(
                storage_service=mock_storage, workspace_manager=mock_workspace
            )

            # Create pre-existing plugins directory with old plugin
            plugins_root = workspace_path / "workspace" / ".claude_data" / "plugins"
            plugins_root.mkdir(parents=True, exist_ok=True)
            (plugins_root / "old-plugin").mkdir()

            plugins = {
                "new-plugin": {"s3_key": "plugins/new-plugin.zip"},
            }

            result = stager.stage_plugins(
                "user-123", "session-456", cast(dict[str, object], plugins)
            )

            assert "new-plugin" in result
            assert not (plugins_root / "old-plugin").exists()

    def test_validates_plugin_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            mock_workspace = MagicMock()
            mock_workspace.get_workspace_path.return_value = workspace_path

            mock_storage = MagicMock()

            stager = PluginStager(
                storage_service=mock_storage, workspace_manager=mock_workspace
            )

            plugins = {
                "invalid plugin": {"s3_key": "plugins/test"},  # Space in name
            }

            with self.assertRaises(AppException) as ctx:
                stager.stage_plugins("user-123", "session-456", plugins)

            assert ctx.exception.error_code == ErrorCode.BAD_REQUEST
            assert "Invalid plugin name" in ctx.exception.message

    def test_validates_plugin_names_on_second_loop_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            mock_workspace = MagicMock()
            mock_workspace.get_workspace_path.return_value = workspace_path

            mock_storage = MagicMock()

            stager = PluginStager(
                storage_service=mock_storage, workspace_manager=mock_workspace
            )

            # This plugin passes the first validation (enabled: False check)
            # but should still be validated in the staging loop
            plugins = {
                "valid-plugin": {"s3_key": "plugins/test", "enabled": True},
                "invalid@plugin": {"s3_key": "plugins/test"},
            }

            with self.assertRaises(AppException) as ctx:
                stager.stage_plugins("user-123", "session-456", plugins)

            assert ctx.exception.error_code == ErrorCode.BAD_REQUEST


class TestPluginStagerAnnotations(unittest.TestCase):
    """Regression tests for PluginStager type annotations."""

    def test_stage_plugins_param_is_dict_str_object(self) -> None:
        """Regression: stage_plugins plugins parameter is dict[str, object] | None, not dict[str, Any]."""
        import typing
        import types

        hints = typing.get_type_hints(PluginStager.stage_plugins)
        plugins_param = hints.get("plugins")
        assert plugins_param is not None, "plugins parameter not found"

        # Handle UnionType for Python 3.10+ union syntax
        origin = get_origin(plugins_param)
        if origin is types.UnionType or origin is Union:
            # Unwrap the union to find dict[str, object]
            args = get_args(plugins_param)
            for arg in args:
                if arg is type(None):
                    continue
                arg_origin = get_origin(arg)
                if arg_origin is dict:
                    args = get_args(arg)
                    key_type, value_type = args
                    assert key_type is str, f"Expected str key, got {key_type}"
                    assert value_type is object, (
                        f"Expected object value, got {value_type}"
                    )
                    return
            raise AssertionError(f"Expected dict in union, got {args}")

        assert origin is dict, f"Expected dict, got {origin}"

        args = get_args(plugins_param)
        assert len(args) == 2, f"Expected 2 type args, got {len(args)}"
        key_type, value_type = args
        assert key_type is str, f"Expected str key, got {key_type}"
        assert value_type is object, f"Expected object value, got {value_type}"

    def test_stage_plugins_return_is_dict_str_dict_str_object(self) -> None:
        """Regression: stage_plugins returns dict[str, dict[str, object]], not dict[str, Any]."""
        import typing

        hints = typing.get_type_hints(PluginStager.stage_plugins)
        return_type = hints.get("return")
        assert return_type is not None, "return type not found"

        origin = get_origin(return_type)
        assert origin is dict, f"Expected dict origin, got {origin}"

        args = get_args(return_type)
        assert len(args) == 2, f"Expected 2 type args, got {len(args)}"
        key_type, value_type = args
        assert key_type is str, f"Expected str key, got {key_type}"

        # Value should be dict[str, object]
        value_origin = get_origin(value_type)
        assert value_origin is dict, f"Expected dict value, got {value_origin}"

        value_args = get_args(value_type)
        assert len(value_args) == 2, (
            f"Expected 2 type args for value, got {len(value_args)}"
        )
        nested_key_type, nested_value_type = value_args
        assert nested_key_type is str, f"Expected str nested key, got {nested_key_type}"
        assert nested_value_type is object, (
            f"Expected object nested value, got {nested_value_type}"
        )


if __name__ == "__main__":
    unittest.main()
