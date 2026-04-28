import pytest

from app.core.callback import CallbackClient
from app.schemas.callback import AgentCallbackRequest, CallbackStatus


class _FakeResponse:
    is_success = True


class _FakeAsyncClient:
    last_headers: dict[str, str] | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        pass

    async def post(self, url, *, json, headers):
        self.__class__.last_headers = headers
        return _FakeResponse()


@pytest.mark.asyncio
async def test_callback_client_sends_callback_token(monkeypatch) -> None:
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    client = CallbackClient(
        callback_url="http://executor-manager/api/v1/callback",
        callback_token="callback-token",
    )

    sent = await client.send(
        AgentCallbackRequest(
            session_id="session-123",
            run_id="run-456",
            status=CallbackStatus.RUNNING,
            progress=10,
        )
    )

    assert sent is True
    assert _FakeAsyncClient.last_headers is not None
    assert _FakeAsyncClient.last_headers["Authorization"] == "Bearer callback-token"
