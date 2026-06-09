"""Structured error responses.

Every error returned by the API uses a consistent JSON body so clients can
reliably branch on a machine-readable code:

    {"error_code": "not_found", "message": "Device not found"}

`AppError` is the base class for all application-raised errors. FastAPI/Starlette
``HTTPException`` and validation errors are also normalised into this shape by
the handlers installed in `register_exception_handlers`.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for application errors with a structured body.

    Attributes:
        error_code: machine-readable, snake_case identifier for the error.
        message: human-readable description safe to show to the client.
        status_code: HTTP status code to return.
    """

    error_code: str = "internal_error"
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if error_code is not None:
            self.error_code = error_code
        if status_code is not None:
            self.status_code = status_code

    def to_body(self) -> dict[str, str]:
        return {"error_code": self.error_code, "message": self.message}


class NotFoundError(AppError):
    error_code = "not_found"
    status_code = status.HTTP_404_NOT_FOUND


class ValidationError(AppError):
    error_code = "validation_error"
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class AuthenticationError(AppError):
    error_code = "authentication_error"
    status_code = status.HTTP_401_UNAUTHORIZED


class AuthorizationError(AppError):
    error_code = "authorization_error"
    status_code = status.HTTP_403_FORBIDDEN


# Maps common HTTP status codes to stable error_code strings so that errors
# raised as plain HTTPException still get a meaningful machine-readable code.
_STATUS_TO_CODE: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "authentication_error",
    status.HTTP_403_FORBIDDEN: "authorization_error",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "validation_error",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_error",
    status.HTTP_503_SERVICE_UNAVAILABLE: "service_unavailable",
}


def _error_response(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": error_code, "message": message},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Install handlers that normalise all errors into the structured body."""

    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("application_error", extra={"error_code": exc.error_code, "detail": exc.message})
        return _error_response(exc.status_code, exc.error_code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        error_code = _STATUS_TO_CODE.get(exc.status_code, "error")
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return _error_response(exc.status_code, error_code, message)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Summarise the first error for the message, keep it human-readable.
        errors = exc.errors()
        if errors:
            first = errors[0]
            loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
            detail = first.get("msg", "Invalid request")
            message = f"{loc}: {detail}" if loc else detail
        else:
            message = "Invalid request"
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "validation_error", message
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Catch-all: never leak internal details to the client (Req 28.4 - the
        # platform keeps operating; the logger records the full context).
        logger.exception("unhandled_exception", extra={"detail": str(exc)})
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "An unexpected error occurred.",
        )
