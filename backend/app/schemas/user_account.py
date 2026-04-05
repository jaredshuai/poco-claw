"""API shapes for `/users/me` profile and credits."""

from typing import Literal

from pydantic import BaseModel


class UserProfilePayload(BaseModel):
    """Profile block; field names match frontend `UserProfile`."""

    id: str
    email: str
    avatar: str = ""
    plan: Literal["free", "pro", "team"]
    planName: str


class UserCreditsPayload(BaseModel):
    """Credits block; field names match frontend `UserCredits`."""

    total: int | str
    free: int | str
    dailyRefreshCurrent: int
    dailyRefreshMax: int
    refreshTime: str


class UserMePayload(BaseModel):
    """Combined GET /users/me body."""

    profile: UserProfilePayload
    credits: UserCreditsPayload
