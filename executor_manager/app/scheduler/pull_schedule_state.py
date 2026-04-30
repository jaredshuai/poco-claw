from functools import lru_cache

from app.scheduler.pull_schedule_config import PullScheduleConfig


class PullScheduleState:
    def __init__(self) -> None:
        self._current_config: PullScheduleConfig | None = None

    def set_current_config(self, config: PullScheduleConfig | None) -> None:
        self._current_config = config

    def get_current_config(self) -> PullScheduleConfig | None:
        return self._current_config


@lru_cache(maxsize=1)
def get_pull_schedule_state() -> PullScheduleState:
    return PullScheduleState()


def set_current_pull_schedule_config(config: PullScheduleConfig | None) -> None:
    get_pull_schedule_state().set_current_config(config)


def get_current_pull_schedule_config() -> PullScheduleConfig | None:
    return get_pull_schedule_state().get_current_config()
