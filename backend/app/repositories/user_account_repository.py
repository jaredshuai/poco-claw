"""Data access for `UserAccount` rows."""

from sqlalchemy.orm import Session

from app.models.user_account import UserAccount


class UserAccountRepository:
    """CRUD helpers for per-user account display data."""

    @staticmethod
    def get_by_user_id(db: Session, user_id: str) -> UserAccount | None:
        """Returns the account row for `user_id`, if present."""
        return db.query(UserAccount).filter(UserAccount.user_id == user_id).first()

    @staticmethod
    def create(db: Session, row: UserAccount) -> UserAccount:
        """Persists a new account row (caller commits)."""
        db.add(row)
        return row
