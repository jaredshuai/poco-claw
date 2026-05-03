"""Tests for the policy engine module."""

import pytest

from app.core.identity import Actor
from app.core.policy import (
    DefaultPolicyEngine,
    PolicyDecision,
    get_default_policy_engine,
)


class TestPolicyDecision:
    """Tests for PolicyDecision dataclass."""

    def test_allowed_decision_has_no_reason(self) -> None:
        decision = PolicyDecision(allowed=True)
        assert decision.allowed is True
        assert decision.reason is None

    def test_denied_decision_has_reason(self) -> None:
        decision = PolicyDecision(allowed=False, reason="user_owner_mismatch")
        assert decision.allowed is False
        assert decision.reason == "user_owner_mismatch"

    def test_frozen_dataclass(self) -> None:
        decision = PolicyDecision(allowed=True)
        with pytest.raises(Exception):
            decision.allowed = False  # type: ignore[misc]


class TestDefaultPolicyEngine:
    """Tests for DefaultPolicyEngine."""

    def setup_method(self) -> None:
        self.engine = DefaultPolicyEngine()

    def test_allows_actor_matching_owner(self) -> None:
        actor = Actor(user_id="user-123")
        decision = self.engine.can_access_user_resource(actor, "user-123")
        assert decision.allowed is True
        assert decision.reason is None

    def test_denies_actor_not_matching_owner(self) -> None:
        actor = Actor(user_id="user-123")
        decision = self.engine.can_access_user_resource(actor, "user-456")
        assert decision.allowed is False
        assert decision.reason == "user_owner_mismatch"

    def test_preserves_stable_denied_reason(self) -> None:
        actor = Actor(user_id="user-123")
        decision1 = self.engine.can_access_user_resource(actor, "user-456")
        decision2 = self.engine.can_access_user_resource(actor, "user-789")
        assert decision1.reason == "user_owner_mismatch"
        assert decision2.reason == "user_owner_mismatch"
        assert decision1.reason == decision2.reason

    def test_allows_actor_with_tenant_id(self) -> None:
        actor = Actor(user_id="user-123", tenant_id="tenant-abc")
        decision = self.engine.can_access_user_resource(actor, "user-123")
        assert decision.allowed is True

    def test_allows_actor_with_roles_and_scopes(self) -> None:
        actor = Actor(
            user_id="user-123",
            roles=("admin", "viewer"),
            scopes=("read", "write"),
        )
        decision = self.engine.can_access_user_resource(actor, "user-123")
        assert decision.allowed is True


class TestGetDefaultPolicyEngine:
    """Tests for get_default_policy_engine function."""

    def test_returns_policy_engine(self) -> None:
        engine = get_default_policy_engine()
        assert isinstance(engine, DefaultPolicyEngine)

    def test_returns_same_instance(self) -> None:
        engine1 = get_default_policy_engine()
        engine2 = get_default_policy_engine()
        assert engine1 is engine2
