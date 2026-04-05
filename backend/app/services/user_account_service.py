"""Business logic for user profile and credits exposed via `/users/me`."""

from sqlalchemy.orm import Session

from app.models.user_account import UserAccount
from app.repositories.user_account_repository import UserAccountRepository
from app.schemas.user_account import (
    UserCreditsPayload,
    UserMePayload,
    UserProfilePayload,
)


def _coerce_credit_field(raw: str) -> int | str:
    """Parses numeric credit strings to int; keeps i18n keys as str."""
    if raw.isdigit():
        return int(raw)
    return raw


def _default_email_for_user(user_id: str) -> str:
    """Seed email for legacy mock parity when the id is the default placeholder."""
    if user_id == "default":
        return "user@poco.com"
    return ""


class UserAccountService:
    """Loads or creates `UserAccount` and maps to API payloads."""

    def get_me(self, db: Session, user_id: str) -> UserMePayload:
        """Returns profile + credits for `user_id`, creating defaults on first access."""
        row = UserAccountRepository.get_by_user_id(db, user_id)
        if row is None:
            row = UserAccount(
                user_id=user_id,
                email=_default_email_for_user(user_id),
                avatar_url="",
                plan="free",
                plan_name_key="user.plan.free",
                credits_total="user.credits.unlimited",
                credits_free="user.credits.unlimited",
                daily_refresh_current=9999,
                daily_refresh_max=9999,
                refresh_time="08:00",
            )
            UserAccountRepository.create(db, row)
            db.commit()
            db.refresh(row)

        plan_value = row.plan if row.plan in ("free", "pro", "team") else "free"
        profile = UserProfilePayload(
            id=row.user_id,
            email=row.email,
            avatar=row.avatar_url,
            plan=plan_value,  # type: ignore[arg-type]
            planName=row.plan_name_key,
        )
        credits = UserCreditsPayload(
            total=_coerce_credit_field(row.credits_total),
            free=_coerce_credit_field(row.credits_free),
            dailyRefreshCurrent=row.daily_refresh_current,
            dailyRefreshMax=row.daily_refresh_max,
            refreshTime=row.refresh_time,
        )
        return UserMePayload(profile=profile, credits=credits)
