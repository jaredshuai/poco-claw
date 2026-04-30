import logging
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.services.storage_service import S3StorageService
from app.services.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)

_GITHUB_HOSTS = {"github.com", "www.github.com"}


class AttachmentStorage(Protocol):
    def download_file(self, *, key: str, destination: Path) -> None: ...


def build_attachment_storage() -> AttachmentStorage:
    return S3StorageService()


def build_attachment_workspace_manager() -> WorkspaceManager:
    return WorkspaceManager()


class AttachmentStager:
    def __init__(
        self,
        storage_service: AttachmentStorage | None = None,
        storage_service_factory: Callable[[], AttachmentStorage] | None = None,
        workspace_manager: WorkspaceManager | None = None,
        workspace_manager_factory: Callable[[], WorkspaceManager] | None = None,
    ) -> None:
        self._storage_service = storage_service
        self._storage_service_factory = (
            storage_service_factory or build_attachment_storage
        )
        self._workspace_manager = workspace_manager
        self._workspace_manager_factory = (
            workspace_manager_factory or build_attachment_workspace_manager
        )

    @property
    def storage_service(self) -> AttachmentStorage:
        if self._storage_service is None:
            self._storage_service = self._storage_service_factory()
        return self._storage_service

    @storage_service.setter
    def storage_service(self, value: AttachmentStorage) -> None:
        self._storage_service = value

    @property
    def workspace_manager(self) -> WorkspaceManager:
        if self._workspace_manager is None:
            self._workspace_manager = self._workspace_manager_factory()
        return self._workspace_manager

    @workspace_manager.setter
    def workspace_manager(self, value: WorkspaceManager) -> None:
        self._workspace_manager = value

    def stage_inputs(
        self,
        user_id: str,
        session_id: str,
        inputs: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        if not inputs:
            return []

        started_total = time.perf_counter()

        session_dir = self.workspace_manager.get_workspace_path(
            user_id=user_id, session_id=session_id, create=True
        )
        workspace_dir = session_dir / "workspace"
        inputs_root = workspace_dir / "inputs"
        inputs_root.mkdir(parents=True, exist_ok=True)

        staged: list[dict[str, Any]] = []
        for item in inputs:
            if not isinstance(item, dict):
                continue

            kind = str(item.get("type") or item.get("kind") or "").lower()
            name = str(item.get("name") or "").strip()
            source = str(item.get("source") or item.get("url") or "").strip()
            if not kind or not source:
                continue

            target_path = item.get("target_path") or item.get("path")
            rel_path = self._normalize_relative_path(target_path)

            if kind == "file":
                s3_key = item.get("source") or item.get("s3_key") or item.get("key")
                if not s3_key:
                    continue
                if not rel_path:
                    rel_path = (
                        self._normalize_relative_path(name) or Path(str(s3_key)).name
                    )
                destination = inputs_root / rel_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                step_started = time.perf_counter()
                self.storage_service.download_file(
                    key=str(s3_key), destination=destination
                )
                logger.info(
                    "timing",
                    extra={
                        "step": "input_stage_file_download",
                        "duration_ms": int((time.perf_counter() - step_started) * 1000),
                        "user_id": user_id,
                        "session_id": session_id,
                        # "name" is reserved in LogRecord (logger name).
                        "input_name": name or destination.name,
                        "rel_path": rel_path,
                        "s3_key": str(s3_key),
                    },
                )
                staged.append(
                    self._build_staged(item, rel_path, name or destination.name)
                )
                continue

            if kind == "url":
                repo_url, branch, repo_name = self._parse_github_repo(source)
                if not rel_path:
                    rel_path = repo_name
                destination_dir = inputs_root / rel_path
                if destination_dir.exists():
                    shutil.rmtree(destination_dir, ignore_errors=True)
                destination_dir.parent.mkdir(parents=True, exist_ok=True)
                step_started = time.perf_counter()
                self._clone_repo(repo_url, destination_dir, branch)
                logger.info(
                    "timing",
                    extra={
                        "step": "input_stage_repo_clone",
                        "duration_ms": int((time.perf_counter() - step_started) * 1000),
                        "user_id": user_id,
                        "session_id": session_id,
                        # "name" is reserved in LogRecord (logger name).
                        "input_name": name or repo_name,
                        "rel_path": rel_path,
                        "repo_url": repo_url,
                        "branch": branch,
                    },
                )
                staged.append(self._build_staged(item, rel_path, name or repo_name))
                continue

        logger.info(
            "timing",
            extra={
                "step": "input_stage_total",
                "duration_ms": int((time.perf_counter() - started_total) * 1000),
                "user_id": user_id,
                "session_id": session_id,
                "inputs_requested": len(inputs),
                "inputs_staged": len(staged),
            },
        )
        return staged

    @staticmethod
    def _normalize_relative_path(raw: object) -> str | None:
        if not raw or not isinstance(raw, str):
            return None
        clean = raw.replace("\\", "/").strip()
        clean = clean.lstrip("/")
        if not clean:
            return None
        parts = [p for p in clean.split("/") if p]
        if not parts or any(p in (".", "..") for p in parts):
            return None
        return "/".join(parts)

    @staticmethod
    def _build_staged(item: dict[str, Any], rel_path: str, name: str) -> dict[str, Any]:
        staged = dict(item)
        staged["name"] = name
        staged["path"] = f"/inputs/{rel_path}"
        return staged

    @staticmethod
    def _parse_github_repo(url: str) -> tuple[str, str | None, str]:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message="Only http(s) GitHub URLs are supported",
            )
        if parsed.netloc not in _GITHUB_HOSTS:
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message="Only github.com URLs are supported",
            )

        path = parsed.path.strip("/")
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2:
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message="Invalid GitHub repository URL",
            )

        owner = parts[0]
        repo = parts[1]
        if repo.endswith(".git"):
            repo = repo[: -len(".git")]
        if not owner or not repo:
            raise AppException(
                error_code=ErrorCode.BAD_REQUEST,
                message="Invalid GitHub repository URL",
            )

        branch = None
        if len(parts) >= 4 and parts[2] == "tree":
            branch = parts[3]

        repo_url = f"https://github.com/{owner}/{repo}.git"
        return repo_url, branch, repo

    @staticmethod
    def _clone_repo(repo_url: str, destination: Path, branch: str | None) -> None:
        args = ["git", "clone", "--depth", "1", "--single-branch"]
        if branch:
            args.extend(["--branch", branch])
        args.extend([repo_url, str(destination)])

        try:
            subprocess.run(
                args,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        except subprocess.CalledProcessError as exc:
            logger.error(f"Git clone failed: {exc.stderr}")
            raise AppException(
                error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
                message="Failed to clone GitHub repository",
                details={"repo_url": repo_url, "error": exc.stderr},
            ) from exc
