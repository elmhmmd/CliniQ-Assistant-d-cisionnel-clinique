import logging

import httpx
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})


def register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        errors = [
            {"field": ".".join(str(l) for l in e["loc"][1:]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "Validation error", "details": errors},
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logger.exception("Database error")
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "Database unavailable")

    @app.exception_handler(httpx.ConnectError)
    async def ollama_error(request: Request, exc: httpx.ConnectError):
        logger.error("Ollama unreachable: %s", exc)
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "LLM service unreachable")

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):
        logger.exception("Unhandled error")
        return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error")
