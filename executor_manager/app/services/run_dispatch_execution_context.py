from dataclasses import dataclass
from typing import Protocol

from app.core.settings import resolve_executor_task_lease_secret


@dataclass(frozen=True)
class RunDispatchExecutionContext:
    callback_base_url: str
    callback_url: str
    callback_token: str
    task_lease_secret: str
    running_lease_seconds: int


class RunDispatchExecutionContextProvider(Protocol):
    def get_context(self) -> RunDispatchExecutionContext: ...


class RunDispatchExecutionContextSettings(Protocol):
    """Protocol for settings required by RunDispatchExecutionContextProvider."""

    callback_base_url: str | None
    callback_token: str


class SettingsRunDispatchExecutionContextProvider:
    def __init__(self, settings: RunDispatchExecutionContextSettings) -> None:
        self.settings = settings

    def get_context(self) -> RunDispatchExecutionContext:
        callback_base_url = (self.settings.callback_base_url or "").strip().rstrip("/")
        if not callback_base_url:
            raise ValueError("callback_base_url cannot be empty")

        return RunDispatchExecutionContext(
            callback_base_url=callback_base_url,
            callback_url=f"{callback_base_url}/api/v1/callback",
            callback_token=self.settings.callback_token,
            task_lease_secret=resolve_executor_task_lease_secret(self.settings),
            running_lease_seconds=max(
                1, int(getattr(self.settings, "task_timeout_seconds", 3600))
            ),
        )
