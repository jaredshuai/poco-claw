class RunClaimSchedulePolicy:
    """Policy for normalizing schedule filters used by run claim requests."""

    @staticmethod
    def normalize_schedule_modes(schedule_modes: list[str] | None) -> list[str] | None:
        if not schedule_modes:
            return None

        normalized = [mode.strip() for mode in schedule_modes if mode.strip()]
        return normalized or None
