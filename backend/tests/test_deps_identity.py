from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.deps import DEFAULT_USER_ID, get_current_user_id
from app.core.errors.exceptions import AppException


def _settings(
    *,
    internal_api_token: str = "internal-token",
    trusted_user_header_token: str = "trusted-user-token",
    allow_default_user: bool = False,
):
    return SimpleNamespace(
        internal_api_token=internal_api_token,
        trusted_user_header_token=trusted_user_header_token,
        allow_default_user=allow_default_user,
    )


def test_get_current_user_id_rejects_missing_identity_by_default():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with pytest.raises(AppException):
            get_current_user_id()


def test_get_current_user_id_uses_default_when_explicitly_allowed():
    with patch(
        "app.core.deps.get_settings",
        return_value=_settings(allow_default_user=True),
    ):
        assert get_current_user_id() == DEFAULT_USER_ID


def test_get_current_user_id_rejects_untrusted_user_header():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with pytest.raises(AppException):
            get_current_user_id(x_user_id="attacker")


def test_get_current_user_id_allows_internal_user_header():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        assert (
            get_current_user_id(
                x_user_id="worker-user",
                x_internal_token="internal-token",
            )
            == "worker-user"
        )


def test_get_current_user_id_rejects_near_match_internal_token():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with pytest.raises(AppException):
            get_current_user_id(
                x_user_id="worker-user",
                x_internal_token="internal-toke",
            )


def test_get_current_user_id_allows_trusted_user_header_token():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        assert (
            get_current_user_id(
                x_user_id="proxy-user",
                x_user_id_token="trusted-user-token",
            )
            == "proxy-user"
        )


def test_get_current_user_id_rejects_near_match_trusted_user_header_token():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with pytest.raises(AppException):
            get_current_user_id(
                x_user_id="proxy-user",
                x_user_id_token="trusted-user-toke",
            )
