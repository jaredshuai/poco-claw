from datetime import UTC, datetime
import os
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Importing app.api.v1 currently imports modules with S3 clients at module load.
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("S3_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "minioadmin")
os.environ.setdefault("S3_SECRET_KEY", "minioadmin")

from app.core.settings import get_settings

get_settings.cache_clear()

from app.api.v1 import callback, runs  # noqa: E402
from app.core.errors.exception_handlers import setup_exception_handlers  # noqa: E402
from app.schemas.callback import CallbackResponse, CallbackStatus  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    setup_exception_handlers(app, debug=False)
    app.include_router(runs.router)
    app.include_router(callback.router)
    return TestClient(app)


def _settings():
    return SimpleNamespace(internal_api_token="internal-token")


def test_run_claim_requires_internal_token():
    client = _client()
    with patch("app.core.deps.get_settings", return_value=_settings()):
        response = client.post(
            "/runs/claim",
            json={"worker_id": "worker-1", "lease_seconds": 30},
        )

    assert response.status_code == 403


def test_run_claim_accepts_internal_token():
    client = _client()
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch("app.api.v1.runs.run_service.claim_next_run", return_value=None):
            response = client.post(
                "/runs/claim",
                json={"worker_id": "worker-1", "lease_seconds": 30},
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 200


def test_callback_requires_internal_token():
    client = _client()
    with patch("app.core.deps.get_settings", return_value=_settings()):
        response = client.post(
            "/callback",
            json={
                "session_id": "session-1",
                "time": datetime.now(UTC).isoformat(),
                "status": "running",
                "progress": 10,
            },
        )

    assert response.status_code == 403


def test_callback_accepts_internal_token():
    client = _client()
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with patch("app.api.v1.callback.callback_service.process_agent_callback") as fn:
            fn.return_value = CallbackResponse(
                session_id="session-1",
                status="running",
                callback_status=CallbackStatus.RUNNING,
                message=None,
            )
            response = client.post(
                "/callback",
                json={
                    "session_id": "session-1",
                    "time": datetime.now(UTC).isoformat(),
                    "status": "running",
                    "progress": 10,
                },
                headers={"X-Internal-Token": "internal-token"},
            )

    assert response.status_code == 200
