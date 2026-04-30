from typing import Protocol

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core.deps import require_callback_token
from app.schemas.computer import ComputerScreenshotUploadResponse
from app.schemas.response import Response, ResponseSchema
from app.services.computer_service import ComputerService

router = APIRouter(prefix="/computer", tags=["computer"])


class ComputerApiService(Protocol):
    def upload_browser_screenshot(
        self,
        *,
        session_id: str,
        tool_use_id: str,
        content_type: str,
        data: bytes,
    ) -> ComputerScreenshotUploadResponse: ...


computer_service: ComputerApiService | None = None


def get_computer_service() -> ComputerApiService:
    global computer_service
    if computer_service is None:
        computer_service = ComputerService()
    return computer_service


@router.post(
    "/screenshots",
    response_model=ResponseSchema[ComputerScreenshotUploadResponse],
)
async def upload_browser_screenshot(
    session_id: str = Form(...),
    tool_use_id: str = Form(...),
    file: UploadFile = File(...),
    _: None = Depends(require_callback_token),
    service: ComputerApiService = Depends(get_computer_service),
):
    """Upload a browser screenshot produced by the executor."""
    raw = await file.read()
    payload = service.upload_browser_screenshot(
        session_id=session_id,
        tool_use_id=tool_use_id,
        content_type=file.content_type or "image/png",
        data=raw,
    )
    return Response.success(data=payload.model_dump(), message="Screenshot uploaded")
