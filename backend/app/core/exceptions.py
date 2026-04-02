"""Application exception classes and FastAPI exception handlers."""

from fastapi import Request
from fastapi.responses import JSONResponse

from app.schemas.response import ErrorCodes, error_response
from app.utils.logger import logger


class AppException(Exception):
    """Base application exception with error code support."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = ErrorCodes.BAD_REQUEST,
        details: list[str] | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, entity: str, entity_id: int | str):
        super().__init__(
            message=f"{entity} with id '{entity_id}' not found",
            status_code=404,
            error_code=ErrorCodes.NOT_FOUND,
        )


class ValidationException(AppException):
    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(
            message=message,
            status_code=422,
            error_code=ErrorCodes.VALIDATION_FAILED,
            details=details,
        )


class ConflictException(AppException):
    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=409,
            error_code=ErrorCodes.CONFLICT,
        )


class GenerationException(AppException):
    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(
            message=message,
            status_code=500,
            error_code=ErrorCodes.GENERATION_FAILED,
            details=details,
        )


class AiServiceException(AppException):
    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(
            message=message,
            status_code=503,
            error_code=ErrorCodes.AI_SERVICE_ERROR,
            details=details,
        )


async def app_exception_handler(_request: Request, exc: AppException) -> JSONResponse:
    logger.warning("AppException: %s (code=%s, status=%d)", exc.message, exc.error_code, exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(exc.error_code, exc.message, exc.details),
    )


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content=error_response(
            ErrorCodes.INTERNAL_ERROR,
            "Internal server error",
        ),
    )
