from typing import Any, Protocol


class TaskDispatchStateGateway(Protocol):
    async def mark_running(self, *, session_id: str) -> None: ...

    async def mark_failed(self, *, session_id: str) -> None: ...


class BackendTaskDispatchStateGateway:
    def __init__(self, backend_client: Any) -> None:
        self.backend_client = backend_client

    async def mark_running(self, *, session_id: str) -> None:
        await self.backend_client.update_session_status(session_id, "running")

    async def mark_failed(self, *, session_id: str) -> None:
        await self.backend_client.update_session_status(session_id, "failed")
