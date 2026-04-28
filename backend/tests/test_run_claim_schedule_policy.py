from app.services.run_claim_schedule_policy import RunClaimSchedulePolicy


def test_normalize_schedule_modes_returns_none_for_absent_modes() -> None:
    assert RunClaimSchedulePolicy.normalize_schedule_modes(None) is None
    assert RunClaimSchedulePolicy.normalize_schedule_modes([]) is None


def test_normalize_schedule_modes_strips_and_keeps_valid_modes_in_order() -> None:
    modes = RunClaimSchedulePolicy.normalize_schedule_modes(
        [" immediate ", "nightly", " scheduled "]
    )

    assert modes == ["immediate", "nightly", "scheduled"]


def test_normalize_schedule_modes_drops_blank_modes() -> None:
    modes = RunClaimSchedulePolicy.normalize_schedule_modes(
        [" ", "immediate", "", "nightly", "\t"]
    )

    assert modes == ["immediate", "nightly"]


def test_normalize_schedule_modes_returns_none_when_all_modes_are_blank() -> None:
    modes = RunClaimSchedulePolicy.normalize_schedule_modes([" ", "", "\t"])

    assert modes is None
