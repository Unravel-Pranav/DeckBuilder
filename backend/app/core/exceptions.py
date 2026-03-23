"""Application exception classes and FastAPI exception handlers."""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.utils.logger import logger


class AppException(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, entity: str, entity_id: int | str):
        super().__init__(f"{entity} with id '{entity_id}' not found", status_code=404)


class ValidationException(AppException):
    def __init__(self, message: str):
        super().__init__(message=message, status_code=422)


class ConflictException(AppException):
    def __init__(self, message: str):
        super().__init__(message=message, status_code=409)


async def app_exception_handler(_request: Request, exc: AppException) -> JSONResponse:
    logger.warning("AppException: %s (status=%d)", exc.message, exc.status_code)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
