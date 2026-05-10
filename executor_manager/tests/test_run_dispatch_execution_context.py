from types import SimpleNamespace
from typing import Any

import pytest

from app.services.run_dispatch_execution_context import (
    RunDispatchExecutionContextSettings,
    SettingsRunDispatchExecutionContextProvider,
)


def test_settings_execution_context_provider_builds_executor_callback_context() -> None:
    settings = SimpleNamespace(
        callback_base_url="http://manager.local/",
        callback_token="callback-token",
        executor_task_lease_secret="lease-secret",
        task_timeout_seconds=7200,
    )
    provider = SettingsRunDispatchExecutionContextProvider(settings)

    context = provider.get_context()

    assert context.callback_base_url == "http://manager.local"
    assert context.callback_url == "http://manager.local/api/v1/callback"
    assert context.callback_token == "callback-token"
    assert context.task_lease_secret == "lease-secret"
    assert context.running_lease_seconds == 7200


def test_settings_execution_context_provider_rejects_empty_callback_base_url() -> None:
    settings = SimpleNamespace(
        callback_base_url=" ",
        callback_token="callback-token",
        executor_task_lease_secret="lease-secret",
        task_timeout_seconds=3600,
    )
    provider = SettingsRunDispatchExecutionContextProvider(settings)

    with pytest.raises(ValueError, match="callback_base_url cannot be empty"):
        provider.get_context()


def test_dedicated_executor_task_lease_secret_wins() -> None:
    """Dedicated executor_task_lease_secret should be used when provided."""
    settings = SimpleNamespace(
        callback_base_url="http://manager.local/",
        callback_token="fallback-token",
        executor_task_lease_secret="dedicated-secret",
        task_timeout_seconds=3600,
    )
    provider = SettingsRunDispatchExecutionContextProvider(settings)

    context = provider.get_context()

    assert context.task_lease_secret == "dedicated-secret"


def test_callback_token_fallback_when_lease_secret_empty() -> None:
    """callback_token should be used when executor_task_lease_secret is empty."""
    settings = SimpleNamespace(
        callback_base_url="http://manager.local/",
        callback_token="fallback-token",
        executor_task_lease_secret="",
        task_timeout_seconds=3600,
    )
    provider = SettingsRunDispatchExecutionContextProvider(settings)

    context = provider.get_context()

    assert context.task_lease_secret == "fallback-token"


def test_task_timeout_seconds_none_defaults_to_3600() -> None:
    """task_timeout_seconds=None should default running_lease_seconds to 3600."""
    settings = SimpleNamespace(
        callback_base_url="http://manager.local/",
        callback_token="callback-token",
        executor_task_lease_secret="lease-secret",
        task_timeout_seconds=None,
    )
    provider = SettingsRunDispatchExecutionContextProvider(settings)

    context = provider.get_context()

    assert context.running_lease_seconds == 3600


def test_task_timeout_seconds_below_1_clamps_to_1() -> None:
    """task_timeout_seconds values below 1 should clamp to 1."""
    settings = SimpleNamespace(
        callback_base_url="http://manager.local/",
        callback_token="callback-token",
        executor_task_lease_secret="lease-secret",
        task_timeout_seconds=0,
    )
    provider = SettingsRunDispatchExecutionContextProvider(settings)

    context = provider.get_context()

    assert context.running_lease_seconds == 1


def test_settings_execution_context_protocol_includes_all_required_fields() -> None:
    """RunDispatchExecutionContextSettings should include executor_task_lease_secret and task_timeout_seconds."""
    annotations = RunDispatchExecutionContextSettings.__annotations__

    assert "executor_task_lease_secret" in annotations, (
        "executor_task_lease_secret must be in annotations"
    )
    assert annotations["executor_task_lease_secret"] is not Any, (
        "executor_task_lease_secret annotation must not be Any"
    )

    assert "task_timeout_seconds" in annotations, (
        "task_timeout_seconds must be in annotations"
    )
    assert annotations["task_timeout_seconds"] is not Any, (
        "task_timeout_seconds annotation must not be Any"
    )


def test_constructor_settings_annotation_is_named_protocol_not_any() -> None:
    """SettingsRunDispatchExecutionContextProvider.__init__ settings must be typed as a named Protocol, not Any."""
    import inspect

    sig = inspect.signature(SettingsRunDispatchExecutionContextProvider.__init__)
    param = sig.parameters["settings"]
    annotation = param.annotation

    assert annotation is not Any, "settings annotation must not be Any"
    assert annotation is RunDispatchExecutionContextSettings, (
        "settings annotation must be RunDispatchExecutionContextSettings"
    )
