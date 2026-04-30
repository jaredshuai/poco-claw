from typing import Any, Protocol


class RunDispatchExecutorGateway(Protocol):
    async def execute_run(
        self,
        *,
        executor_url: str,
        session_id: str,
        run_id: str | None,
        prompt: str,
        callback_url: str,
        callback_token: str,
        task_lease_secret: str | None,
        config: dict[str, Any],
        callback_base_url: str | None,
        sdk_session_id: str | None,
        permission_mode: str,
    ) -> str: ...


class ExecutorClientRunDispatchGateway:
    def __init__(self, executor_client: Any) -> None:
        self.executor_client = executor_client

    async def execute_run(
        self,
        *,
        executor_url: str,
        session_id: str,
        run_id: str | None,
        prompt: str,
        callback_url: str,
        callback_token: str,
        task_lease_secret: str | None,
        config: dict[str, Any],
        callback_base_url: str | None,
        sdk_session_id: str | None,
        permission_mode: str,
    ) -> str:
        return await self.executor_client.execute_task(
            executor_url=executor_url,
            session_id=session_id,
            run_id=run_id,
            prompt=prompt,
            callback_url=callback_url,
            callback_token=callback_token,
            task_lease_secret=task_lease_secret,
            config=config,
            callback_base_url=callback_base_url,
            sdk_session_id=sdk_session_id,
            permission_mode=permission_mode,
        )
