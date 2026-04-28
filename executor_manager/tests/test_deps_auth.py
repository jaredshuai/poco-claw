from types import SimpleNamespace
from unittest.mock import patch

from app.core.deps import require_callback_token


def test_callback_token_uses_constant_time_compare() -> None:
    with (
        patch(
            "app.core.deps.get_settings",
            return_value=SimpleNamespace(callback_token="callback-token"),
        ),
        patch("hmac.compare_digest", return_value=True) as compare_digest,
    ):
        require_callback_token("Bearer callback-token")

    compare_digest.assert_called_once_with("callback-token", "callback-token")
