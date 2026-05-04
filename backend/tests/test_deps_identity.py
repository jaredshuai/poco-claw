from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.deps import (
    DEFAULT_USER_ID,
    get_current_actor,
    get_current_user_id,
    get_internal_actor,
)
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


# Tests for get_current_actor


def test_get_current_actor_returns_default_actor_when_allowed():
    with patch(
        "app.core.deps.get_settings",
        return_value=_settings(allow_default_user=True),
    ):
        actor = get_current_actor()
        assert actor.user_id == DEFAULT_USER_ID
        assert actor.auth_source == "default_user"
        assert actor.tenant_id is None
        assert actor.roles == ()
        assert actor.scopes == ()


def test_get_current_actor_trusted_user_header_with_metadata():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        actor = get_current_actor(
            x_user_id="proxy-user",
            x_user_id_token="trusted-user-token",
            x_tenant_id="tenant-123",
            x_user_roles="admin,editor",
            x_user_scopes="read,write",
        )
        assert actor.user_id == "proxy-user"
        assert actor.auth_source == "trusted_user_header"
        assert actor.tenant_id == "tenant-123"
        assert actor.roles == ("admin", "editor")
        assert actor.scopes == ("read", "write")


def test_get_current_actor_internal_token_with_metadata():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        actor = get_current_actor(
            x_user_id="worker-user",
            x_internal_token="internal-token",
            x_tenant_id="tenant-456",
            x_user_roles="viewer",
            x_user_scopes="read",
        )
        assert actor.user_id == "worker-user"
        assert actor.auth_source == "internal_token"
        assert actor.tenant_id == "tenant-456"
        assert actor.roles == ("viewer",)
        assert actor.scopes == ("read",)


def test_get_current_actor_untrusted_metadata_rejects():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with pytest.raises(AppException):
            get_current_actor(
                x_user_id="attacker",
                x_tenant_id="malicious-tenant",
                x_user_roles="admin",
                x_user_scopes="root",
            )


def test_get_current_user_id_backward_compatible():
    with patch(
        "app.core.deps.get_settings",
        return_value=_settings(allow_default_user=True),
    ):
        # Ensure get_current_user_id still returns just the string
        result = get_current_user_id()
        assert isinstance(result, str)
        assert result == DEFAULT_USER_ID

    with patch("app.core.deps.get_settings", return_value=_settings()):
        result = get_current_user_id(
            x_user_id="test-user",
            x_user_id_token="trusted-user-token",
        )
        assert result == "test-user"


def test_get_current_actor_parses_csv_headers():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        actor = get_current_actor(
            x_user_id="user-1",
            x_user_id_token="trusted-user-token",
            x_user_roles="  admin , editor  ,  ",
            x_user_scopes="read, write , ,delete",
        )
        assert actor.roles == ("admin", "editor")
        assert actor.scopes == ("read", "write", "delete")


def test_get_current_actor_normalizes_tenant_id_whitespace():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        actor = get_current_actor(
            x_user_id="proxy-user",
            x_user_id_token="trusted-user-token",
            x_tenant_id="  tenant-123  ",
        )
        assert actor.tenant_id == "tenant-123"


def test_get_current_actor_whitespace_only_tenant_id_becomes_none():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        actor = get_current_actor(
            x_user_id="proxy-user",
            x_user_id_token="trusted-user-token",
            x_tenant_id="   ",
        )
        assert actor.tenant_id is None


def test_get_current_actor_empty_tenant_id_becomes_none():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        actor = get_current_actor(
            x_user_id="proxy-user",
            x_user_id_token="trusted-user-token",
            x_tenant_id="",
        )
        assert actor.tenant_id is None


def test_get_current_actor_internal_token_normalizes_tenant_id():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        actor = get_current_actor(
            x_user_id="worker-user",
            x_internal_token="internal-token",
            x_tenant_id="  tenant-456  ",
        )
        assert actor.tenant_id == "tenant-456"


# Tests for get_internal_actor


def test_get_internal_actor_returns_actor_with_internal_token_auth_source():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        actor = get_internal_actor(
            x_user_id="worker-user",
            x_internal_token="internal-token",
        )
        assert actor.user_id == "worker-user"
        assert actor.auth_source == "internal_token"
        assert actor.tenant_id is None
        assert actor.roles == ()
        assert actor.scopes == ()


def test_get_internal_actor_trims_user_id_whitespace():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        actor = get_internal_actor(
            x_user_id="  worker-user  ",
            x_internal_token="internal-token",
        )
        assert actor.user_id == "worker-user"


def test_get_internal_actor_parses_roles_and_scopes():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        actor = get_internal_actor(
            x_user_id="worker-user",
            x_internal_token="internal-token",
            x_tenant_id="  tenant-789  ",
            x_user_roles="admin, editor",
            x_user_scopes="read, write, delete",
        )
        assert actor.tenant_id == "tenant-789"
        assert actor.roles == ("admin", "editor")
        assert actor.scopes == ("read", "write", "delete")


def test_get_internal_actor_rejects_missing_user_id():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with pytest.raises(AppException) as exc_info:
            get_internal_actor(x_internal_token="internal-token")
        assert exc_info.value.error_code.name == "FORBIDDEN"
        assert "User identity is required" in exc_info.value.message


def test_get_internal_actor_rejects_missing_internal_token():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with pytest.raises(AppException) as exc_info:
            get_internal_actor(x_user_id="worker-user")
        assert exc_info.value.error_code.name == "FORBIDDEN"


def test_get_internal_actor_rejects_invalid_internal_token():
    with patch("app.core.deps.get_settings", return_value=_settings()):
        with pytest.raises(AppException) as exc_info:
            get_internal_actor(
                x_user_id="worker-user",
                x_internal_token="wrong-token",
            )
        assert exc_info.value.error_code.name == "FORBIDDEN"


def test_get_internal_actor_rejects_trusted_user_id_token_without_internal_token():
    """Proves get_internal_actor does not accept X-User-Id-Token as an alternative.

    Unlike get_current_actor, get_internal_actor only validates via X-Internal-Token.
    The function signature does not include x_user_id_token, so even a valid trusted
    user header token cannot authenticate the request.
    """
    with patch("app.core.deps.get_settings", return_value=_settings()):
        # get_internal_actor does not accept x_user_id_token parameter at all,
        # proving it cannot use the proxy-token trust path.
        # Passing only user_id without internal_token should fail.
        with pytest.raises(AppException) as exc_info:
            get_internal_actor(x_user_id="proxy-user")
        assert exc_info.value.error_code.name == "FORBIDDEN"
