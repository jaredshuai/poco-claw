import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.errors.error_codes import ErrorCode
from app.core.errors.exceptions import AppException
from app.schemas.response import Response

logger = logging.getLogger(__name__)

# Map ErrorCode enums to their corresponding HTTP status codes.
# Any ErrorCode not listed here defaults to 400 (Bad Request).
_ERROR_CODE_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.BAD_REQUEST: 400,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
}


def setup_exception_handlers(app: FastAPI, *, debug: bool) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request, exc: AppException
    ) -> JSONResponse:
        status_code = _ERROR_CODE_HTTP_STATUS.get(exc.error_code, 400)
        return Response.error(
            code=exc.code,
            message=exc.message,
            data=exc.details,
            status_code=status_code,
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        if isinstance(exc.detail, dict):
            message_value = exc.detail.get("message")
            message = (
                message_value if isinstance(message_value, str) else str(exc.detail)
            )
            data = exc.detail
        else:
            message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            data = None

        return Response.error(
            code=exc.status_code,
            message=message,
            data=data,
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception")

        data = {"type": type(exc).__name__, "message": str(exc)} if debug else None

        return Response.error(
            code=ErrorCode.INTERNAL_ERROR.code,
            message=ErrorCode.INTERNAL_ERROR.message,
            data=data,
            status_code=500,
        )
