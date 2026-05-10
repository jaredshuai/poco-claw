from typing import Protocol

from app.services.run_dispatch_execution_context import RunDispatchExecutionContext


class RunDispatchExecutorClientPort(Protocol):
    """Minimal protocol for executor client required by run dispatch."""

    async def execute_task(
        self,
        *,
        executor_url: str,
        session_id: str,
        run_id: str | None,
        prompt: str,
        callback_url: str,
        callback_token: str,
        task_lease_secret: str,
        config: dict[str, object],
        callback_base_url: str,
        sdk_session_id: str | None,
        permission_mode: str,
    ) -> str: ...


class RunDispatchExecutorGateway(Protocol):
    async def execute_run(
        self,
        *,
        executor_url: str,
        session_id: str,
        run_id: str,
        prompt: str,
        execution_context: RunDispatchExecutionContext,
        config: dict[str, object],
        sdk_session_id: str | None,
        permission_mode: str,
    ) -> str: ...


class ExecutorClientRunDispatchGateway:
    def __init__(self, executor_client: RunDispatchExecutorClientPort) -> None:
        self.executor_client = executor_client

    async def execute_run(
        self,
        *,
        executor_url: str,
        session_id: str,
        run_id: str,
        prompt: str,
        execution_context: RunDispatchExecutionContext,
        config: dict[str, object],
        sdk_session_id: str | None,
        permission_mode: str,
    ) -> str:
        return await self.executor_client.execute_task(
            executor_url=executor_url,
            session_id=session_id,
            run_id=run_id,
            prompt=prompt,
            callback_url=execution_context.callback_url,
            callback_token=execution_context.callback_token,
            task_lease_secret=execution_context.task_lease_secret,
            config=config,
            callback_base_url=execution_context.callback_base_url,
            sdk_session_id=sdk_session_id,
            permission_mode=permission_mode,
        )
