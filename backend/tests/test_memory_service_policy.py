from threading import Lock
from typing import Any

import pytest

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.memory_service import DEFAULT_MEMORY_AGENT_ID, MemoryService


class FakeMemoryInstance:
    def __init__(self, scoped_memories: Any) -> None:
        self.scoped_memories = scoped_memories
        self.get_all_calls: list[dict[str, Any]] = []
        self.get_calls: list[str] = []
        self.update_calls: list[dict[str, str]] = []
        self.history_calls: list[str] = []
        self.delete_calls: list[str] = []

    def get_all(self, **params: Any) -> Any:
        self.get_all_calls.append(params)
        return self.scoped_memories

    def get(self, memory_id: str) -> dict[str, str]:
        self.get_calls.append(memory_id)
        return {"id": memory_id, "memory": "owned memory"}

    def update(self, *, memory_id: str, text: str) -> dict[str, str]:
        self.update_calls.append({"memory_id": memory_id, "text": text})
        return {"id": memory_id, "memory": text}

    def history(self, *, memory_id: str) -> list[dict[str, str]]:
        self.history_calls.append(memory_id)
        return [{"memory_id": memory_id, "event": "created"}]

    def delete(self, *, memory_id: str) -> None:
        self.delete_calls.append(memory_id)


def _memory_service(instance: FakeMemoryInstance) -> MemoryService:
    service = MemoryService()
    service._enabled = True
    service._custom_config = None
    service._instance = instance
    service._lock = Lock()
    return service


def _assert_not_found(exc: pytest.ExceptionInfo[AppException]) -> None:
    assert exc.value.error_code is ErrorCode.NOT_FOUND
    assert exc.value.message == "Memory not found"


def test_get_memory_requires_memory_in_user_scope():
    instance = FakeMemoryInstance([{"id": "mem-owned"}])
    service = _memory_service(instance)

    result = service.get_memory(memory_id="mem-owned", user_id="user-1")

    assert result == {"id": "mem-owned", "memory": "owned memory"}
    assert instance.get_all_calls == [
        {"user_id": "user-1", "agent_id": DEFAULT_MEMORY_AGENT_ID}
    ]
    assert instance.get_calls == ["mem-owned"]


def test_get_memory_accepts_results_wrapped_scope_payload():
    instance = FakeMemoryInstance({"results": [{"memory_id": "mem-owned"}]})
    service = _memory_service(instance)

    result = service.get_memory(memory_id="mem-owned", user_id="user-1")

    assert result["id"] == "mem-owned"
    assert instance.get_calls == ["mem-owned"]


def test_update_memory_rejects_memory_outside_user_scope():
    instance = FakeMemoryInstance([{"id": "mem-other"}])
    service = _memory_service(instance)

    with pytest.raises(AppException) as exc:
        service.update_memory(
            memory_id="mem-owned",
            user_id="user-1",
            text="updated",
        )

    _assert_not_found(exc)
    assert instance.update_calls == []


def test_get_memory_history_rejects_memory_outside_user_scope():
    instance = FakeMemoryInstance([{"id": "mem-other"}])
    service = _memory_service(instance)

    with pytest.raises(AppException) as exc:
        service.get_memory_history(memory_id="mem-owned", user_id="user-1")

    _assert_not_found(exc)
    assert instance.history_calls == []


def test_delete_memory_rejects_memory_outside_user_scope():
    instance = FakeMemoryInstance([{"id": "mem-other"}])
    service = _memory_service(instance)

    with pytest.raises(AppException) as exc:
        service.delete_memory(memory_id="mem-owned", user_id="user-1")

    _assert_not_found(exc)
    assert instance.delete_calls == []
