from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_actor, get_db
from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.core.identity import Actor
from app.schemas.response import Response, ResponseSchema
from app.schemas.usage_analytics import UsageAnalyticsResponse
from app.services.usage_analytics_service import UsageAnalyticsService

router = APIRouter(prefix="/usage", tags=["usage"])

usage_analytics_service = UsageAnalyticsService()


def _parse_month(raw_month: str | None) -> date | None:
    if raw_month is None:
        return None
    try:
        return datetime.strptime(raw_month, "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise AppException(
            error_code=ErrorCode.BAD_REQUEST,
            message="month must use YYYY-MM format",
        ) from exc


def _parse_day(raw_day: str | None) -> date | None:
    if raw_day is None:
        return None
    try:
        return date.fromisoformat(raw_day)
    except ValueError as exc:
        raise AppException(
            error_code=ErrorCode.BAD_REQUEST,
            message="day must use YYYY-MM-DD format",
        ) from exc


@router.get("/analytics", response_model=ResponseSchema[UsageAnalyticsResponse])
async def get_usage_analytics(
    month: str | None = Query(default=None),
    day: str | None = Query(default=None),
    timezone: str = Query(default="UTC"),
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = usage_analytics_service.get_user_usage_analytics(
        db,
        actor.user_id,
        target_month=_parse_month(month),
        target_day=_parse_day(day),
        timezone_name=timezone,
    )
    return Response.success(data=result, message="Usage analytics retrieved")
