"""Policy engine for authorization decisions.

This module provides a minimal policy engine for user-owned resource access control.
It is pure Python and does not depend on FastAPI, SQLAlchemy, or other frameworks.
"""

from dataclasses import dataclass
from typing import Protocol

from app.core.identity import Actor


@dataclass(frozen=True)
class PolicyDecision:
    """Represents an authorization decision.

    Attributes:
        allowed: Whether the action is permitted.
        reason: A stable reason code if denied, None if allowed.
    """

    allowed: bool
    reason: str | None = None


class PolicyEngine(Protocol):
    """Protocol for policy engines that evaluate access to user-owned resources."""

    def can_access_user_resource(
        self, actor: Actor, owner_user_id: str
    ) -> PolicyDecision:
        """Check if an actor can access a resource owned by a user.

        Args:
            actor: The authenticated actor making the request.
            owner_user_id: The user id of the resource owner.

        Returns:
            A PolicyDecision indicating whether access is allowed.
        """
        ...


class DefaultPolicyEngine:
    """Default implementation of PolicyEngine for user-owned resources.

    Allows access when the actor's user_id matches the owner_user_id.
    Denies access otherwise with a stable reason code.
    """

    def can_access_user_resource(
        self, actor: Actor, owner_user_id: str
    ) -> PolicyDecision:
        if actor.user_id == owner_user_id:
            return PolicyDecision(allowed=True)
        return PolicyDecision(allowed=False, reason="user_owner_mismatch")


# Singleton instance for reuse
_default_policy_engine = DefaultPolicyEngine()


def get_default_policy_engine() -> PolicyEngine:
    """Get the default policy engine instance.

    Returns:
        The shared DefaultPolicyEngine instance.
    """
    return _default_policy_engine
