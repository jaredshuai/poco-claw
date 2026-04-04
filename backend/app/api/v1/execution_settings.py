from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id, get_db
from app.schemas.execution_settings import (
    ExecutionSettings,
    ExecutionSettingsUpdateRequest,
)
from app.schemas.permission_policy import (
    PermissionPolicy,
    PermissionPolicyUpdateRequest,
)
from app.schemas.response import Response, ResponseSchema
from app.services.execution_settings_service import ExecutionSettingsService

router = APIRouter(prefix="/execution-settings", tags=["execution-settings"])

service = ExecutionSettingsService()


def _resolve_permission_policy(settings: ExecutionSettings) -> PermissionPolicy:
    permissions = settings.permissions
    if isinstance(permissions, PermissionPolicy):
        return permissions
    return PermissionPolicy.from_dict(permissions)


@router.get("", response_model=ResponseSchema[ExecutionSettings])
async def get_execution_settings(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.get_or_create(db, user_id)
    return Response.success(data=result, message="Execution settings retrieved")


@router.patch("", response_model=ResponseSchema[ExecutionSettings])
async def update_execution_settings(
    request: ExecutionSettingsUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.update(db, user_id, request.settings)
    return Response.success(data=result, message="Execution settings updated")


@router.get("/permissions", response_model=ResponseSchema[PermissionPolicy])
async def get_permission_policy(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = service.get_or_create(db, user_id)
    return Response.success(
        data=_resolve_permission_policy(result),
        message="Permission policy retrieved",
    )


@router.patch("/permissions", response_model=ResponseSchema[PermissionPolicy])
async def update_permission_policy(
    request: PermissionPolicyUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    current_settings = service.get_or_create(db, user_id)
    current_policy = _resolve_permission_policy(current_settings)
    update_dict = request.model_dump(exclude_unset=True)
    # model_copy doesn't validate nested models; re-validate to ensure rules
    # are deserialized correctly.
    merged = current_policy.model_dump()
    merged.update(update_dict)
    updated_policy = PermissionPolicy.model_validate(merged)
    updated_settings = current_settings.model_copy(
        update={"permissions": updated_policy}
    )
    result = service.update(db, user_id, updated_settings)
    return Response.success(
        data=_resolve_permission_policy(result),
        message="Permission policy updated",
    )


@router.get("/catalog", response_model=ResponseSchema[dict])
async def get_execution_settings_catalog() -> JSONResponse:
    return Response.success(
        data={
            "hook_keys": [
                "workspace",
                "todo",
                "callback",
                "run_snapshot",
                "browser_screenshot",
            ],
            "hook_phases": ["setup", "pre_query", "message", "error", "teardown"],
            "workspace_strategies": [
                "clone",
                "worktree",
                "sparse-clone",
                "sparse-worktree",
            ],
        },
        message="Execution settings catalog retrieved",
    )
