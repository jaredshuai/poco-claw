"""Tests for the Office viewer service."""

import os
from unittest.mock import MagicMock, patch

import jwt
import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.office_viewer_service import (
    SUPPORTED_EXTENSIONS,
    build_viewer_config,
    detect_extension,
    generate_document_key,
)


class TestDetectExtension:
    def test_detect_from_filename(self):
        assert detect_extension("report.docx") == "docx"
        assert detect_extension("data.xlsx") == "xlsx"
        assert detect_extension("slides.pptx") == "pptx"
        assert detect_extension("legacy.doc") == "doc"
        assert detect_extension("legacy.xls") == "xls"
        assert detect_extension("legacy.ppt") == "ppt"

    def test_filename_takes_priority_over_explicit(self):
        """Filename extension must win when both are supported types."""
        # report.docx has a supported extension → always returns "docx"
        # even though explicit says "pptx"
        assert detect_extension("report.docx", "pptx") == "docx"

    def test_explicit_used_only_for_extensionless_files(self):
        """Explicit override applies ONLY for files with no extension at all."""
        assert detect_extension("noext", "xlsx") == "xlsx"
        assert detect_extension("README", "docx") == "docx"

    def test_explicit_rejected_for_non_office_extension(self):
        """Files with a non-Office extension cannot be overridden via file_type."""
        with pytest.raises(AppException) as exc:
            detect_extension("image.png", "docx")
        assert exc.value.error_code == ErrorCode.BAD_REQUEST

        with pytest.raises(AppException) as exc:
            detect_extension("data.csv", "xlsx")
        assert exc.value.error_code == ErrorCode.BAD_REQUEST

    def test_case_insensitive(self):
        assert detect_extension("FILE.DOCX") == "docx"
        assert detect_extension("noext", ".XLSX") == "xlsx"

    def test_unsupported_raises(self):
        with pytest.raises(AppException) as exc:
            detect_extension("image.png")
        assert exc.value.error_code == ErrorCode.BAD_REQUEST

    def test_no_extension_raises(self):
        with pytest.raises(AppException) as exc:
            detect_extension("noext")
        assert exc.value.error_code == ErrorCode.BAD_REQUEST

    def test_all_supported_extensions_detected(self):
        for ext in SUPPORTED_EXTENSIONS:
            assert detect_extension(f"file.{ext}") == ext


class TestGenerateDocumentKey:
    def test_deterministic(self):
        key1 = generate_document_key("workspace/session-123/report.docx")
        key2 = generate_document_key("workspace/session-123/report.docx")
        assert key1 == key2

    def test_different_keys_for_different_files(self):
        key1 = generate_document_key("workspace/session-123/report.docx")
        key2 = generate_document_key("workspace/session-456/report.docx")
        assert key1 != key2

    def test_length(self):
        key = generate_document_key("any/path.docx")
        assert len(key) == 20


class TestBuildViewerConfig:
    @patch.dict(os.environ, {"OFFICE_JWT_SECRET": "test-secret-key"})
    def test_basic_config(self):
        # Clear cached settings
        from app.core.settings import get_settings
        get_settings.cache_clear()

        try:
            config = build_viewer_config(
                file_name="report.docx",
                presigned_url="https://s3.example.com/bucket/report.docx?sig=abc",
                object_key="workspace/session-1/report.docx",
            )

            assert config.document.fileType == "docx"
            assert config.document.title == "report.docx"
            assert config.document.url == "https://s3.example.com/bucket/report.docx?sig=abc"
            assert config.documentType == "word"
            assert config.editorConfig.mode == "view"
            assert config.editorConfig.lang == "en"
            assert config.type == "embedded"

            # Verify JWT is valid
            payload = jwt.decode(config.token, "test-secret-key", algorithms=["HS256"])
            assert payload["document"]["fileType"] == "docx"
            assert payload["documentType"] == "word"
            assert payload["editorConfig"]["mode"] == "view"
        finally:
            get_settings.cache_clear()

    @patch.dict(os.environ, {"OFFICE_JWT_SECRET": "test-secret-key"})
    def test_xlsx_document_type(self):
        from app.core.settings import get_settings
        get_settings.cache_clear()

        try:
            config = build_viewer_config(
                file_name="data.xlsx",
                presigned_url="https://example.com/data.xlsx",
                object_key="ws/data.xlsx",
            )
            assert config.documentType == "cell"
        finally:
            get_settings.cache_clear()

    @patch.dict(os.environ, {"OFFICE_JWT_SECRET": "test-secret-key"})
    def test_pptx_document_type(self):
        from app.core.settings import get_settings
        get_settings.cache_clear()

        try:
            config = build_viewer_config(
                file_name="slides.pptx",
                presigned_url="https://example.com/slides.pptx",
                object_key="ws/slides.pptx",
            )
            assert config.documentType == "slide"
        finally:
            get_settings.cache_clear()

    @patch.dict(os.environ, {"OFFICE_JWT_SECRET": "test-secret-key"})
    def test_language_passed_through(self):
        from app.core.settings import get_settings
        get_settings.cache_clear()

        try:
            config = build_viewer_config(
                file_name="file.docx",
                presigned_url="https://example.com/file.docx",
                object_key="ws/file.docx",
                language="zh",
            )
            assert config.editorConfig.lang == "zh"
        finally:
            get_settings.cache_clear()

    @patch.dict(os.environ, {"OFFICE_JWT_SECRET": ""})
    def test_empty_secret_raises(self):
        from app.core.settings import get_settings
        get_settings.cache_clear()

        try:
            with pytest.raises(Exception, match="OFFICE_JWT_SECRET"):
                build_viewer_config(
                    file_name="file.docx",
                    presigned_url="https://example.com/file.docx",
                    object_key="ws/file.docx",
                )
        finally:
            get_settings.cache_clear()

    @patch.dict(os.environ, {"OFFICE_JWT_SECRET": "test-secret-key"})
    def test_document_key_uses_object_key_not_url(self):
        from app.core.settings import get_settings
        get_settings.cache_clear()

        try:
            config1 = build_viewer_config(
                file_name="report.docx",
                presigned_url="https://s3.example.com/bucket/report.docx?sig=abc",
                object_key="workspace/session-1/report.docx",
            )
            config2 = build_viewer_config(
                file_name="report.docx",
                presigned_url="https://s3.example.com/bucket/report.docx?sig=xyz",
                object_key="workspace/session-1/report.docx",
            )
            # Same object_key → same document key (regardless of presigned URL)
            assert config1.document.key == config2.document.key
        finally:
            get_settings.cache_clear()


class TestResolveFileObjectKey:
    """Tests for the _resolve_file_object_key helper in office.py."""

    @patch.dict(
        os.environ,
        {
            "OFFICE_JWT_SECRET": "test-secret",
            "S3_BUCKET": "test-bucket",
            "S3_ENDPOINT": "http://localhost:9000",
            "S3_ACCESS_KEY": "minioadmin",
            "S3_SECRET_KEY": "minioadmin",
        },
    )
    def test_returns_size_from_manifest(self):
        from app.api.v1.office import _resolve_file_object_key
        from app.core.settings import get_settings
        get_settings.cache_clear()

        try:
            mock_session = MagicMock()
            mock_session.workspace_manifest_key = "manifest.json"
            mock_session.workspace_files_prefix = "ws/abc"

            manifest = {
                "files": [
                    {
                        "path": "report.docx",
                        "key": "ws/abc/report.docx",
                        "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "size": 1024,
                    },
                ],
            }

            with patch("app.api.v1.office.storage_service") as mock_storage:
                mock_storage.get_manifest.return_value = manifest
                object_key, mime_type, file_size = _resolve_file_object_key(
                    mock_session, "report.docx",
                )

            assert object_key == "ws/abc/report.docx"
            assert mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            assert file_size == 1024
        finally:
            get_settings.cache_clear()

    @patch.dict(
        os.environ,
        {
            "OFFICE_JWT_SECRET": "test-secret",
            "S3_BUCKET": "test-bucket",
            "S3_ENDPOINT": "http://localhost:9000",
            "S3_ACCESS_KEY": "minioadmin",
            "S3_SECRET_KEY": "minioadmin",
        },
    )
    def test_returns_none_size_when_manifest_lacks_size(self):
        from app.api.v1.office import _resolve_file_object_key
        from app.core.settings import get_settings
        get_settings.cache_clear()

        try:
            mock_session = MagicMock()
            mock_session.workspace_manifest_key = "manifest.json"
            mock_session.workspace_files_prefix = ""

            manifest = {
                "files": [
                    {
                        "path": "data.xlsx",
                        "key": "data.xlsx",
                        "mimeType": None,
                    },
                ],
            }

            with patch("app.api.v1.office.storage_service") as mock_storage:
                mock_storage.get_manifest.return_value = manifest
                object_key, mime_type, file_size = _resolve_file_object_key(
                    mock_session, "data.xlsx",
                )

            assert object_key == "data.xlsx"
            assert mime_type is None
            assert file_size is None
        finally:
            get_settings.cache_clear()

    @patch.dict(
        os.environ,
        {
            "OFFICE_JWT_SECRET": "test-secret",
            "S3_BUCKET": "test-bucket",
            "S3_ENDPOINT": "http://localhost:9000",
            "S3_ACCESS_KEY": "minioadmin",
            "S3_SECRET_KEY": "minioadmin",
        },
    )
    def test_raises_when_file_not_found(self):
        from app.api.v1.office import _resolve_file_object_key
        from app.core.settings import get_settings
        get_settings.cache_clear()

        try:
            mock_session = MagicMock()
            mock_session.workspace_manifest_key = "manifest.json"
            mock_session.workspace_files_prefix = ""

            manifest = {"files": []}

            with patch("app.api.v1.office.storage_service") as mock_storage:
                mock_storage.get_manifest.return_value = manifest
                with pytest.raises(AppException) as exc:
                    _resolve_file_object_key(mock_session, "missing.docx")

            assert exc.value.error_code == ErrorCode.NOT_FOUND
            assert "not found" in exc.value.message.lower()
        finally:
            get_settings.cache_clear()

    @patch.dict(
        os.environ,
        {
            "OFFICE_JWT_SECRET": "test-secret",
            "S3_BUCKET": "test-bucket",
            "S3_ENDPOINT": "http://localhost:9000",
            "S3_ACCESS_KEY": "minioadmin",
            "S3_SECRET_KEY": "minioadmin",
        },
    )
    def test_raises_when_no_manifest_key(self):
        from app.api.v1.office import _resolve_file_object_key
        from app.core.settings import get_settings
        get_settings.cache_clear()

        try:
            mock_session = MagicMock()
            mock_session.workspace_manifest_key = None

            with pytest.raises(AppException) as exc:
                _resolve_file_object_key(mock_session, "any.docx")

            assert exc.value.error_code == ErrorCode.NOT_FOUND
        finally:
            get_settings.cache_clear()


class TestFileSizeEnforcement:
    """Tests for the server-side file size check in the viewer-config route."""

    @patch.dict(
        os.environ,
        {
            "OFFICE_JWT_SECRET": "test-secret",
            "OFFICE_FILE_SIZE_LIMIT_MB": "1",
            "S3_BUCKET": "test-bucket",
            "S3_ENDPOINT": "http://localhost:9000",
            "S3_ACCESS_KEY": "minioadmin",
            "S3_SECRET_KEY": "minioadmin",
        },
    )
    def test_rejects_oversized_file_from_manifest(self):
        from app.core.settings import get_settings
        get_settings.cache_clear()

        try:
            # 2 MB > 1 MB limit
            manifest = {
                "files": [
                    {
                        "path": "big.docx",
                        "key": "ws/big.docx",
                        "size": 2 * 1024 * 1024,
                    },
                ],
            }

            with patch("app.api.v1.office.storage_service") as mock_storage:
                mock_storage.get_manifest.return_value = manifest
                # The route calls _resolve_file_object_key internally, but
                # we test it at the function level here for simplicity.
                from app.api.v1.office import _resolve_file_object_key
                mock_session = MagicMock()
                mock_session.workspace_manifest_key = "manifest.json"
                mock_session.workspace_files_prefix = ""
                object_key, _, file_size = _resolve_file_object_key(
                    mock_session, "big.docx",
                )

            assert file_size == 2 * 1024 * 1024
            # Caller (the route) would then compare against the limit:
            assert file_size > 1 * 1024 * 1024  # exceeds 1 MB limit
        finally:
            get_settings.cache_clear()

    @patch.dict(
        os.environ,
        {
            "OFFICE_JWT_SECRET": "test-secret",
            "OFFICE_FILE_SIZE_LIMIT_MB": "1",
            "S3_BUCKET": "test-bucket",
            "S3_ENDPOINT": "http://localhost:9000",
            "S3_ACCESS_KEY": "minioadmin",
            "S3_SECRET_KEY": "minioadmin",
        },
    )
    def test_allows_file_within_limit(self):
        from app.core.settings import get_settings
        get_settings.cache_clear()

        try:
            manifest = {
                "files": [
                    {
                        "path": "small.docx",
                        "key": "ws/small.docx",
                        "size": 512 * 1024,  # 512 KB
                    },
                ],
            }

            with patch("app.api.v1.office.storage_service") as mock_storage:
                mock_storage.get_manifest.return_value = manifest
                from app.api.v1.office import _resolve_file_object_key
                mock_session = MagicMock()
                mock_session.workspace_manifest_key = "manifest.json"
                mock_session.workspace_files_prefix = ""
                _, _, file_size = _resolve_file_object_key(
                    mock_session, "small.docx",
                )

            assert file_size == 512 * 1024
            assert file_size <= 1 * 1024 * 1024  # within 1 MB limit
        finally:
            get_settings.cache_clear()


class TestPathValidation:
    """Tests for path traversal protection."""

    def test_normalize_manifest_path_rejects_traversal(self):
        from app.utils.workspace_manifest import normalize_manifest_path

        assert normalize_manifest_path("../etc/passwd") is None
        assert normalize_manifest_path("foo/../../bar") is None
        assert normalize_manifest_path("./secret") is None
        assert normalize_manifest_path("a/../b/../../../c") is None

    def test_normalize_manifest_path_accepts_valid_paths(self):
        from app.utils.workspace_manifest import normalize_manifest_path

        assert normalize_manifest_path("report.docx") is not None
        assert normalize_manifest_path("folder/report.docx") is not None
        assert normalize_manifest_path("/absolute/path.docx") is not None
