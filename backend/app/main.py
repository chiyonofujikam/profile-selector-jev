import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from backend.app.api.routes import router
from backend.app.core.config import get_settings
from backend.app.db.session import engine
from backend.app.services.decisions import ProviderError
from backend.app.schemas import HealthResponse

settings = get_settings()
app = FastAPI(title="Jev Smart Filter Selector", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[value.strip() for value in settings.allowed_origins.split(",") if value.strip()],
                   allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-Request-ID"])
app.include_router(router)
logger = logging.getLogger("jev.api")


@app.middleware("http")
async def request_id(request: Request, call_next):
    candidate = request.headers.get("X-Request-ID", "")
    request.state.request_id = candidate if len(candidate) <= 160 and candidate.isascii() and candidate.isprintable() and candidate else str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def error(request, code, message, status_code, details=None):
    payload = {"error": {"code": code, "message": message, "request_id": getattr(request.state, "request_id", None)}}
    if details is not None:
        payload["error"]["details"] = details
    return JSONResponse(payload, status_code=status_code)


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return error(request, "request_error", str(exc.detail), exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Do not reflect submitted state or secrets into error responses/logs.
    details = [{"location": list(item["loc"]), "message": item["msg"], "type": item["type"]} for item in exc.errors()]
    return error(request, "validation_error", "Please check the submitted values", 422, details)


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    logger.warning("Database unavailable request_id=%s exception=%s", request.state.request_id, type(exc).__name__)
    return error(request, "database_unavailable", "PostgreSQL is unavailable or migrations have not been applied. Start the database and run migrations, then retry.", 503)


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return error(request, "invalid_selection", str(exc), 422)


@app.exception_handler(ProviderError)
async def provider_error(request, exc):
    return error(request, exc.code, exc.message, exc.status_code)


@app.get("/health", response_model=HealthResponse)
def health():
    database_ready = False
    schema_ready = False
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            database_ready = True
            has_schema = connection.scalar(text("SELECT to_regclass('public.alembic_version') IS NOT NULL"))
            schema_ready = bool(has_schema and connection.scalar(text("SELECT version_num FROM alembic_version")) == "5be32c366157")
    except SQLAlchemyError:
        pass
    return {"status": "ok" if database_ready and schema_ready and settings.provider_ready else "degraded",
            "database": {"ready": database_ready and schema_ready, "reachable": database_ready, "migrated": schema_ready},
            "provider": {"name": settings.decision_provider, "ready": settings.provider_ready,
                         "live_verified": False if settings.decision_provider == "jev" else None}}


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    logger.error("Unhandled API error request_id=%s exception=%s", getattr(request.state, "request_id", None), type(exc).__name__)
    return error(request, "internal_error", "The request could not be completed. Please retry.", 500)
