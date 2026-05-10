import hashlib
import hmac
import inspect
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.executor_client import ExecutorClient


class TestExecutorClientInit(unittest.TestCase):
    """Test ExecutorClient.__init__."""

    def test_init_no_settings_parameter(self) -> None:
        """Regression: __init__ must not expose a settings parameter."""
        sig = inspect.signature(ExecutorClient.__init__)
        assert "settings" not in sig.parameters

    def test_init_no_any_in_annotations(self) -> None:
        """Regression: __init__ must not reference Any in its annotations."""
        annotations = ExecutorClient.__init__.__annotations__
        param_annotations = {k: v for k, v in annotations.items() if k != "return"}
        for name, annotation in param_annotations.items():
            assert "Any" not in str(annotation), (
                f"Parameter '{name}' references Any: {annotation}"
            )

    def test_init_accepts_clock_and_task_client_factory(self) -> None:
        """__init__ should accept clock and task_client_factory."""
        clock = MagicMock()
        task_client_factory = MagicMock()
        client = ExecutorClient(clock=clock, task_client_factory=task_client_factory)
        assert client.clock is clock
        assert client.task_client_factory is task_client_factory


class TestExecutorClientTraceHeaders(unittest.TestCase):
    """Test ExecutorClient._trace_headers."""

    def test_trace_headers_with_existing_ids(self) -> None:
        with patch("app.services.executor_client.get_request_id") as mock_get_req:
            with patch("app.services.executor_client.get_trace_id") as mock_get_trace:
                mock_get_req.return_value = "req-123"
                mock_get_trace.return_value = "trace-456"

                headers = ExecutorClient._trace_headers()

                assert headers["X-Request-ID"] == "req-123"
                assert headers["X-Trace-ID"] == "trace-456"

    def test_trace_headers_generates_ids(self) -> None:
        with patch("app.services.executor_client.get_request_id") as mock_get_req:
            with patch("app.services.executor_client.get_trace_id") as mock_get_trace:
                with patch(
                    "app.services.executor_client.generate_request_id"
                ) as mock_gen_req:
                    with patch(
                        "app.services.executor_client.generate_trace_id"
                    ) as mock_gen_trace:
                        mock_get_req.return_value = None
                        mock_get_trace.return_value = None
                        mock_gen_req.return_value = "new-req-123"
                        mock_gen_trace.return_value = "new-trace-456"

                        headers = ExecutorClient._trace_headers()

                        assert headers["X-Request-ID"] == "new-req-123"
                        assert headers["X-Trace-ID"] == "new-trace-456"


@pytest.mark.asyncio
class TestExecutorClientExecuteTask:
    """Test ExecutorClient.execute_task."""

    async def test_execute_task_success(self) -> None:
        client = ExecutorClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"session_id": "session-123"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await client.execute_task(
                executor_url="http://executor:8080",
                session_id="session-123",
                run_id="run-456",
                prompt="Hello",
                callback_url="http://callback",
                callback_token="token-abc",
                config={"model": "claude"},
            )

            assert result == "session-123"
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            headers = call_args.kwargs["headers"]
            assert headers["Authorization"] == "Bearer token-abc"
            assert "X-Poco-Task-Lease-Expires-At" in headers
            assert "X-Poco-Task-Lease-Signature" in headers

    async def test_execute_task_uses_injected_http_client_factory(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"session_id": "session-123"}
        mock_response.raise_for_status = MagicMock()
        task_client = AsyncMock()
        task_client.__aenter__.return_value = task_client
        task_client.post = AsyncMock(return_value=mock_response)
        task_client_factory = MagicMock(return_value=task_client)
        client = ExecutorClient(task_client_factory=task_client_factory)

        with patch(
            "app.services.executor_client.httpx.AsyncClient",
            side_effect=AssertionError("task client should be injected"),
        ):
            result = await client.execute_task(
                executor_url="http://executor:8080",
                session_id="session-123",
                run_id="run-456",
                prompt="Hello",
                callback_url="http://callback",
                callback_token="token-abc",
                config={"model": "claude"},
            )

        assert result == "session-123"
        task_client_factory.assert_called_once_with()
        task_client.post.assert_awaited_once()

    async def test_execute_task_signs_task_lease(self) -> None:
        clock = MagicMock()
        clock.now_utc.return_value = datetime.fromtimestamp(1000, tz=timezone.utc)
        client = ExecutorClient(clock=clock)

        mock_response = MagicMock()
        mock_response.json.return_value = {"session_id": "session-123"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            await client.execute_task(
                executor_url="http://executor:8080",
                session_id="session-123",
                run_id="run-456",
                prompt="Hello",
                callback_url="http://callback",
                callback_token="token-abc",
                config={"model": "claude"},
            )

        call_args = mock_client.post.call_args
        headers = call_args.kwargs["headers"]
        assert headers["X-Poco-Task-Lease-Expires-At"] == "1300"
        clock.now_utc.assert_called_once_with()
        body_digest = headers["X-Poco-Task-Lease-Body-SHA256"]
        expected_payload = f"session-123\nrun-456\n1300\n{body_digest}".encode()
        expected_signature = hmac.new(
            b"token-abc",
            expected_payload,
            hashlib.sha256,
        ).hexdigest()
        assert headers["X-Poco-Task-Lease-Signature"] == expected_signature

    async def test_execute_task_signs_task_lease_with_dedicated_secret(self) -> None:
        clock = MagicMock()
        clock.now_utc.return_value = datetime.fromtimestamp(1000, tz=timezone.utc)
        client = ExecutorClient(clock=clock)

        mock_response = MagicMock()
        mock_response.json.return_value = {"session_id": "session-123"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            await client.execute_task(
                executor_url="http://executor:8080",
                session_id="session-123",
                run_id="run-456",
                prompt="Hello",
                callback_url="http://callback",
                callback_token="callback-token",
                task_lease_secret="lease-secret",
                config={"model": "claude"},
            )

        call_args = mock_client.post.call_args
        headers = call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer callback-token"
        assert headers["X-Poco-Task-Lease-Expires-At"] == "1300"
        clock.now_utc.assert_called_once_with()
        body_digest = headers["X-Poco-Task-Lease-Body-SHA256"]
        expected_payload = f"session-123\nrun-456\n1300\n{body_digest}".encode()
        expected_signature = hmac.new(
            b"lease-secret",
            expected_payload,
            hashlib.sha256,
        ).hexdigest()
        assert headers["X-Poco-Task-Lease-Signature"] == expected_signature

    async def test_execute_task_with_optional_params(self) -> None:
        client = ExecutorClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"session_id": "session-123"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await client.execute_task(
                executor_url="http://executor:8080",
                session_id="session-123",
                run_id=None,
                prompt="Hello",
                callback_url="http://callback",
                callback_token="token-abc",
                config={"model": "claude"},
                callback_base_url="http://base",
                sdk_session_id="sdk-789",
                permission_mode="acceptEdits",
            )

            assert result == "session-123"
            call_args = mock_client.post.call_args
            body = call_args.kwargs["content"]
            import json

            body_data = json.loads(body)
            assert body_data["callback_base_url"] == "http://base"
            assert body_data["sdk_session_id"] == "sdk-789"
            assert body_data["permission_mode"] == "acceptEdits"

    async def test_execute_task_http_error(self) -> None:
        client = ExecutorClient()

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Error", request=MagicMock(), response=MagicMock()
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                await client.execute_task(
                    executor_url="http://executor:8080",
                    session_id="session-123",
                    run_id=None,
                    prompt="Hello",
                    callback_url="http://callback",
                    callback_token="token-abc",
                    config={},
                )

    async def test_execute_task_includes_body_digest_header(self) -> None:
        """ExecutorClient must include body digest header in task execution requests."""
        clock = MagicMock()
        clock.now_utc.return_value = datetime.fromtimestamp(1000, tz=timezone.utc)
        client = ExecutorClient(clock=clock)

        mock_response = MagicMock()
        mock_response.json.return_value = {"session_id": "session-123"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            await client.execute_task(
                executor_url="http://executor:8080",
                session_id="session-123",
                run_id="run-456",
                prompt="Hello",
                callback_url="http://callback",
                callback_token="token-abc",
                config={"model": "claude"},
            )

        call_args = mock_client.post.call_args
        headers = call_args.kwargs["headers"]
        assert "X-Poco-Task-Lease-Body-SHA256" in headers
        body_digest = headers["X-Poco-Task-Lease-Body-SHA256"]
        assert len(body_digest) == 64
        assert all(c in "0123456789abcdef" for c in body_digest)

    async def test_execute_task_sets_content_type_header(self) -> None:
        """ExecutorClient must set Content-Type: application/json header."""
        clock = MagicMock()
        clock.now_utc.return_value = datetime.fromtimestamp(1000, tz=timezone.utc)
        client = ExecutorClient(clock=clock)

        mock_response = MagicMock()
        mock_response.json.return_value = {"session_id": "session-123"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            await client.execute_task(
                executor_url="http://executor:8080",
                session_id="session-123",
                run_id="run-456",
                prompt="Hello",
                callback_url="http://callback",
                callback_token="token-abc",
                config={"model": "claude"},
            )

        call_args = mock_client.post.call_args
        headers = call_args.kwargs["headers"]
        assert headers["Content-Type"] == "application/json"

    async def test_execute_task_body_digest_matches_content(self) -> None:
        """Body digest header must match SHA-256 of actual content bytes."""
        clock = MagicMock()
        clock.now_utc.return_value = datetime.fromtimestamp(1000, tz=timezone.utc)
        client = ExecutorClient(clock=clock)

        mock_response = MagicMock()
        mock_response.json.return_value = {"session_id": "session-123"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            await client.execute_task(
                executor_url="http://executor:8080",
                session_id="session-123",
                run_id="run-456",
                prompt="Hello",
                callback_url="http://callback",
                callback_token="token-abc",
                config={"model": "claude"},
            )

        call_args = mock_client.post.call_args
        headers = call_args.kwargs["headers"]
        content = call_args.kwargs["content"]
        body_digest = headers["X-Poco-Task-Lease-Body-SHA256"]

        expected_digest = hashlib.sha256(content).hexdigest()
        assert body_digest == expected_digest

    async def test_execute_task_signs_body_digest(self) -> None:
        """Signature must include body digest so tampered body is rejected."""
        clock = MagicMock()
        clock.now_utc.return_value = datetime.fromtimestamp(1000, tz=timezone.utc)
        client = ExecutorClient(clock=clock)

        mock_response = MagicMock()
        mock_response.json.return_value = {"session_id": "session-123"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            await client.execute_task(
                executor_url="http://executor:8080",
                session_id="session-123",
                run_id="run-456",
                prompt="Hello",
                callback_url="http://callback",
                callback_token="token-abc",
                config={"model": "claude"},
            )

        call_args = mock_client.post.call_args
        headers = call_args.kwargs["headers"]
        body_digest = headers["X-Poco-Task-Lease-Body-SHA256"]

        expected_payload = f"session-123\nrun-456\n1300\n{body_digest}".encode()
        expected_signature = hmac.new(
            b"token-abc",
            expected_payload,
            hashlib.sha256,
        ).hexdigest()
        assert headers["X-Poco-Task-Lease-Signature"] == expected_signature


if __name__ == "__main__":
    unittest.main()
