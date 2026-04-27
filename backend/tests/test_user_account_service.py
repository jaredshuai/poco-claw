"""Unit tests for UserAccountService.get_me mapping."""

import unittest
from unittest.mock import MagicMock, patch

from app.services.user_account_service import UserAccountService


class TestUserAccountServiceGetMe(unittest.TestCase):
    """Tests profile/credits mapping from an existing DB row."""

    def setUp(self) -> None:
        self.service = UserAccountService()
        self.db = MagicMock()

    @patch("app.services.user_account_service.UserAccountRepository.get_by_user_id")
    def test_get_me_maps_existing_row(self, mock_get: MagicMock) -> None:
        row = MagicMock()
        row.user_id = "u1"
        row.email = "a@example.com"
        row.avatar_url = ""
        row.plan = "pro"
        row.plan_name_key = "user.plan.pro"
        row.credits_total = "100"
        row.credits_free = "50"
        row.daily_refresh_current = 1
        row.daily_refresh_max = 10
        row.refresh_time = "09:00"
        mock_get.return_value = row

        result = self.service.get_me(self.db, "u1")

        self.assertEqual(result.profile.id, "u1")
        self.assertEqual(result.profile.email, "a@example.com")
        self.assertEqual(result.profile.plan, "pro")
        self.assertEqual(result.profile.planName, "user.plan.pro")
        self.assertEqual(result.credits.total, 100)
        self.assertEqual(result.credits.free, 50)
        self.assertEqual(result.credits.dailyRefreshCurrent, 1)
        self.assertEqual(result.credits.dailyRefreshMax, 10)
        self.assertEqual(result.credits.refreshTime, "09:00")


if __name__ == "__main__":
    unittest.main()
