import unittest
from unittest.mock import MagicMock, patch

from app.schemas.permission_policy import (
    PermissionPolicy,
    PermissionPolicyUpdateRequest,
    PermissionRule,
    PermissionRuleMatch,
)
from app.services.execution_settings_service import ExecutionSettingsService


class TestExecutionSettingsService(unittest.TestCase):
    """Tests for ExecutionSettingsService.get_or_create and update."""

    def setUp(self) -> None:
        self.service = ExecutionSettingsService()
        self.db = MagicMock()
        self.user_id = "user-123"

    @patch(
        "app.services.execution_settings_service.UserExecutionSettingRepository.get_by_user_id"
    )
    @patch(
        "app.services.execution_settings_service.UserExecutionSettingRepository.create"
    )
    def test_get_or_create_returns_defaults_when_no_record(
        self, mock_create: MagicMock, mock_get: MagicMock
    ) -> None:
        mock_get.return_value = None
        result = self.service.get_or_create(self.db, self.user_id)
        self.assertEqual(result.schema_version, "v1")
        self.assertIsInstance(result.permissions, PermissionPolicy)

    @patch(
        "app.services.execution_settings_service.UserExecutionSettingRepository.get_by_user_id"
    )
    def test_get_or_create_returns_existing(self, mock_get: MagicMock) -> None:
        record = MagicMock()
        record.schema_version = "v1"
        record.settings = {
            "permissions": {
                "version": "v1",
                "mode": "enforce",
                "default_action": "deny",
                "rules": [],
            }
        }
        mock_get.return_value = record
        result = self.service.get_or_create(self.db, self.user_id)
        policy = result.permissions
        assert isinstance(policy, PermissionPolicy)
        self.assertEqual(policy.mode, "enforce")
        self.assertEqual(policy.default_action, "deny")


class TestPermissionPolicyPartialUpdate(unittest.TestCase):
    """Tests for PATCH /permissions partial update semantics."""

    def test_exclude_unset_only_includes_sent_fields(self) -> None:
        request = PermissionPolicyUpdateRequest(mode="enforce")
        dump = request.model_dump(exclude_unset=True)
        self.assertEqual(dump, {"mode": "enforce"})

    def test_exclude_unset_with_multiple_fields(self) -> None:
        request = PermissionPolicyUpdateRequest(
            mode="enforce",
            default_action="deny",
        )
        dump = request.model_dump(exclude_unset=True)
        self.assertEqual(dump, {"mode": "enforce", "default_action": "deny"})

    def test_exclude_unset_empty_body(self) -> None:
        request = PermissionPolicyUpdateRequest()
        dump = request.model_dump(exclude_unset=True)
        self.assertEqual(dump, {})

    def test_merge_preserves_unsent_fields(self) -> None:
        current = PermissionPolicy(mode="audit", default_action="allow")
        request = PermissionPolicyUpdateRequest(mode="enforce")
        update_dict = request.model_dump(exclude_unset=True)
        merged = current.model_dump()
        merged.update(update_dict)
        updated = PermissionPolicy.model_validate(merged)
        self.assertEqual(updated.mode, "enforce")
        self.assertEqual(updated.default_action, "allow")  # unchanged
        self.assertEqual(updated.version, "v1")  # unchanged

    def test_merge_preserves_rules(self) -> None:
        current = PermissionPolicy(
            mode="audit",
            rules=[
                PermissionRule(
                    id="r1",
                    match=PermissionRuleMatch(tools=["Bash"]),
                    action="deny",
                    reason="test",
                )
            ],
        )
        request = PermissionPolicyUpdateRequest(mode="enforce")
        update_dict = request.model_dump(exclude_unset=True)
        merged = current.model_dump()
        merged.update(update_dict)
        updated = PermissionPolicy.model_validate(merged)
        self.assertEqual(updated.mode, "enforce")
        self.assertEqual(len(updated.rules), 1)
        self.assertEqual(updated.rules[0].id, "r1")

    def test_update_rules_only(self) -> None:
        current = PermissionPolicy(mode="audit")
        new_rules = [
            PermissionRule(
                id="r2",
                match=PermissionRuleMatch(tools=["Write"]),
                action="ask",
            )
        ]
        request = PermissionPolicyUpdateRequest(rules=new_rules)
        update_dict = request.model_dump(exclude_unset=True)
        merged = current.model_dump()
        merged.update(update_dict)
        updated = PermissionPolicy.model_validate(merged)
        self.assertEqual(updated.mode, "audit")  # unchanged
        self.assertEqual(len(updated.rules), 1)
        self.assertEqual(updated.rules[0].id, "r2")

    def test_full_update_all_fields(self) -> None:
        current = PermissionPolicy()
        new_rules = [
            PermissionRule(
                id="r1",
                match=PermissionRuleMatch(tools=["Bash"]),
                action="deny",
            )
        ]
        request = PermissionPolicyUpdateRequest(
            version="v2",
            mode="enforce",
            default_action="deny",
            preset_source="strict",
            rules=new_rules,
        )
        update_dict = request.model_dump(exclude_unset=True)
        merged = current.model_dump()
        merged.update(update_dict)
        updated = PermissionPolicy.model_validate(merged)
        self.assertEqual(updated.version, "v2")
        self.assertEqual(updated.mode, "enforce")
        self.assertEqual(updated.default_action, "deny")
        self.assertEqual(updated.preset_source, "strict")
        self.assertEqual(len(updated.rules), 1)


class TestResolvePermissionPolicy(unittest.TestCase):
    """Tests for PermissionPolicy.from_dict (used by _resolve_permission_policy)."""

    def test_from_dict_with_none_returns_default(self) -> None:
        policy = PermissionPolicy.from_dict(None)
        self.assertIsInstance(policy, PermissionPolicy)
        self.assertEqual(policy.mode, "audit")
        self.assertEqual(policy.default_action, "allow")

    def test_from_dict_with_empty_dict_returns_default(self) -> None:
        policy = PermissionPolicy.from_dict({})
        self.assertIsInstance(policy, PermissionPolicy)
        self.assertEqual(policy.version, "v1")

    def test_from_dict_with_valid_data(self) -> None:
        data = {"version": "v1", "mode": "enforce", "default_action": "deny"}
        policy = PermissionPolicy.from_dict(data)
        self.assertEqual(policy.mode, "enforce")
        self.assertEqual(policy.default_action, "deny")

    def test_from_dict_passthrough_for_policy_instance(self) -> None:
        original = PermissionPolicy(mode="enforce")
        result = PermissionPolicy.from_dict(original)
        self.assertIs(result, original)

    def test_from_dict_with_rules(self) -> None:
        data = {
            "version": "v1",
            "mode": "enforce",
            "rules": [
                {
                    "id": "r1",
                    "priority": 10,
                    "match": {"tools": ["Bash"]},
                    "action": "deny",
                    "reason": "test",
                }
            ],
        }
        policy = PermissionPolicy.from_dict(data)
        self.assertEqual(len(policy.rules), 1)
        self.assertEqual(policy.rules[0].id, "r1")
