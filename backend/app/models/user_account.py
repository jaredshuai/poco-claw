"""Per-user account profile and credits (replaces frontend mock defaults)."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class UserAccount(Base, TimestampMixin):
    """Stores display profile and credit counters keyed by `user_id` (see `get_current_user_id`)."""

    __tablename__ = "user_accounts"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    email: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    avatar_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    plan_name_key: Mapped[str] = mapped_column(
        String(128), nullable=False, default="user.plan.free"
    )
    credits_total: Mapped[str] = mapped_column(
        String(64), nullable=False, default="user.credits.unlimited"
    )
    credits_free: Mapped[str] = mapped_column(
        String(64), nullable=False, default="user.credits.unlimited"
    )
    daily_refresh_current: Mapped[int] = mapped_column(Integer, nullable=False, default=9999)
    daily_refresh_max: Mapped[int] = mapped_column(Integer, nullable=False, default=9999)
    refresh_time: Mapped[str] = mapped_column(String(16), nullable=False, default="08:00")
