import asyncio
from functools import lru_cache
from typing import Any, Protocol

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.deps import require_callback_token
from app.schemas.response import Response, ResponseSchema
from app.services.backend_client import BackendClient
from app.services.workspace_export_service import WorkspaceExportService

router = APIRouter(prefix="/skills", tags=["skills"])


class SkillsUploadBackendClient(Protocol):
    async def submit_skill_from_workspace(
        self,
        session_id: str,
        *,
        folder_path: str,
        skill_name: str | None,
        workspace_files_prefix: str,
    ) -> dict[str, Any]: ...


class SkillsUploadWorkspaceExportService(Protocol):
    def stage_skill_submission_folder(
        self, session_id: str, *, folder_path: str
    ) -> str: ...

    def export_workspace_folder(self, session_id: str, *, folder_path: str) -> Any: ...


def build_backend_client() -> SkillsUploadBackendClient:
    return BackendClient()


@lru_cache(maxsize=1)
def get_backend_client() -> SkillsUploadBackendClient:
    return build_backend_client()


def build_workspace_export_service() -> SkillsUploadWorkspaceExportService:
    return WorkspaceExportService()


@lru_cache(maxsize=1)
def get_workspace_export_service() -> SkillsUploadWorkspaceExportService:
    return build_workspace_export_service()


class SkillSubmitRequest(BaseModel):
    session_id: str
    folder_path: str
    skill_name: str | None = None


async def _prepare_and_export_skill_folder(
    session_id: str,
    *,
    folder_path: str,
    exporter: SkillsUploadWorkspaceExportService,
) -> tuple[str, str]:
    staged_folder_path = await asyncio.to_thread(
        exporter.stage_skill_submission_folder,
        session_id,
        folder_path=folder_path,
    )
    result = await asyncio.to_thread(
        exporter.export_workspace_folder,
        session_id,
        folder_path=staged_folder_path,
    )
    if result.workspace_export_status != "ready":
        raise HTTPException(
            status_code=400,
            detail=result.error or "Skill folder export failed",
        )
    workspace_files_prefix = (result.workspace_files_prefix or "").strip()
    if not workspace_files_prefix:
        raise HTTPException(
            status_code=400, detail="Skill folder export is missing files"
        )
    return staged_folder_path, workspace_files_prefix


@router.post("/submit", response_model=ResponseSchema[dict])
async def submit_skill(
    request: SkillSubmitRequest,
    _: None = Depends(require_callback_token),
    backend: SkillsUploadBackendClient = Depends(get_backend_client),
    exporter: SkillsUploadWorkspaceExportService = Depends(
        get_workspace_export_service
    ),
) -> JSONResponse:
    folder_path, workspace_files_prefix = await _prepare_and_export_skill_folder(
        request.session_id,
        folder_path=request.folder_path,
        exporter=exporter,
    )
    try:
        payload = await backend.submit_skill_from_workspace(
            request.session_id,
            folder_path=folder_path,
            skill_name=request.skill_name,
            workspace_files_prefix=workspace_files_prefix,
        )
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        try:
            payload = exc.response.json()
            detail = payload.get("message") or payload.get("detail") or detail
        except Exception:
            pass
        raise HTTPException(
            status_code=exc.response.status_code, detail=detail
        ) from exc

    return Response.success(
        data=payload.get("data"),
        message=payload.get("message", "Skill submission queued successfully"),
    )
