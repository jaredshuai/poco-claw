import calendar
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.models.agent_session import AgentSession
from app.models.usage_log import UsageLog
from app.schemas.usage_analytics import (
    UsageAnalyticsBucket,
    UsageAnalyticsDayView,
    UsageAnalyticsMonthView,
    UsageAnalyticsResponse,
    UsageAnalyticsSummary,
    UsageMetricSummary,
)
from app.services.clock import Clock, SystemClock


class UsageAnalyticsService:
    """Service layer for user-level usage analytics."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()

    @staticmethod
    def _get_timezone(timezone_name: str) -> ZoneInfo:
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message=f"Invalid timezone: {timezone_name}",
            ) from exc

    @staticmethod
    def _to_float(value: Decimal | float | int | None) -> float:
        if value is None:
            return 0.0
        return float(value)

    @staticmethod
    def _month_bounds(
        target_month: date, tzinfo: ZoneInfo
    ) -> tuple[datetime, datetime]:
        month_start = datetime.combine(target_month.replace(day=1), time.min, tzinfo)
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1, day=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1, day=1)
        return month_start, next_month

    @staticmethod
    def _day_bounds(target_day: date, tzinfo: ZoneInfo) -> tuple[datetime, datetime]:
        day_start = datetime.combine(target_day, time.min, tzinfo)
        return day_start, day_start + timedelta(days=1)

    def _today(self, tzinfo: ZoneInfo) -> date:
        return self._clock.now_utc().astimezone(tzinfo).date()

    @staticmethod
    def _to_summary(row: object) -> UsageMetricSummary:
        return UsageMetricSummary(
            input_tokens=int(getattr(row, "input_tokens", 0) or 0),
            output_tokens=int(getattr(row, "output_tokens", 0) or 0),
            cache_creation_input_tokens=int(
                getattr(row, "cache_creation_input_tokens", 0) or 0
            ),
            cache_read_input_tokens=int(
                getattr(row, "cache_read_input_tokens", 0) or 0
            ),
            total_tokens=int(getattr(row, "total_tokens", 0) or 0),
            total_cost_usd=UsageAnalyticsService._to_float(
                getattr(row, "total_cost_usd", 0.0)
            ),
        )

    def _build_summary_query(self, db: Session, user_id: str):
        return (
            db.query(
                func.coalesce(func.sum(UsageLog.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(UsageLog.output_tokens), 0).label(
                    "output_tokens"
                ),
                func.coalesce(func.sum(UsageLog.cache_creation_input_tokens), 0).label(
                    "cache_creation_input_tokens"
                ),
                func.coalesce(func.sum(UsageLog.cache_read_input_tokens), 0).label(
                    "cache_read_input_tokens"
                ),
                func.coalesce(func.sum(UsageLog.total_tokens), 0).label("total_tokens"),
                func.coalesce(func.sum(UsageLog.total_cost_usd), 0).label(
                    "total_cost_usd"
                ),
            )
            .join(AgentSession, AgentSession.id == UsageLog.session_id)
            .filter(AgentSession.user_id == user_id)
            .filter(UsageLog.include_in_user_analytics.is_(True))
        )

    def _get_summary(
        self,
        db: Session,
        user_id: str,
        *,
        start_utc: datetime | None = None,
        end_utc: datetime | None = None,
    ) -> UsageMetricSummary:
        query = self._build_summary_query(db, user_id)
        if start_utc is not None:
            query = query.filter(UsageLog.created_at >= start_utc)
        if end_utc is not None:
            query = query.filter(UsageLog.created_at < end_utc)
        return self._to_summary(query.one())

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
        local_created_at = func.timezone(timezone_name, UsageLog.created_at)
        bucket_day_expr = func.date(local_created_at)
        rows = (
            self._build_summary_query(db, user_id)
            .add_columns(bucket_day_expr.label("bucket_day"))
            .filter(UsageLog.created_at >= start_utc)
            .filter(UsageLog.created_at < end_utc)
            .group_by(bucket_day_expr)
            .order_by(bucket_day_expr)
            .all()
        )

        by_day: dict[date, UsageMetricSummary] = {}
        for row in rows:
            bucket_day = getattr(row, "bucket_day")
            if isinstance(bucket_day, datetime):
                day_key = bucket_day.date()
            elif isinstance(bucket_day, date):
                day_key = bucket_day
            else:
                day_key = date.fromisoformat(str(bucket_day))
            by_day[day_key] = self._to_summary(row)

        total_days = calendar.monthrange(target_month.year, target_month.month)[1]
        buckets: list[UsageAnalyticsBucket] = []
        for day_number in range(1, total_days + 1):
            bucket_day = target_month.replace(day=day_number)
            summary = by_day.get(bucket_day, UsageMetricSummary())
            buckets.append(
                UsageAnalyticsBucket(
                    bucket_id=bucket_day.isoformat(),
                    label=f"{day_number:02d}",
                    **summary.model_dump(),
                )
            )
        return buckets

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
        local_created_at = func.timezone(timezone_name, UsageLog.created_at)
        bucket_hour_expr = func.extract("hour", local_created_at)
        rows = (
            self._build_summary_query(db, user_id)
            .add_columns(bucket_hour_expr.label("bucket_hour"))
            .filter(UsageLog.created_at >= start_utc)
            .filter(UsageLog.created_at < end_utc)
            .group_by(bucket_hour_expr)
            .order_by(bucket_hour_expr)
            .all()
        )

        by_hour = {
            int(getattr(row, "bucket_hour", 0) or 0): self._to_summary(row)
            for row in rows
        }

        buckets: list[UsageAnalyticsBucket] = []
        for hour in range(24):
            summary = by_hour.get(hour, UsageMetricSummary())
            buckets.append(
                UsageAnalyticsBucket(
                    bucket_id=f"{target_day.isoformat()}T{hour:02d}:00",
                    label=f"{hour:02d}:00",
                    **summary.model_dump(),
                )
            )
        return buckets

    @staticmethod
    def _resolve_day(
        target_day: date | None,
        *,
        target_month: date,
        month_buckets: list[UsageAnalyticsBucket],
        tzinfo: ZoneInfo,
    ) -> date:
        if target_day is not None:
            return target_day

        non_empty_days = [
            date.fromisoformat(bucket.bucket_id)
            for bucket in month_buckets
            if bucket.total_tokens > 0
        ]
        if non_empty_days:
            return non_empty_days[-1]

        today = datetime.now(tzinfo).date()
        if today.year == target_month.year and today.month == target_month.month:
            return today
        return target_month.replace(day=1)

    def get_user_usage_analytics(
        self,
        db: Session,
        user_id: str,
        *,
        target_month: date | None,
        target_day: date | None,
        timezone_name: str,
    ) -> UsageAnalyticsResponse:
        tzinfo = self._get_timezone(timezone_name)
        local_today = self._today(tzinfo)
        resolved_month = (target_month or local_today).replace(day=1)

        if target_day is not None and (
            target_day.year != resolved_month.year
            or target_day.month != resolved_month.month
        ):
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message="day must belong to the selected month",
            )

        month_start_local, month_end_local = self._month_bounds(resolved_month, tzinfo)
        month_start_utc = month_start_local.astimezone(timezone.utc)
        month_end_utc = month_end_local.astimezone(timezone.utc)

        month_buckets = self._get_month_buckets(
            db,
            user_id,
            target_month=resolved_month,
            timezone_name=timezone_name,
            start_utc=month_start_utc,
            end_utc=month_end_utc,
        )
        resolved_day = self._resolve_day(
            target_day,
            target_month=resolved_month,
            month_buckets=month_buckets,
            tzinfo=tzinfo,
        )

        day_start_local, day_end_local = self._day_bounds(resolved_day, tzinfo)
        day_start_utc = day_start_local.astimezone(timezone.utc)
        day_end_utc = day_end_local.astimezone(timezone.utc)
        day_buckets = self._get_day_buckets(
            db,
            user_id,
            target_day=resolved_day,
            timezone_name=timezone_name,
            start_utc=day_start_utc,
            end_utc=day_end_utc,
        )

        return UsageAnalyticsResponse(
            timezone=timezone_name,
            month=resolved_month.strftime("%Y-%m"),
            day=resolved_day.isoformat(),
            summary=UsageAnalyticsSummary(
                month=self._get_summary(
                    db,
                    user_id,
                    start_utc=month_start_utc,
                    end_utc=month_end_utc,
                ),
                day=self._get_summary(
                    db,
                    user_id,
                    start_utc=day_start_utc,
                    end_utc=day_end_utc,
                ),
                all_time=self._get_summary(db, user_id),
            ),
            month_view=UsageAnalyticsMonthView(
                month=resolved_month.strftime("%Y-%m"),
                buckets=month_buckets,
            ),
            day_view=UsageAnalyticsDayView(
                day=resolved_day.isoformat(),
                buckets=day_buckets,
            ),
        )
