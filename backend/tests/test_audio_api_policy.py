"""Tests for audio API Actor boundary migration.

These tests verify that:
1. The route accepts an Actor dependency rather than user_id
2. file and language are passed through unchanged to audio_transcription_service.transcribe(...)
3. actor.user_id is not passed to the transcription service
4. Response.success exact message/data is preserved
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.audio import audio_transcription_service, router
from app.core.identity import Actor
from app.schemas.audio import AudioTranscriptionResponse


def create_test_actor() -> Actor:
    """Create a test Actor for testing."""
    return Actor(
        user_id="test-user-123",
        tenant_id=None,
        roles=(),
        scopes=(),
        auth_source="test",
    )


@pytest.fixture
def app_with_mocked_actor() -> FastAPI:
    """Create a test FastAPI app with the audio router and mocked Actor."""
    app = FastAPI()

    # Override the get_current_actor dependency
    from app.core.deps import get_current_actor

    app.dependency_overrides[get_current_actor] = create_test_actor
    app.include_router(router)
    return app


@pytest.fixture
def client(app_with_mocked_actor: FastAPI) -> TestClient:
    """Create a test client for the app."""
    return TestClient(app_with_mocked_actor)


@pytest.fixture
def mock_transcribe() -> AsyncMock:
    """Mock the transcription service."""
    with patch.object(
        audio_transcription_service,
        "transcribe",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


class TestAudioActorBoundary:
    """Tests verifying Actor boundary migration for audio transcription."""

    def test_route_signature_uses_actor_type(self) -> None:
        """Verify the route depends on Actor type, not user_id string."""
        import inspect

        from app.api.v1.audio import transcribe_audio

        sig = inspect.signature(transcribe_audio)
        params = sig.parameters

        # Check that _actor parameter exists and has Actor type
        assert "_actor" in params, "Route should have _actor parameter"
        actor_param = params["_actor"]

        # The parameter should have Depends with get_current_actor
        assert actor_param.default is not inspect.Parameter.empty, (
            "_actor should have a default (Depends)"
        )
        # Verify the annotation is Actor
        assert actor_param.annotation is Actor, (
            "_actor parameter should be typed as Actor, not str"
        )

    def test_no_get_current_user_id_import(self) -> None:
        """Verify that get_current_user_id is no longer imported in audio.py."""
        import app.api.v1.audio as audio_module

        # Check that get_current_user_id is not in the module's namespace
        assert not hasattr(audio_module, "get_current_user_id"), (
            "audio.py should not import get_current_user_id"
        )

        # Check the source code doesn't import get_current_user_id
        import inspect

        source = inspect.getsource(audio_module)
        assert "get_current_user_id" not in source, (
            "audio.py source should not reference get_current_user_id"
        )

    def test_file_and_language_passed_unchanged(
        self, client: TestClient, mock_transcribe: AsyncMock
    ) -> None:
        """Verify file and language are passed through to the service unchanged."""
        mock_transcribe.return_value = AudioTranscriptionResponse(text="Hello world")

        # Create a mock audio file
        audio_content = b"fake audio data"
        files = {"file": ("test.webm", audio_content, "audio/webm")}
        data = {"language": "en"}

        response = client.post(
            "/audio/transcriptions",
            files=files,
            data=data,
        )

        assert response.status_code == 200
        mock_transcribe.assert_called_once()

        # Verify the call arguments
        call_kwargs = mock_transcribe.call_args.kwargs
        assert "file" in call_kwargs
        assert "language" in call_kwargs
        assert call_kwargs["language"] == "en"

        # Verify user_id is NOT in the service call
        assert "user_id" not in call_kwargs

    def test_actor_user_id_not_passed_to_service(
        self, client: TestClient, mock_transcribe: AsyncMock
    ) -> None:
        """Verify that actor.user_id is NOT passed to the transcription service."""
        mock_transcribe.return_value = AudioTranscriptionResponse(
            text="Transcribed text"
        )

        audio_content = b"fake audio data"
        files = {"file": ("test.webm", audio_content, "audio/webm")}

        response = client.post(
            "/audio/transcriptions",
            files=files,
        )

        assert response.status_code == 200
        mock_transcribe.assert_called_once()

        call_kwargs = mock_transcribe.call_args.kwargs

        # Critical: user_id must NOT be in the service call
        assert "user_id" not in call_kwargs, (
            "actor.user_id must NOT be passed to audio_transcription_service.transcribe"
        )

    def test_response_message_preserved(
        self, client: TestClient, mock_transcribe: AsyncMock
    ) -> None:
        """Verify Response.success message is preserved exactly."""
        mock_transcribe.return_value = AudioTranscriptionResponse(text="Sample text")

        audio_content = b"fake audio data"
        files = {"file": ("test.webm", audio_content, "audio/webm")}

        response = client.post(
            "/audio/transcriptions",
            files=files,
        )

        assert response.status_code == 200
        json_response = response.json()

        # Verify exact message
        assert json_response["message"] == "Audio transcribed successfully"

        # Verify data structure
        assert json_response["data"] is not None
        assert json_response["data"]["text"] == "Sample text"

    def test_response_data_structure_preserved(
        self, client: TestClient, mock_transcribe: AsyncMock
    ) -> None:
        """Verify Response.success data structure is preserved."""
        expected_text = "This is a transcription result"
        mock_transcribe.return_value = AudioTranscriptionResponse(text=expected_text)

        audio_content = b"fake audio data"
        files = {"file": ("test.webm", audio_content, "audio/webm")}
        data = {"language": "zh"}

        response = client.post(
            "/audio/transcriptions",
            files=files,
            data=data,
        )

        assert response.status_code == 200
        json_response = response.json()

        # Verify response code
        assert json_response["code"] == 0

        # Verify data
        assert json_response["data"]["text"] == expected_text

    def test_service_receives_file_and_language_only(
        self, client: TestClient, mock_transcribe: AsyncMock
    ) -> None:
        """Verify service transcribe receives only file and language parameters."""
        mock_transcribe.return_value = AudioTranscriptionResponse(text="Result")

        audio_content = b"fake audio data"
        files = {"file": ("test.mp3", audio_content, "audio/mpeg")}
        data = {"language": "fr"}

        response = client.post(
            "/audio/transcriptions",
            files=files,
            data=data,
        )

        assert response.status_code == 200
        mock_transcribe.assert_called_once()

        call_kwargs = mock_transcribe.call_args.kwargs

        # Should only have file and language
        assert set(call_kwargs.keys()) == {"file", "language"}, (
            "Service should receive only file and language, no user_id or actor"
        )
