import pytest

from app.core.computer import ComputerClient
from app.core.user_input import UserInputClient


class _FakeResponse:
    is_success = True
    status_code = 200
    text = ""

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"data": {"id": "req-123", "status": "pending"}}


class _FakeAsyncClient:
    last_headers: dict[str, str] | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        pass

    async def post(self, url, **kwargs):
        self.__class__.last_headers = kwargs["headers"]
        return _FakeResponse()

    async def get(self, url, **kwargs):
        self.__class__.last_headers = kwargs["headers"]
        return _FakeResponse()


@pytest.mark.asyncio
async def test_computer_client_sends_callback_token(monkeypatch) -> None:
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    client = ComputerClient(
        base_url="http://executor-manager",
        callback_token="callback-token",
    )

    uploaded = await client.upload_browser_screenshot(
        session_id="session-123",
        tool_use_id="tool-456",
        png_bytes=b"png",
    )

    assert uploaded is True
    assert _FakeAsyncClient.last_headers is not None
    assert _FakeAsyncClient.last_headers["Authorization"] == "Bearer callback-token"


@pytest.mark.asyncio
async def test_user_input_client_sends_callback_token(monkeypatch) -> None:
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    client = UserInputClient(
        base_url="http://executor-manager",
        callback_token="callback-token",
    )

    result = await client.create_request(
        {
            "session_id": "session-123",
            "tool_name": "ask_user",
            "tool_input": {"question": "Continue?"},
        }
    )

    assert result["id"] == "req-123"
    assert _FakeAsyncClient.last_headers is not None
    assert _FakeAsyncClient.last_headers["Authorization"] == "Bearer callback-token"
