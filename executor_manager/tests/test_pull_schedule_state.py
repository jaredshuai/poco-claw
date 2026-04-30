"""Tests for scheduler/pull_schedule_state.py."""

from app.scheduler.pull_schedule_config import PullScheduleConfig


def test_pull_schedule_state_has_no_module_current_config_global() -> None:
    from app.scheduler import pull_schedule_state

    assert not hasattr(pull_schedule_state, "_CURRENT_CONFIG")


def test_pull_schedule_state_tracks_current_config() -> None:
    from app.scheduler import pull_schedule_state

    pull_schedule_state.get_pull_schedule_state.cache_clear()
    config = PullScheduleConfig()

    try:
        pull_schedule_state.set_current_pull_schedule_config(config)

        assert pull_schedule_state.get_current_pull_schedule_config() is config
    finally:
        pull_schedule_state.set_current_pull_schedule_config(None)
        pull_schedule_state.get_pull_schedule_state.cache_clear()
