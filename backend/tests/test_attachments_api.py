import asyncio
import importlib
import io
import json
import os
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

from fastapi import UploadFile


class FixedIdGenerator:
    def __init__(self, *ids: str) -> None:
        self._ids = list(ids)

    def new_id(self) -> str:
        return self._ids.pop(0)


def _load_attachments_module():
    from app.core.settings import get_settings

    env = {
        "S3_BUCKET": "test-bucket",
        "S3_ENDPOINT": "http://localhost:9000",
        "S3_ACCESS_KEY": "access",
        "S3_SECRET_KEY": "secret",
    }
    with (
        patch.dict(os.environ, env, clear=False),
        patch("app.services.storage_service.boto3.client", return_value=MagicMock()),
    ):
        get_settings.cache_clear()
        module = importlib.import_module("app.api.v1.attachments")
        module = importlib.reload(module)
        get_settings.cache_clear()
        return module


def test_upload_attachment_uses_injected_id_generator_for_storage_key():
    attachments = _load_attachments_module()
    file = cast(
        UploadFile,
        SimpleNamespace(
            filename="report.txt",
            file=io.BytesIO(b"contents"),
            content_type="text/plain",
        ),
    )

    with patch.object(attachments, "storage_service") as storage_service:
        response = asyncio.run(
            attachments.upload_attachment(
                file=file,
                user_id="user-123",
                id_generator=FixedIdGenerator("attachment-fixed"),
            )
        )

    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["data"]["id"] == "attachment-fixed"
    assert body["data"]["source"] == "attachments/user-123/attachment-fixed/file"
    storage_service.upload_fileobj.assert_called_once_with(
        fileobj=file.file,
        key="attachments/user-123/attachment-fixed/file",
        content_type="text/plain",
    )
