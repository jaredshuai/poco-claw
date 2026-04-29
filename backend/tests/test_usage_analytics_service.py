from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.schemas.usage_analytics import UsageAnalyticsBucket, UsageMetricSummary
from app.services.usage_analytics_service import UsageAnalyticsService


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now_utc(self) -> datetime:
        return self._now


class StubUsageAnalyticsService(UsageAnalyticsService):
    def _get_summary(
        self,
        db: Session,
        user_id: str,
        *,
        start_utc: datetime | None = None,
        end_utc: datetime | None = None,
    ) -> UsageMetricSummary:
        return UsageMetricSummary()

    def _get_month_buckets(
        self,
        db: Session,
        user_id: str,
        *,
        target_month: date,
        timezone_name: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[UsageAnalyticsBucket]:
        return []

    def _get_day_buckets(
        self,
        db: Session,
        user_id: str,
        *,
        target_day: date,
        timezone_name: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[UsageAnalyticsBucket]:
        return []


def test_default_month_uses_service_clock():
    service = StubUsageAnalyticsService(
        clock=FixedClock(datetime(2025, 2, 15, tzinfo=UTC))
    )

    with patch.object(StubUsageAnalyticsService, "_get_timezone", return_value=UTC):
        response = service.get_user_usage_analytics(
            MagicMock(spec=Session),
            "user-1",
            target_month=None,
            target_day=date(2025, 2, 10),
            timezone_name="UTC",
        )

    assert response.month == "2025-02"
    assert response.day == "2025-02-10"


def test_default_day_uses_service_clock_when_month_has_no_usage():
    service = StubUsageAnalyticsService(
        clock=FixedClock(datetime(2025, 2, 15, tzinfo=UTC))
    )

    with patch.object(StubUsageAnalyticsService, "_get_timezone", return_value=UTC):
        response = service.get_user_usage_analytics(
            MagicMock(spec=Session),
            "user-1",
            target_month=date(2025, 2, 1),
            target_day=None,
            timezone_name="UTC",
        )

    assert response.day == "2025-02-15"
