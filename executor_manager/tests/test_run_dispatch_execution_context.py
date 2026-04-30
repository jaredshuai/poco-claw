from types import SimpleNamespace

import pytest

from app.services.run_dispatch_execution_context import (
    SettingsRunDispatchExecutionContextProvider,
)


def test_settings_execution_context_provider_builds_executor_callback_context() -> None:
    settings = SimpleNamespace(
        callback_base_url="http://manager.local/",
        callback_token="callback-token",
        executor_task_lease_secret="lease-secret",
    )
    provider = SettingsRunDispatchExecutionContextProvider(settings)

    context = provider.get_context()

    assert context.callback_base_url == "http://manager.local"
    assert context.callback_url == "http://manager.local/api/v1/callback"
    assert context.callback_token == "callback-token"
    assert context.task_lease_secret == "lease-secret"


def test_settings_execution_context_provider_rejects_empty_callback_base_url() -> None:
    settings = SimpleNamespace(
        callback_base_url=" ",
        callback_token="callback-token",
        executor_task_lease_secret="lease-secret",
    )
    provider = SettingsRunDispatchExecutionContextProvider(settings)

    with pytest.raises(ValueError, match="callback_base_url cannot be empty"):
        provider.get_context()
