"""Tests for the SkillsMP marketplace service."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.marketplace.skillsmp_service import SkillsMpService


def test_constructor_uses_injected_env_var_service() -> None:
    env_var_service = MagicMock()
    env_var_service.get_env_map.return_value = {"SKILLSMP_API_KEY": "secret-key"}
    settings = SimpleNamespace(
        skillsmp_base_url="https://skillsmp.example",
        skillsmp_api_key="",
        skillsmp_timeout_seconds=10,
    )

    with (
        patch(
            "app.services.marketplace.skillsmp_service.get_settings",
            return_value=settings,
        ),
        patch(
            "app.services.marketplace.skillsmp_service.EnvVarService",
            side_effect=AssertionError("env var service should be injected"),
        ),
    ):
        service = SkillsMpService(env_var_service=env_var_service)

    result = service.get_marketplace_status(MagicMock(), user_id="user-123")

    assert result.configured is True
    env_var_service.get_env_map.assert_called_once()
