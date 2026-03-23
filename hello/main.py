from fastapi import FastAPI, Request
import time as _time
import os
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
import uuid
from hello.services.api_errors import json_error, get_request_id
from hello.services.logging_context import (
    set_user_email,
    clear_user_email,
    set_request_id,
    clear_request_id,
    extract_email_from_request,
)
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from hello.routers import (
    health,
    templates,
    sections,
    prompts,
    reports,
    schedules,
    users,
    agents,
    sidebar_options,
)
from hello.routers.auth import router as auth_router
from hello.services.multi_agent_workflow_service import workflow_service
from hello.ml.utils.snowflake_connector import SnowflakeConnector
from hello.services.logging_helper import setup_logging
from hello.ml.logger import GLOBAL_LOGGER as logger
from sqlalchemy import text
from hello.services.database import engine
from hello.services.config import settings
from fastapi.openapi.utils import get_openapi
from hello.services.miq_service import close_miq_client

def is_cbre_env() -> bool:
    return (settings.TESTING_ENV or "").upper() == "CBRE"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.

    Handles startup and shutdown events for the application,
    including initialization of the multi-agent workflow service.
    """
    # Startup
    # Ensure logging is configured for console output (no-op if already set)
    try:
        setup_logging()
    except Exception:
        pass

    logger.info("Starting CBRE Research Reports API...")

    if is_cbre_env():
        try:
            logger.info("Initializing Snowflake connector...₹")
            success = SnowflakeConnector().connect()
            if success:
                logger.info("✅ Snowflake connector initialized successfully")
            else:
                logger.error("Failed to initialize Snowflake connector")
                # Continue startup even if snowflake connector fails to allow health checks
        except Exception as e:
            logger.error(f"Error during Snowflake connector initialization: {str(e)}")
            # Continue startup even if snowflake connector fails to allow health checks

    try:
        # Initialize the multi-agent workflow service
        logger.info("Initializing multi-agent workflow service...")
        success = await workflow_service.initialize()

        if success:
            logger.info("Multi-agent workflow service initialized successfully")
        else:
            logger.error("Failed to initialize multi-agent workflow service")
            # Continue startup even if workflow fails to allow health checks
    except Exception as e:
        logger.error(f"Error during workflow service initialization: {str(e)}")
        # Continue startup even if workflow fails to allow health checks

    # Opportunistic DDL: ensure new columns exist for backward-compatible deploys
    try:
        async with engine.begin() as conn:
            # Add 'version' column to prompts if missing (Postgres supports IF EXISTS/IF NOT EXISTS)
            await conn.execute(
                text(
                    "ALTER TABLE IF EXISTS prompts "
                    "ADD COLUMN IF NOT EXISTS version integer DEFAULT 1"
                )
            )
    except Exception as e:
        logger.warning(f"Failed to ensure schema compatibility: {e}")

    logger.info("CBRE Research Reports API startup completed")

    yield

    if is_cbre_env():
        logger.info("Disconnecting Snowflake connector...")
        SnowflakeConnector().disconnect()
        logger.info("✅ Snowflake connector disconnected")

    # Close MIQ HTTP client
    try:
        logger.info("Closing MIQ HTTP client...")
        await close_miq_client()
        logger.info("✅ MIQ HTTP client closed")
    except Exception as e:
        logger.error(f"Error closing MIQ client: {e}")

    # Shutdown
    logger.info("Shutting down CBRE Research Reports API...")
    logger.info("CBRE Research Reports API shutdown completed")


app = FastAPI(
    title="CBRE Research Reports API",
    version="1.0.0",
    openapi_version="3.0.3",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


# OAuth login flow stores state in the Starlette session middleware.
app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET)

# Database schema is managed via Alembic migrations.

app.add_middleware(
    CORSMiddleware,
    # Explicitly list frontend origins; avoid '*' with credentials
    allow_origins=[
        "http://localhost:5241",
        "http://localhost:5421",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5241",
        "http://127.0.0.1:5421",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    # Also allow any localhost/127.0.0.1 with arbitrary port
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(health.router)
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(sections.router, prefix="/api/sections", tags=["sections"])
app.include_router(prompts.router, prefix="/api/prompts", tags=["prompts"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(schedules.router, prefix="/api/schedules", tags=["schedules"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(
    sidebar_options.router,
    prefix="/api/snowflake-sidebar",
    tags=["snowflake-sidebar"],
)
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])


SWAGGER_UI_ROUTE = "/docs"
SWAGGER_OAUTH2_REDIRECT_ROUTE = "/docs/oauth2-redirect"


@app.get(SWAGGER_UI_ROUTE, include_in_schema=False)
async def custom_swagger_ui() -> JSONResponse:
    response = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        oauth2_redirect_url=SWAGGER_OAUTH2_REDIRECT_ROUTE,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get(SWAGGER_OAUTH2_REDIRECT_ROUTE, include_in_schema=False)
async def swagger_ui_redirect() -> JSONResponse:
    response = get_swagger_ui_oauth2_redirect_html()
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# Custom OpenAPI schema generation with defensive fallback --------------------
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    try:
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("Failed to generate OpenAPI schema", exc_info=exc)
        openapi_schema = {
            "openapi": app.openapi_version or "3.0.3",
            "info": {
                "title": app.title,
                "version": app.version,
                "description": app.description or "",
            },
            "paths": {},
        }

    if "openapi" not in openapi_schema:
        openapi_schema["openapi"] = app.openapi_version or "3.0.3"

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi_schema = None
app.openapi = custom_openapi


# Request ID middleware and exception handlers ---------------------------------


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    # Attach a request id for correlation
    request_id = None
    user_email = None
    try:
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        set_request_id(request_id)
    except Exception:
        pass
    
    # Extract user email from JWT token for logging context
    try:
        user_email = extract_email_from_request(request)
        set_user_email(user_email)
    except Exception:
        set_user_email(None)
    
    # Access log timing
    _start = _time.time()
    try:
        response = await call_next(request)
    finally:
        # Always clear the logging context after request processing
        clear_user_email()
        clear_request_id()
    
    _duration_ms = int((_time.time() - _start) * 1000)
    try:
        response.headers["X-Request-ID"] = get_request_id(request)
    except Exception:
        pass
    try:
        logger.info(
            "access: %s %s status=%s dur_ms=%s rid=%s user=%s",
            request.method,
            request.url.path,
            getattr(response, "status_code", None),
            _duration_ms,
            request_id or "-",
            user_email or "-",
        )
    except Exception:
        pass
    return response


@app.exception_handler(RequestValidationError)
async def on_request_validation_error(request: Request, exc: RequestValidationError):
    details = [
        {"loc": err.get("loc"), "msg": err.get("msg"), "type": err.get("type")}
        for err in exc.errors()
    ]
    return json_error(
        request,
        status=422,
        message="Request validation failed",
        code="request_validation_error",
        details=details,
    )


@app.exception_handler(ValidationError)
async def on_pydantic_validation_error(request: Request, exc: ValidationError):
    return json_error(
        request,
        status=422,
        message="Validation failed",
        code="validation_error",
        details=exc.errors(),
    )


@app.exception_handler(SQLAlchemyError)
async def on_sqlalchemy_error(request: Request, exc: SQLAlchemyError):
    logger.exception("Database error", exc_info=exc)
    return json_error(
        request,
        status=500,
        message="Database error",
        code="database_error",
    )


@app.exception_handler(Exception)
async def on_unhandled_exception(request: Request, exc: Exception):
    logger.exception("Unhandled error", exc_info=exc)
    return json_error(
        request,
        status=500,
        message="Internal server error",
        code="internal_error",
    )
