"""Every refusal has one shape: `{"error": {"code": ..., "message": ...}}`.

`code` is a stable name the web app switches on. A message never repeats what the client
sent: a rejected body or token may hold anything.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

_MAX_PROBLEMS = 5
_STATUS_CODES = {404: "not_found", 405: "method_not_allowed"}


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra or {}
        self.headers = headers or {}


def unauthorized() -> ApiError:
    return ApiError(
        401,
        "unauthorized",
        "A valid identity token is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _invalid_request)
    app.add_exception_handler(HTTPException, _http_error)


def _body(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, **extra}}


async def _api_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, ApiError)
    content = _body(error.code, error.message, **error.extra)
    return JSONResponse(content, status_code=error.status, headers=error.headers)


async def _invalid_request(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)
    problems = [
        f"{'.'.join(str(part) for part in problem['loc'][1:]) or 'body'}: {problem['msg']}"
        for problem in error.errors()[:_MAX_PROBLEMS]
    ]
    return JSONResponse(_body("invalid_request", "; ".join(problems)), status_code=422)


async def _http_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, HTTPException)
    code = _STATUS_CODES.get(error.status_code, f"http_{error.status_code}")
    return JSONResponse(
        _body(code, str(error.detail)), status_code=error.status_code, headers=error.headers
    )
