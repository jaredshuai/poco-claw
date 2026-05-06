from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Self


@dataclass(frozen=True)
class RunDispatchClaim:
    run_id: object
    session_id: str
    user_id: str
    prompt: str
    config_snapshot: dict[str, Any]
    sdk_session_id: str | None = None
    permission_mode: str = "default"

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Self | None:
        run = payload.get("run") or {}
        if not isinstance(run, Mapping):
            return None

        run_id = run.get("run_id")
        session_id = run.get("session_id")
        user_id = payload.get("user_id") or ""
        prompt = payload.get("prompt") or ""
        if not run_id or not session_id or not user_id or not prompt:
            return None

        config_snapshot = payload.get("config_snapshot") or {}
        if not isinstance(config_snapshot, dict):
            config_snapshot = {}

        raw_permission_mode = str(run.get("permission_mode") or "default").strip()
        permission_mode = raw_permission_mode or "default"
        sdk_session_id = (
            None if run.get("scheduled_task_id") else payload.get("sdk_session_id")
        )

        return cls(
            run_id=run_id,
            session_id=str(session_id),
            user_id=str(user_id),
            prompt=str(prompt),
            config_snapshot=config_snapshot,
            sdk_session_id=str(sdk_session_id) if sdk_session_id else None,
            permission_mode=permission_mode,
        )

    @property
    def run_id_str(self) -> str:
        return str(self.run_id)

    @property
    def container_mode(self) -> str:
        return str(self.config_snapshot.get("container_mode") or "ephemeral")

    @property
    def container_id(self) -> str | None:
        container_id = self.config_snapshot.get("container_id")
        return str(container_id) if container_id is not None else None
