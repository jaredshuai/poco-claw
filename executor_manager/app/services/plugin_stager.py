import logging
import re
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.storage_service import S3StorageService
from app.services.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)


class PluginStorage(Protocol):
    def download_prefix(self, *, prefix: str, destination_dir: Path) -> None: ...

    def download_file(self, *, key: str, destination: Path) -> None: ...


def build_plugin_storage() -> PluginStorage:
    return S3StorageService()


def build_plugin_workspace_manager() -> WorkspaceManager:
    return WorkspaceManager()


class PluginStager:
    def __init__(
        self,
        storage_service: PluginStorage | None = None,
        storage_service_factory: Callable[[], PluginStorage] | None = None,
        workspace_manager: WorkspaceManager | None = None,
        workspace_manager_factory: Callable[[], WorkspaceManager] | None = None,
    ) -> None:
        self._storage_service = storage_service
        self._storage_service_factory = storage_service_factory or build_plugin_storage
        self._workspace_manager = workspace_manager
        self._workspace_manager_factory = (
            workspace_manager_factory or build_plugin_workspace_manager
        )

    @property
    def storage_service(self) -> PluginStorage:
        if self._storage_service is None:
            self._storage_service = self._storage_service_factory()
        return self._storage_service

    @storage_service.setter
    def storage_service(self, value: PluginStorage) -> None:
        self._storage_service = value

    @property
    def workspace_manager(self) -> WorkspaceManager:
        if self._workspace_manager is None:
            self._workspace_manager = self._workspace_manager_factory()
        return self._workspace_manager

    @workspace_manager.setter
    def workspace_manager(self, value: WorkspaceManager) -> None:
        self._workspace_manager = value

    @staticmethod
    def _validate_plugin_name(name: str) -> None:
        if name in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9._-]+", name):
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message=f"Invalid plugin name: {name}",
            )

    @staticmethod
    def _clean_plugins_dir(plugins_root: Path, keep_names: set[str]) -> int:
        removed = 0
        plugins_root_resolved = plugins_root.resolve()
        for entry in plugins_root.iterdir():
            if not entry.is_dir() or entry.is_symlink():
                continue
            if entry.name in keep_names:
                continue
            try:
                entry.resolve().relative_to(plugins_root_resolved)
            except Exception:
                continue
            try:
                shutil.rmtree(entry)
                removed += 1
            except Exception:
                continue
        return removed

    def stage_plugins(
        self, user_id: str, session_id: str, plugins: dict[str, object] | None
    ) -> dict[str, dict[str, object]]:
        started_total = time.perf_counter()

        session_dir = self.workspace_manager.get_workspace_path(
            user_id=user_id, session_id=session_id, create=True
        )
        workspace_dir = session_dir / "workspace"
        plugins_root = workspace_dir / ".claude_data" / "plugins"
        plugins_root.mkdir(parents=True, exist_ok=True)

        enabled_names: set[str] = set()
        for name, spec in (cast(dict[str, object], plugins) or {}).items():
            if not isinstance(spec, dict):
                continue
            self._validate_plugin_name(name)
            if spec.get("enabled") is False:
                continue
            enabled_names.add(name)

        removed = self._clean_plugins_dir(plugins_root, enabled_names)

        staged: dict[str, dict[str, object]] = {}
        plugins_root_resolved = plugins_root.resolve()
        for name, spec in (cast(dict[str, object], plugins) or {}).items():
            if not isinstance(spec, dict):
                continue
            self._validate_plugin_name(name)
            if spec.get("enabled") is False:
                staged[name] = {"enabled": False}
                continue
            entry_dict = (
                cast(dict[str, object], spec.get("entry"))
                if isinstance(spec.get("entry"), dict)
                else cast(dict[str, object], spec)
            )
            entry = entry_dict
            s3_key = entry.get("s3_key") or entry.get("key")
            if not s3_key:
                continue
            target_dir = (plugins_root / name).resolve()
            if plugins_root_resolved not in target_dir.parents:
                raise AppException(
                    error_code=ErrorCode.BAD_REQUEST,
                    message=f"Invalid plugin path: {name}",
                )
            target_dir.mkdir(parents=True, exist_ok=True)

            try:
                step_started = time.perf_counter()
                if entry.get("is_prefix") or str(s3_key).endswith("/"):
                    self.storage_service.download_prefix(
                        prefix=str(s3_key), destination_dir=target_dir
                    )
                else:
                    filename = Path(str(s3_key)).name
                    destination = target_dir / filename
                    self.storage_service.download_file(
                        key=str(s3_key), destination=destination
                    )
                logger.info(
                    "timing",
                    extra={
                        "step": "plugin_stage_download",
                        "duration_ms": int((time.perf_counter() - step_started) * 1000),
                        "user_id": user_id,
                        "session_id": session_id,
                        "plugin_name": name,
                        "s3_key": str(s3_key),
                        "is_prefix": bool(entry.get("is_prefix"))
                        or str(s3_key).endswith("/"),
                    },
                )
            except Exception as exc:
                raise AppException(
                    error_code=ErrorCode.PLUGIN_DOWNLOAD_FAILED,
                    message=f"Failed to stage plugin {name}: {exc}",
                ) from exc

            staged[name] = {
                **spec,
                "enabled": True,
                "local_path": str(target_dir),
                "entry": entry,
            }

        logger.info(
            "timing",
            extra={
                "step": "plugin_stage_total",
                "duration_ms": int((time.perf_counter() - started_total) * 1000),
                "user_id": user_id,
                "session_id": session_id,
                "plugins_requested": len(plugins or {}),
                "plugins_staged": len(staged),
                "plugins_removed": removed,
            },
        )
        return staged
