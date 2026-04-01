from typing import Any

from app.hooks.base import AgentHook, ExecutionContext


class HookManager:
    def __init__(self, hooks: list[AgentHook]):
        self.hooks = sorted(
            hooks,
            key=lambda hook: int(
                getattr(hook, "hook_spec", {}).get("order", 100)
                if isinstance(getattr(hook, "hook_spec", {}), dict)
                else 100
            ),
        )

    async def run_on_setup(self, context: ExecutionContext):
        for hook in self.hooks:
            await hook.on_setup(context)

    async def run_on_response(self, context: ExecutionContext, message: Any):
        for hook in self.hooks:
            await hook.on_agent_response(context, message)

    async def run_on_teardown(self, context: ExecutionContext):
        for hook in reversed(self.hooks):
            await hook.on_teardown(context)

    async def run_on_error(self, context: ExecutionContext, error: Exception):
        for hook in self.hooks:
            await hook.on_error(context, error)
