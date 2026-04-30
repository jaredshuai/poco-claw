from typing import Any, Protocol


class RunDispatchStateGateway(Protocol):
    async def record_mcp_staged(
        self,
        *,
        run_id: str,
        session_id: str,
        server_name: str,
    ) -> None: ...

    async def start_run(self, *, run_id: Any, worker_id: str) -> None: ...

    async def fail_run(
        self,
        *,
        run_id: Any,
        worker_id: str,
        error_message: str,
    ) -> None: ...


class BackendRunDispatchStateGateway:
    def __init__(self, backend_client: Any) -> None:
        self.backend_client = backend_client

    async def record_mcp_staged(
        self,
        *,
        run_id: str,
        session_id: str,
        server_name: str,
    ) -> None:
        await self.backend_client.record_mcp_transition(
            run_id=run_id,
            session_id=session_id,
            server_name=server_name,
            to_state="staged",
            event_source="executor_manager",
        )

    async def start_run(self, *, run_id: Any, worker_id: str) -> None:
        await self.backend_client.start_run(run_id=run_id, worker_id=worker_id)

    async def fail_run(
        self,
        *,
        run_id: Any,
        worker_id: str,
        error_message: str,
    ) -> None:
        await self.backend_client.fail_run(
            run_id=run_id,
            worker_id=worker_id,
            error_message=error_message,
        )
