import types
import unittest
from collections.abc import Mapping
from types import SimpleNamespace
from typing import get_origin, get_args
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.backend_client import BackendClient


class TestBackendClientTraceHeaders(unittest.TestCase):
    """Test BackendClient._trace_headers."""

    def test_init_accepts_injected_settings_and_http_client(self) -> None:
        settings = SimpleNamespace(
            backend_url="http://backend/",
            internal_api_token="token-123",
        )
        http_client = MagicMock()

        with (
            patch(
                "app.services.backend_client.get_settings",
                side_effect=AssertionError("settings should be injected"),
            ),
            patch(
                "app.services.backend_client.httpx.AsyncClient",
                side_effect=AssertionError("http client should be injected"),
            ),
        ):
            client = BackendClient(settings=settings, http_client=http_client)

        assert client.settings is settings
        assert client.base_url == "http://backend"
        assert client._client is http_client

    def test_init_defers_default_http_client_construction(self) -> None:
        settings = SimpleNamespace(
            backend_url="http://backend/",
            internal_api_token="token-123",
        )
        http_client = MagicMock()

        with patch(
            "app.services.backend_client.httpx.AsyncClient",
            return_value=http_client,
        ) as http_client_cls:
            client = BackendClient(settings=settings)

            http_client_cls.assert_not_called()
            assert client._client is http_client

        http_client_cls.assert_called_once()

    def test_trace_headers_with_existing_ids(self) -> None:
        with patch("app.services.backend_client.get_request_id") as mock_get_req:
            with patch("app.services.backend_client.get_trace_id") as mock_get_trace:
                mock_get_req.return_value = "req-123"
                mock_get_trace.return_value = "trace-456"

                headers = BackendClient._trace_headers()

                assert headers["X-Request-ID"] == "req-123"
                assert headers["X-Trace-ID"] == "trace-456"

    def test_trace_headers_generates_ids(self) -> None:
        with patch("app.services.backend_client.get_request_id") as mock_get_req:
            with patch("app.services.backend_client.get_trace_id") as mock_get_trace:
                with patch(
                    "app.services.backend_client.generate_request_id"
                ) as mock_gen_req:
                    with patch(
                        "app.services.backend_client.generate_trace_id"
                    ) as mock_gen_trace:
                        mock_get_req.return_value = None
                        mock_get_trace.return_value = None
                        mock_gen_req.return_value = "new-req-123"
                        mock_gen_trace.return_value = "new-trace-456"

                        headers = BackendClient._trace_headers()

                        assert headers["X-Request-ID"] == "new-req-123"
                        assert headers["X-Trace-ID"] == "new-trace-456"

    def test_internal_headers_include_token_and_trace_context(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                backend_url="http://backend",
                internal_api_token="token-123",
            )
            client = BackendClient()

            with patch.object(
                client,
                "_trace_headers",
                return_value={
                    "X-Request-ID": "req-123",
                    "X-Trace-ID": "trace-456",
                },
            ):
                headers = client._internal_headers()

        assert headers == {
            "X-Internal-Token": "token-123",
            "X-Request-ID": "req-123",
            "X-Trace-ID": "trace-456",
        }

    def test_internal_user_headers_include_trusted_user_context(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                backend_url="http://backend",
                internal_api_token="token-123",
            )
            client = BackendClient()

            with patch.object(
                client,
                "_trace_headers",
                return_value={
                    "X-Request-ID": "req-123",
                    "X-Trace-ID": "trace-456",
                },
            ):
                headers = client._internal_user_headers("user-123")

        assert headers == {
            "X-Internal-Token": "token-123",
            "X-User-Id": "user-123",
            "X-Request-ID": "req-123",
            "X-Trace-ID": "trace-456",
        }


@pytest.mark.asyncio
class TestBackendClientRequest:
    """Test BackendClient._request method."""

    async def test_request_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client._request("GET", "/test")

                assert result == mock_response

    async def test_request_retries_connect_error(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()

            call_count = 0

            async def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise httpx.ConnectError("connection error")
                return mock_response

            with patch.object(client._client, "request", side_effect=side_effect):
                result = await client._request("GET", "/test", retry_connect_errors=2)

                assert result == mock_response
                assert call_count == 3

    async def test_request_raises_after_max_retries(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            async def always_fail(*args, **kwargs):
                raise httpx.ConnectError("connection error")

            with patch.object(client._client, "request", side_effect=always_fail):
                with pytest.raises(httpx.ConnectError):
                    await client._request("GET", "/test", retry_connect_errors=2)

    async def test_request_raises_connect_timeout(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            async def timeout_error(*args, **kwargs):
                raise httpx.ConnectTimeout("timeout")

            with patch.object(client._client, "request", side_effect=timeout_error):
                with pytest.raises(httpx.ConnectTimeout):
                    await client._request("GET", "/test")

    async def test_request_raises_http_status_error(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.status_code = 404

            async def raise_404(*args, **kwargs):
                mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "Not found", request=MagicMock(), response=mock_response
                )
                return mock_response

            with patch.object(client._client, "request", side_effect=raise_404):
                with pytest.raises(httpx.HTTPStatusError):
                    await client._request("GET", "/test")


@pytest.mark.asyncio
class TestBackendClientCreateSession:
    """Test BackendClient.create_session."""

    async def test_create_session_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": {"session_id": "sess-123", "sdk_session_id": "sdk-456"}
            }
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.create_session("user-123", {"model": "claude"})

                assert result["session_id"] == "sess-123"

    async def test_create_session_non_dict_data_returns_empty_dict(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": "not a dict"}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.create_session("user-123", {"model": "claude"})

                assert result == {}


@pytest.mark.asyncio
class TestBackendClientGetSession:
    """Test BackendClient.get_session."""

    async def test_get_session_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": {
                    "session_id": "sess-123",
                    "user_id": "user-123",
                    "status": "running",
                }
            }
            mock_response.raise_for_status = MagicMock()

            request = AsyncMock(return_value=mock_response)
            with patch.object(client._client, "request", request):
                result = await client.get_session("sess-123")

            assert result["session_id"] == "sess-123"
            request.assert_awaited_once()
            args, kwargs = request.call_args
            assert args[:2] == ("GET", "/api/v1/sessions/sess-123")
            assert "headers" in kwargs


def test_backend_client_create_session_config_is_dict_str_object() -> None:
    """Regression: BackendClient.create_session config is dict[str, object], not bare dict."""
    import typing

    hints = typing.get_type_hints(BackendClient.create_session)
    config_type = hints.get("config")

    assert get_origin(config_type) is dict
    assert get_args(config_type) == (str, object)


def test_backend_client_create_session_return_is_dict_str_object() -> None:
    """Regression: BackendClient.create_session returns dict[str, object], not bare dict."""
    import typing

    hints = typing.get_type_hints(BackendClient.create_session)
    return_type = hints.get("return")

    assert get_origin(return_type) is dict
    assert get_args(return_type) == (str, object)


def test_backend_client_get_session_return_is_dict_str_object() -> None:
    """Regression: BackendClient.get_session returns dict[str, object], not dict[str, Any]."""
    import typing

    hints = typing.get_type_hints(BackendClient.get_session)
    return_type = hints.get("return")

    assert get_origin(return_type) is dict
    assert get_args(return_type) == (str, object)


@pytest.mark.asyncio
class TestBackendClientUpdateSessionStatus:
    """Test BackendClient.update_session_status."""

    async def test_update_session_status_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                # Should not raise
                await client.update_session_status("sess-123", "completed")


@pytest.mark.asyncio
class TestBackendClientForwardCallback:
    """Test BackendClient.forward_callback."""

    async def test_forward_callback_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                backend_url="http://backend",
                internal_api_token="token-123",
            )

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"status": "ok"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ) as mock_request:
                result = await client.forward_callback({"event": "completed"})

                assert result == {"status": "ok"}
                assert (
                    mock_request.call_args.kwargs["headers"]["X-Internal-Token"]
                    == "token-123"
                )

    async def test_forward_callback_empty_data(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.forward_callback({"event": "completed"})

                assert result == {}

    async def test_forward_callback_returns_empty_mapping_for_non_mapping_data(
        self,
    ) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": ["raw", "payload"]}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.forward_callback({"event": "completed"})

                assert result == {}

    async def test_forward_callback_returns_empty_mapping_for_non_string_mapping_keys(
        self,
    ) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {123: "received"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.forward_callback({"event": "completed"})

                assert result == {}


@pytest.mark.asyncio
class TestBackendClientClaimRun:
    """Test BackendClient.claim_run."""

    async def test_claim_run_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                backend_url="http://backend",
                internal_api_token="token-123",
            )

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"run_id": "run-123"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ) as mock_request:
                result = await client.claim_run("worker-1", lease_seconds=60)

                assert result["run_id"] == "run-123"
                assert (
                    mock_request.call_args.kwargs["headers"]["X-Internal-Token"]
                    == "token-123"
                )

    async def test_claim_run_with_schedule_modes(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": None}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ) as mock_request:
                await client.claim_run(
                    "worker-1", schedule_modes=["immediate", "scheduled"]
                )

                # Verify schedule_modes was included in payload
                call_args = mock_request.call_args
                assert "schedule_modes" in call_args.kwargs["json"]

    async def test_claim_run_returns_none(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": None}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.claim_run("worker-1")

                assert result is None

    async def test_claim_run_returns_none_for_non_mapping_data(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": ["raw", "payload"]}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.claim_run("worker-1")

                assert result is None

    async def test_claim_run_returns_none_for_non_string_mapping_keys(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {123: "run-123"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.claim_run("worker-1")

                assert result is None


def test_backend_client_claim_run_return_is_mapping_str_object_or_none() -> None:
    """Regression: BackendClient.claim_run returns Mapping[str, object] | None."""
    import typing

    hints = typing.get_type_hints(BackendClient.claim_run)
    return_type = hints.get("return")

    assert return_type is not None
    assert "Any" not in str(return_type)
    assert "dict" not in str(return_type)

    args = get_args(return_type)
    mapping_type = next(
        (arg for arg in args if get_origin(arg) is Mapping),
        None,
    )

    assert mapping_type is not None
    assert get_args(mapping_type) == (str, object)


def _assert_mapping_str_object(annotation: object) -> None:
    assert annotation is not None
    assert "Any" not in str(annotation)
    assert "dict" not in str(annotation)
    assert get_origin(annotation) is Mapping
    assert get_args(annotation) == (str, object)


def test_backend_client_forward_callback_port_is_mapping_str_object() -> None:
    """Regression: forward_callback port uses Mapping[str, object], not Any or dict."""
    import typing

    hints = typing.get_type_hints(BackendClient.forward_callback)

    _assert_mapping_str_object(hints.get("callback_data"))
    _assert_mapping_str_object(hints.get("return"))


def test_backend_client_start_fail_run_return_is_mapping_str_object() -> None:
    """Regression: start/fail run adapters return Mapping[str, object], not bare dict."""
    import typing

    start_hints = typing.get_type_hints(BackendClient.start_run)
    fail_hints = typing.get_type_hints(BackendClient.fail_run)

    _assert_mapping_str_object(start_hints.get("return"))
    _assert_mapping_str_object(fail_hints.get("return"))


@pytest.mark.asyncio
class TestBackendClientRunOperations:
    """Test BackendClient run operations: start_run, fail_run."""

    async def test_start_run_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                backend_url="http://backend",
                internal_api_token="token-123",
            )

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"status": "running"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ) as mock_request:
                result = await client.start_run("run-123", "worker-1")

                assert result["status"] == "running"
                assert (
                    mock_request.call_args.kwargs["headers"]["X-Internal-Token"]
                    == "token-123"
                )

    async def test_start_run_with_lease_seconds(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                backend_url="http://backend",
                internal_api_token="token-123",
            )

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"status": "running"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ) as mock_request:
                result = await client.start_run(
                    "run-123", "worker-1", lease_seconds=3600
                )

                assert result["status"] == "running"
                call_kwargs = mock_request.call_args.kwargs
                assert call_kwargs["json"]["worker_id"] == "worker-1"
                assert call_kwargs["json"]["lease_seconds"] == 3600

    async def test_start_run_without_lease_seconds(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                backend_url="http://backend",
                internal_api_token="token-123",
            )

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"status": "running"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ) as mock_request:
                result = await client.start_run("run-123", "worker-1")

                assert result["status"] == "running"
                call_kwargs = mock_request.call_args.kwargs
                assert call_kwargs["json"]["worker_id"] == "worker-1"
                assert "lease_seconds" not in call_kwargs["json"]

    async def test_fail_run_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"status": "failed"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.fail_run(
                    "run-123", "worker-1", error_message="Something went wrong"
                )

                assert result["status"] == "failed"

    async def test_start_run_returns_empty_mapping_for_non_mapping_data(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": ["raw", "state"]}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.start_run("run-123", "worker-1")

                assert result == {}

    async def test_fail_run_returns_empty_mapping_for_non_string_mapping_keys(
        self,
    ) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(backend_url="http://backend")

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {123: "failed"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.fail_run("run-123", "worker-1")

                assert result == {}


@pytest.mark.asyncio
class TestBackendClientEnvMap:
    """Test BackendClient.get_env_map."""

    async def test_get_env_map_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": {"API_KEY": "secret", "BASE_URL": "https://api.example.com"}
            }
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client,
                "_internal_user_headers",
                wraps=client._internal_user_headers,
            ) as mock_headers:
                with patch.object(
                    client._client, "request", AsyncMock(return_value=mock_response)
                ) as mock_request:
                    result = await client.get_env_map("user-123")

            mock_headers.assert_called_once_with("user-123")
            request_headers = mock_request.call_args.kwargs["headers"]
            assert request_headers["X-Internal-Token"] == "token-123"
            assert request_headers["X-User-Id"] == "user-123"
            assert "X-Request-ID" in request_headers
            assert "X-Trace-ID" in request_headers
            assert result["API_KEY"] == "secret"


@pytest.mark.asyncio
class TestBackendClientInternalUserHeaders:
    """Test user-scoped internal backend calls use shared trusted headers."""

    async def test_get_claude_md_uses_internal_user_headers(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"content": "# Claude MD"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client,
                "_internal_user_headers",
                wraps=client._internal_user_headers,
            ) as mock_headers:
                with patch.object(
                    client._client, "request", AsyncMock(return_value=mock_response)
                ) as mock_request:
                    with patch(
                        "app.services.backend_client.httpx.AsyncClient"
                    ) as mock_async_client_cls:
                        result = await client.get_claude_md("user-123")

            mock_async_client_cls.assert_not_called()
            mock_headers.assert_called_once_with("user-123")
            request_headers = mock_request.call_args.kwargs["headers"]
            assert request_headers["X-Internal-Token"] == "token-123"
            assert request_headers["X-User-Id"] == "user-123"
            assert "X-Request-ID" in request_headers
            assert "X-Trace-ID" in request_headers
            assert result["content"] == "# Claude MD"

    async def test_get_claude_md_uses_relative_path_request(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"content": "# Claude MD"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ) as mock_request:
                result = await client.get_claude_md("user-123")

            mock_request.assert_awaited_once()
            assert mock_request.call_args.args[:2] == (
                "GET",
                "/api/v1/internal/claude-md",
            )
            assert result["content"] == "# Claude MD"


@pytest.mark.asyncio
class TestBackendClientEnvMapReturn:
    """Test BackendClient.get_env_map response handling."""

    async def test_get_env_map_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": {"API_KEY": "secret", "BASE_URL": "https://api.example.com"}
            }
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.get_env_map("user-123")

            assert result["API_KEY"] == "secret"


@pytest.mark.asyncio
class TestBackendClientResolveMcpConfig:
    """Test BackendClient.resolve_mcp_config."""

    async def test_resolve_mcp_config_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": {"server1": {"command": "uvx", "args": ["mcp-server"]}}
            }
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.resolve_mcp_config("user-123", [1, 2])

                assert "server1" in result


class TestBackendClientResolveMcpConfigReturnType:
    """Regression tests for BackendClient.resolve_mcp_config return type."""

    def test_resolve_mcp_config_return_type_is_dict_str_object(self) -> None:
        """Regression: verify resolve_mcp_config return annotation is dict[str, object], not bare dict."""
        import typing

        hints = typing.get_type_hints(BackendClient.resolve_mcp_config)
        return_type = hints.get("return")
        origin = get_origin(return_type)
        args = get_args(return_type)
        assert origin is dict, f"Expected dict origin, got {origin}"
        assert args == (str, object), f"Expected dict[str, object], got {args}"


class TestBackendClientResolveSkillConfigReturnType:
    """Regression tests for BackendClient.resolve_skill_config return type."""

    def test_resolve_skill_config_return_type_is_dict_str_object(self) -> None:
        """Regression: verify resolve_skill_config return annotation is dict[str, object], not bare dict."""
        import typing

        hints = typing.get_type_hints(BackendClient.resolve_skill_config)
        return_type = hints.get("return")
        origin = get_origin(return_type)
        args = get_args(return_type)
        assert origin is dict, f"Expected dict origin, got {origin}"
        assert args == (str, object), f"Expected dict[str, object], got {args}"


class TestBackendClientResolveSubagentsReturnType:
    """Regression tests for BackendClient.resolve_subagents return type."""

    def test_resolve_subagents_return_type_is_dict_str_object(self) -> None:
        """Regression: verify resolve_subagents return annotation is dict[str, object], not bare dict."""
        import typing

        hints = typing.get_type_hints(BackendClient.resolve_subagents)
        return_type = hints.get("return")
        origin = get_origin(return_type)
        args = get_args(return_type)
        assert origin is dict, f"Expected dict origin, got {origin}"
        assert args == (str, object), f"Expected dict[str, object], got {args}"


@pytest.mark.asyncio
class TestBackendClientResolveSkillConfig:
    """Test BackendClient.resolve_skill_config."""

    async def test_resolve_skill_config_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": {"skill1": {"content": "# Skill content"}}
            }
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.resolve_skill_config("user-123", [1])

                assert "skill1" in result

    async def test_submit_skill_from_workspace_uses_internal_headers(self) -> None:
        settings = SimpleNamespace(
            backend_url="http://backend",
            internal_api_token="token-123",
        )
        http_client = MagicMock()
        client = BackendClient(settings=settings, http_client=http_client)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {"job_id": "skill-job-123"},
            "message": "Skill submission queued",
        }

        with (
            patch.object(
                client, "_request", AsyncMock(return_value=mock_response)
            ) as mock_request,
            patch.object(
                client,
                "_internal_headers",
                return_value={"X-Internal-Token": "token-123"},
            ),
        ):
            result = await client.submit_skill_from_workspace(
                "session-123",
                folder_path="/staged/skill-folder",
                skill_name="my-skill",
                workspace_files_prefix="files/prefix/",
            )

        assert result == {
            "data": {"job_id": "skill-job-123"},
            "message": "Skill submission queued",
        }
        mock_request.assert_awaited_once_with(
            "POST",
            "/api/v1/internal/skills/submit-from-workspace",
            params={"session_id": "session-123"},
            json={
                "folder_path": "/staged/skill-folder",
                "skill_name": "my-skill",
                "workspace_files_prefix": "files/prefix/",
            },
            headers={"X-Internal-Token": "token-123"},
        )


@pytest.mark.asyncio
class TestBackendClientResolveSubagents:
    """Test BackendClient.resolve_subagents."""

    async def test_resolve_subagents_with_ids(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": {"subagent1": {"name": "researcher"}}
            }
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ) as mock_request:
                await client.resolve_subagents("user-123", [1, 2])

                # Verify subagent_ids was included
                call_args = mock_request.call_args
                assert "subagent_ids" in call_args.kwargs["json"]

    async def test_resolve_subagents_none_ids(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ) as mock_request:
                await client.resolve_subagents("user-123", None)

                # Verify subagent_ids was NOT included when None
                call_args = mock_request.call_args
                assert "subagent_ids" not in call_args.kwargs["json"]


@pytest.mark.asyncio
class TestBackendClientResolveSlashCommands:
    """Test BackendClient.resolve_slash_commands."""

    async def test_resolve_slash_commands_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": {"/help": "Help content", "/review": "Review content"}
            }
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.resolve_slash_commands("user-123")

                assert "/help" in result
                assert "/review" in result

    async def test_resolve_slash_commands_non_dict_response(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": "not a dict"}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.resolve_slash_commands("user-123")

                assert result == {}


@pytest.mark.asyncio
class TestBackendClientDispatchScheduledTasks:
    """Test BackendClient.dispatch_due_scheduled_tasks."""

    async def test_dispatch_due_scheduled_tasks_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"dispatched": 5}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.dispatch_due_scheduled_tasks(limit=100)

                assert result["dispatched"] == 5


@pytest.mark.asyncio
class TestBackendClientResolvePluginConfig:
    """Test BackendClient.resolve_plugin_config."""

    async def test_resolve_plugin_config_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"plugin1": {"enabled": True}}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.resolve_plugin_config("user-123", [1, 2])

                assert "plugin1" in result


@pytest.mark.asyncio
class TestBackendClientGetClaudeMd:
    """Test BackendClient.get_claude_md."""

    async def test_get_claude_md_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"content": "# Claude MD"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.get_claude_md("user-123")

            assert result["content"] == "# Claude MD"

    async def test_get_claude_md_non_dict_response(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": "not a dict"}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.get_claude_md("user-123")

            assert result == {}


def test_backend_client_get_claude_md_return_is_dict_str_object() -> None:
    """Regression: BackendClient.get_claude_md returns dict[str, object], not bare dict."""
    import typing
    from app.services.backend_client import BackendClient

    hints = typing.get_type_hints(BackendClient.get_claude_md)
    return_type = hints.get("return")
    assert return_type is not None, "return type not found"

    origin = get_origin(return_type)
    assert origin is dict, f"Expected dict origin, got {origin}"

    args = get_args(return_type)
    assert len(args) == 2, f"Expected 2 type args, got {len(args)}"
    key_type, value_type = args
    assert key_type is str, f"Expected str key, got {key_type}"
    assert value_type is object, f"Expected object value, got {value_type}"


def test_backend_client_get_execution_settings_return_is_dict_str_object() -> None:
    """Regression: BackendClient.get_execution_settings returns dict[str, object], not bare dict."""
    import typing
    from app.services.backend_client import BackendClient

    hints = typing.get_type_hints(BackendClient.get_execution_settings)
    return_type = hints.get("return")
    assert return_type is not None, "return type not found"

    origin = get_origin(return_type)
    assert origin is dict, f"Expected dict origin, got {origin}"

    args = get_args(return_type)
    assert len(args) == 2, f"Expected 2 type args, got {len(args)}"
    key_type, value_type = args
    assert key_type is str, f"Expected str key, got {key_type}"
    assert value_type is object, f"Expected object value, got {value_type}"


def test_backend_client_resolve_plugin_config_return_is_dict_str_object() -> None:
    """Regression: BackendClient.resolve_plugin_config returns dict[str, object], not bare dict."""
    import typing
    from app.services.backend_client import BackendClient

    hints = typing.get_type_hints(BackendClient.resolve_plugin_config)
    return_type = hints.get("return")
    assert return_type is not None, "return type not found"

    origin = get_origin(return_type)
    assert origin is dict, f"Expected dict origin, got {origin}"

    args = get_args(return_type)
    assert len(args) == 2, f"Expected 2 type args, got {len(args)}"
    key_type, value_type = args
    assert key_type is str, f"Expected str key, got {key_type}"
    assert value_type is object, f"Expected object value, got {value_type}"


def test_backend_client_update_run_metadata_param_is_dict_str_object() -> None:
    """Regression: BackendClient.update_run_metadata accepts metadata: dict[str, object], not bare dict."""
    import typing
    from app.services.backend_client import BackendClient

    hints = typing.get_type_hints(BackendClient.update_run_metadata)
    metadata_param_type = hints.get("metadata")
    assert metadata_param_type is not None, "metadata parameter type not found"

    origin = get_origin(metadata_param_type)
    assert origin is dict, f"Expected dict origin, got {origin}"

    args = get_args(metadata_param_type)
    assert len(args) == 2, f"Expected 2 type args, got {len(args)}"
    key_type, value_type = args
    assert key_type is str, f"Expected str key, got {key_type}"
    assert value_type is object, f"Expected object value, got {value_type}"


@pytest.mark.asyncio
class TestBackendClientUserInputRequests:
    """Test BackendClient user input request methods."""

    async def test_create_user_input_request_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"id": "req-123"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ) as mock_request:
                result = await client.create_user_input_request({"question": "ok?"})

            mock_request.assert_awaited_once()
            assert mock_request.call_args.args[:2] == (
                "POST",
                "/api/v1/internal/user-input-requests",
            )
            assert result["id"] == "req-123"

    async def test_create_user_input_request_returns_empty_mapping_for_non_mapping_data(
        self,
    ) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": ["raw", "payload"]}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.create_user_input_request({"question": "ok?"})

            assert result == {}

    async def test_create_user_input_request_returns_empty_mapping_for_non_string_keys(
        self,
    ) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {123: "req-123"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.create_user_input_request({"question": "ok?"})

            assert result == {}

    async def test_get_user_input_request_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"status": "pending"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ) as mock_request:
                result = await client.get_user_input_request("req-123")

            mock_request.assert_awaited_once()
            assert mock_request.call_args.args[:2] == (
                "GET",
                "/api/v1/internal/user-input-requests/req-123",
            )
            assert result["status"] == "pending"

    async def test_get_user_input_request_returns_none_for_non_mapping_data(
        self,
    ) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": None}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.get_user_input_request("req-123")

            assert result is None

    async def test_get_user_input_request_returns_none_for_non_string_keys(
        self,
    ) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {123: "pending"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.get_user_input_request("req-123")

            assert result is None


def test_backend_client_user_input_request_ports_are_structured() -> None:
    """Regression: user-input request adapter ports avoid Any and bare dict."""
    import typing

    create_hints = typing.get_type_hints(BackendClient.create_user_input_request)
    get_hints = typing.get_type_hints(BackendClient.get_user_input_request)

    payload_hint = create_hints.get("payload")
    assert payload_hint is not None
    assert "Any" not in str(payload_hint)
    assert get_origin(payload_hint) is dict
    assert get_args(payload_hint) == (str, object)

    _assert_mapping_str_object(create_hints.get("return"))

    return_hint = get_hints.get("return")
    assert return_hint is not None
    assert "Any" not in str(return_hint)
    assert "dict" not in str(return_hint)
    args = get_args(return_hint)
    mapping_type = next(
        (arg for arg in args if get_origin(arg) is Mapping),
        None,
    )
    assert mapping_type is not None
    assert get_args(mapping_type) == (str, object)


@pytest.mark.asyncio
class TestBackendClientMemoryOperations:
    """Test BackendClient memory CRUD operations."""

    async def test_create_memory_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"id": "mem-123"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ) as mock_request:
                result = await client.create_memory("sess-123", {"content": "test"})

            assert mock_request.call_args.args[:2] == (
                "POST",
                "/api/v1/internal/memories",
            )
            assert mock_request.call_args.kwargs["params"] == {"session_id": "sess-123"}
            assert result["id"] == "mem-123"

    async def test_get_memory_create_job_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"status": "completed"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.get_memory_create_job("sess-123", "job-456")

            assert result["status"] == "completed"

    async def test_list_memories_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [{"id": "mem-1"}, {"id": "mem-2"}]
            }
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.list_memories("sess-123")

            assert len(result) == 2

    async def test_search_memories_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": [{"id": "mem-1"}]}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.search_memories("sess-123", {"query": "test"})

            assert len(result) == 1

    async def test_get_memory_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": {"id": "mem-123", "content": "test"}
            }
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.get_memory("sess-123", "mem-123")

            assert result["id"] == "mem-123"

    async def test_update_memory_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": {"id": "mem-123", "updated": True}
            }
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.update_memory(
                    "sess-123", "mem-123", {"content": "updated"}
                )

            assert result["updated"] is True

    async def test_get_memory_history_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": [{"version": 1}, {"version": 2}]}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.get_memory_history("sess-123", "mem-123")

            assert len(result) == 2

    async def test_delete_memory_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"deleted": True}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.delete_memory("sess-123", "mem-123")

            assert result["deleted"] is True

    async def test_delete_memory_non_dict_response(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": None}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.delete_memory("sess-123", "mem-123")

            assert result == {}

    async def test_delete_all_memories_success(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"count": 5}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.delete_all_memories("sess-123")

            assert result["count"] == 5

    async def test_delete_all_memories_non_dict_response(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": "deleted"}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ):
                result = await client.delete_all_memories("sess-123")

            assert result == {}


@pytest.mark.asyncio
class TestBackendClientResolveSlashCommandsWithSkillNames:
    """Test BackendClient.resolve_slash_commands with skill_names parameter."""

    async def test_resolve_slash_commands_with_skill_names(self) -> None:
        with patch("app.services.backend_client.get_settings") as mock_settings:
            mock_settings_obj = MagicMock()
            mock_settings_obj.backend_url = "http://backend"
            mock_settings_obj.internal_api_token = "token-123"
            mock_settings.return_value = mock_settings_obj

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"/skill1": "Skill content"}}
            mock_response.raise_for_status = MagicMock()

            with patch.object(
                client._client, "request", AsyncMock(return_value=mock_response)
            ) as mock_request:
                result = await client.resolve_slash_commands(
                    "user-123", skill_names=["skill1"]
                )

                # Verify skill_names was included in payload
                call_args = mock_request.call_args
                assert "skill_names" in call_args.kwargs["json"]
                assert "/skill1" in result


if __name__ == "__main__":
    unittest.main()


def test_backend_client_record_mcp_transition_metadata_param_is_dict_str_object() -> (
    None
):
    """Regression: BackendClient.record_mcp_transition accepts metadata: dict[str, object], not bare dict."""
    import typing
    from app.services.backend_client import BackendClient

    hints = typing.get_type_hints(BackendClient.record_mcp_transition)
    metadata_param_type = hints.get("metadata")
    assert metadata_param_type is not None, "metadata parameter type not found"

    # Handle UnionType (Python 3.10+ syntax: dict[str, object] | None)
    origin = get_origin(metadata_param_type)
    if origin is types.UnionType or hasattr(origin, "__origin__"):
        # It's a union, get the dict part
        args = get_args(metadata_param_type)
        dict_type = next((a for a in args if get_origin(a) is dict), None)
        assert dict_type is not None, "Expected dict in union type"
        origin = get_origin(dict_type)
        args = get_args(dict_type)
    else:
        assert origin is dict, f"Expected dict origin, got {origin}"
        args = get_args(metadata_param_type)

    assert len(args) == 2, f"Expected 2 type args, got {len(args)}"
    key_type, value_type = args
    assert key_type is str, f"Expected str key, got {key_type}"
    assert value_type is object, f"Expected object value, got {value_type}"


def test_backend_client_record_permission_audit_tool_input_param_is_dict_str_object() -> (
    None
):
    """Regression: BackendClient.record_permission_audit accepts tool_input: dict[str, object], not bare dict."""
    import typing
    from app.services.backend_client import BackendClient

    hints = typing.get_type_hints(BackendClient.record_permission_audit)
    tool_input_param_type = hints.get("tool_input")
    assert tool_input_param_type is not None, "tool_input parameter type not found"

    # Handle UnionType (Python 3.10+ syntax: dict[str, object] | None)
    origin = get_origin(tool_input_param_type)
    if origin is types.UnionType or hasattr(origin, "__origin__"):
        # It's a union, get the dict part
        args = get_args(tool_input_param_type)
        dict_type = next((a for a in args if get_origin(a) is dict), None)
        assert dict_type is not None, "Expected dict in union type"
        origin = get_origin(dict_type)
        args = get_args(dict_type)
    else:
        assert origin is dict, f"Expected dict origin, got {origin}"
        args = get_args(tool_input_param_type)

    assert len(args) == 2, f"Expected 2 type args, got {len(args)}"
    key_type, value_type = args
    assert key_type is str, f"Expected str key, got {key_type}"
    assert value_type is object, f"Expected object value, got {value_type}"


def test_backend_client_record_permission_audit_context_param_is_dict_str_object() -> (
    None
):
    """Regression: BackendClient.record_permission_audit accepts context: dict[str, object], not bare dict."""
    import typing
    from app.services.backend_client import BackendClient

    hints = typing.get_type_hints(BackendClient.record_permission_audit)
    context_param_type = hints.get("context")
    assert context_param_type is not None, "context parameter type not found"

    # Handle UnionType (Python 3.10+ syntax: dict[str, object] | None)
    origin = get_origin(context_param_type)
    if origin is types.UnionType or hasattr(origin, "__origin__"):
        # It's a union, get the dict part
        args = get_args(context_param_type)
        dict_type = next((a for a in args if get_origin(a) is dict), None)
        assert dict_type is not None, "Expected dict in union type"
        origin = get_origin(dict_type)
        args = get_args(dict_type)
    else:
        assert origin is dict, f"Expected dict origin, got {origin}"
        args = get_args(context_param_type)

    assert len(args) == 2, f"Expected 2 type args, got {len(args)}"
    key_type, value_type = args
    assert key_type is str, f"Expected str key, got {key_type}"
    assert value_type is object, f"Expected object value, got {value_type}"


class TestBackendClientDispatchScheduledTasksReturnType:
    """Regression tests for BackendClient.dispatch_due_scheduled_tasks return type."""

    def test_dispatch_due_scheduled_tasks_return_type_is_dict_str_object(self) -> None:
        """Regression: verify dispatch_due_scheduled_tasks return annotation is dict[str, object], not bare dict."""
        import typing

        hints = typing.get_type_hints(BackendClient.dispatch_due_scheduled_tasks)
        return_type = hints.get("return")
        origin = get_origin(return_type)
        args = get_args(return_type)
        assert origin is dict, f"Expected dict origin, got {origin}"
        assert args == (str, object), f"Expected dict[str, object], got {args}"
