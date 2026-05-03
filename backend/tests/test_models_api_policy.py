"""Tests for models API Actor boundary integration."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.core.identity import Actor
from app.api.v1.models import get_model_config, upsert_provider_models


def _run(coro):
    """Run an async coroutine synchronously for testing."""
    return asyncio.run(coro)


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_model_config_service() -> MagicMock:
    service = MagicMock()
    service.get_model_config = MagicMock()
    service.upsert_provider_models = MagicMock()
    return service


class TestGetModelConfigActorBoundary:
    """Tests for get_model_config endpoint Actor boundary."""

    def test_uses_actor_user_id_when_calling_service(
        self, mock_db, mock_model_config_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-123")
        mock_payload = MagicMock()
        mock_model_config_service.get_model_config.return_value = mock_payload

        monkeypatch.setattr(
            "app.api.v1.models.model_config_service", mock_model_config_service
        )

        with patch("app.api.v1.models.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(get_model_config(actor=actor, db=mock_db))

        mock_model_config_service.get_model_config.assert_called_once_with(
            mock_db, user_id="user-123"
        )
        mock_success.assert_called_once_with(
            data=mock_payload, message="Models retrieved successfully"
        )

    def test_different_actor_user_id_passed_to_service(
        self, mock_db, mock_model_config_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="different-user-456")
        mock_payload = MagicMock()
        mock_model_config_service.get_model_config.return_value = mock_payload

        monkeypatch.setattr(
            "app.api.v1.models.model_config_service", mock_model_config_service
        )

        with patch("app.api.v1.models.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(get_model_config(actor=actor, db=mock_db))

        mock_model_config_service.get_model_config.assert_called_once_with(
            mock_db, user_id="different-user-456"
        )


class TestUpsertProviderModelsActorBoundary:
    """Tests for upsert_provider_models endpoint Actor boundary."""

    def test_uses_actor_user_id_and_preserves_provider_id(
        self, mock_db, mock_model_config_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-789")
        provider_id = "provider-abc"
        mock_request = MagicMock()
        mock_payload = MagicMock()
        mock_model_config_service.upsert_provider_models.return_value = mock_payload

        monkeypatch.setattr(
            "app.api.v1.models.model_config_service", mock_model_config_service
        )

        with patch("app.api.v1.models.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                upsert_provider_models(
                    provider_id=provider_id,
                    request=mock_request,
                    actor=actor,
                    db=mock_db,
                )
            )

        mock_model_config_service.upsert_provider_models.assert_called_once_with(
            mock_db,
            user_id="user-789",
            provider_id="provider-abc",
            request=mock_request,
        )
        mock_success.assert_called_once_with(
            data=mock_payload, message="Provider models updated"
        )

    def test_passes_request_object_unchanged(
        self, mock_db, mock_model_config_service, monkeypatch
    ) -> None:
        actor = Actor(user_id="user-xyz")
        provider_id = "openai"
        mock_request = MagicMock()
        mock_request.models = ["gpt-4", "gpt-3.5-turbo"]
        mock_payload = MagicMock()
        mock_model_config_service.upsert_provider_models.return_value = mock_payload

        monkeypatch.setattr(
            "app.api.v1.models.model_config_service", mock_model_config_service
        )

        with patch("app.api.v1.models.Response.success") as mock_success:
            mock_success.return_value = MagicMock()
            _run(
                upsert_provider_models(
                    provider_id=provider_id,
                    request=mock_request,
                    actor=actor,
                    db=mock_db,
                )
            )

        call_args = mock_model_config_service.upsert_provider_models.call_args
        assert call_args.kwargs["request"] is mock_request
