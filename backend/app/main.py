"""
RAG Chatbot Application — FastAPI entry point.
"""

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.config.configuration_manager import ConfigurationManager
from app.db.connection import init_db
from app.routers import documents, chat, config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan Event Handler (Startup / Shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for configuration loading and DB setup."""
    # 1. Initialize ConfigurationManager (Requirement 12.1)
    config_dir = os.getenv("CONFIG_DIR")
    if not config_dir:
        if os.path.exists("backend/config"):
            config_dir = "backend/config"
        else:
            config_dir = "config"
    logger.info("Initializing ConfigurationManager with directory: %s", config_dir)
    config_manager = ConfigurationManager(config_dir)
    config_manager.load()
    app.state.config_manager = config_manager

    # Initialize rate limiting store in app.state
    app.state.rate_limiter_requests = {}

    # Wait for PostgreSQL, Qdrant (and optionally MinIO) services to be healthy
    from app.startup_validation import wait_for_services
    disable_minio = os.getenv("DISABLE_MINIO", "false").lower() == "true"
    await wait_for_services(timeout=60.0, interval=2.0, include_minio=not disable_minio)

    # 2. Initialize PostgreSQL schema
    logger.info("Initializing database schema...")
    try:
        await init_db()
        logger.info("Database schema initialized successfully.")
    except Exception as exc:
        logger.exception("Database schema initialization failed: %s", exc)

    yield


# ---------------------------------------------------------------------------
# FastAPI App Definition
# ---------------------------------------------------------------------------

app = FastAPI(
    title="RAG Chatbot API",
    description="Retrieval-Augmented Generation chatbot backend.",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Custom Middlewares
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforces 100 requests per 60-second window per client IP (Req 4.10, 4.11)."""

    def __init__(self, app, limit: int = 100, window: float = 60.0):
        super().__init__(app)
        self.limit = limit
        self.window = window

    async def dispatch(self, request: Request, call_next):
        # Retrieve rate limiter store from app.state
        if not hasattr(request.app.state, "rate_limiter_requests"):
            request.app.state.rate_limiter_requests = {}
        requests_store = request.app.state.rate_limiter_requests

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Clean up timestamps older than the window
        if client_ip in requests_store:
            requests_store[client_ip] = [t for t in requests_store[client_ip] if now - t < self.window]
        else:
            requests_store[client_ip] = []

        # Check limit breach
        if len(requests_store[client_ip]) >= self.limit:
            logger.warning("Rate limit exceeded for client: %s", client_ip)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "detail": "Rate limit exceeded. Maximum 100 requests per 60 seconds.",
                },
            )

        requests_store[client_ip].append(now)
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs incoming request metadata and execution duration (Requirement 12.3)."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        method = request.method
        path = request.url.path
        query = request.url.query
        client = request.client.host if request.client else "unknown"

        logger.info(
            "Incoming API request: client=%s method=%s path=%s query=%s",
            client, method, path, query,
        )

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Completed API request: method=%s path=%s status=%d duration=%.2fms",
            method, path, response.status_code, duration_ms,
        )
        return response


# Add Custom Middlewares
app.add_middleware(RateLimitMiddleware, limit=999999, window=60.0)
app.add_middleware(RequestLoggingMiddleware)

# Add CORS Middleware
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
# Allow both the configured origin and localhost dev server variants
allowed_origins = [frontend_origin, "http://localhost:3000", "http://localhost:5173", "http://localhost:7860"]
# Remove duplicates
allowed_origins = list(set(allowed_origins))
logger.info("Configuring CORS with allowed origins: %s", allowed_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global Exception Handlers (Requirement 7.10, 7.11)
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Intercepts validation failures and formats into HTTP 400 responses (Requirement 7.10)."""
    errors = exc.errors()
    if errors:
        err = errors[0]
        field = ".".join(str(loc) for loc in err.get("loc", []))
        msg = err.get("msg", "Validation failed")
        detail = f"Field '{field}': {msg}"
    else:
        detail = "Validation failed"

    logger.warning("API validation error: %s", detail)
    return JSONResponse(
        status_code=400,
        content={"error": "validation_error", "detail": detail},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Formats standard HTTP errors cleanly (Requirement 7.10)."""
    status_map = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        429: "rate_limit_exceeded",
    }
    error_code = status_map.get(exc.status_code, "http_error")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error_code, "detail": exc.detail},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch unhandled errors, log stack trace, return HTTP 500 with unique UUID (Req 7.11)."""
    error_id = str(uuid.uuid4())
    logger.exception("Unhandled server exception occurred. error_id=%s: %s", error_id, exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "detail": f"An unexpected error occurred. Support reference: {error_id}",
        },
    )


# ---------------------------------------------------------------------------
# API Routes Wiring
# ---------------------------------------------------------------------------

@app.get("/", summary="Health check", tags=["health"])
async def health_check() -> JSONResponse:
    """Returns a simple liveness response to verify that the app is running."""
    return JSONResponse(content={"status": "ok"})


@app.get("/health", summary="Detailed health check of database and storage dependencies", tags=["health"])
async def detailed_health_check() -> JSONResponse:
    """Verifies connection health to PostgreSQL, Qdrant, and MinIO (Req 8.7)."""
    from app.startup_validation import check_postgres, check_qdrant, check_minio
    
    use_local = os.getenv("USE_LOCAL_MODE", "false").lower() == "true"
    if use_local:
        postgres_ok = await check_postgres()
        status = "healthy" if postgres_ok else "unhealthy"
        details = {
            "sqlite": "healthy" if postgres_ok else "unhealthy",
            "qdrant": "local (healthy)",
            "minio": "disabled (healthy)",
        }
    else:
        postgres_ok = await check_postgres()
        qdrant_ok = check_qdrant()
        minio_ok = check_minio()

        status = "healthy" if (postgres_ok and qdrant_ok and minio_ok) else "unhealthy"
        details = {
            "postgres": "healthy" if postgres_ok else "unhealthy",
            "qdrant": "healthy" if qdrant_ok else "unhealthy",
            "minio": "healthy" if minio_ok else "unhealthy",
        }
    
    status_code = 200 if status == "healthy" else 503
    return JSONResponse(status_code=status_code, content={"status": status, "details": details})


# Include Routers
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(config.router)

# ---------------------------------------------------------------------------
# Serve React Frontend Static Files
# Must be LAST — catches all unmatched routes and serves index.html
# ---------------------------------------------------------------------------
frontend_dist = os.getenv("FRONTEND_DIST", "")
if not frontend_dist:
    # Try common relative paths
    for candidate in ["../frontend/dist", "frontend/dist", "/app/frontend_dist/dist"]:
        if os.path.isdir(candidate):
            frontend_dist = candidate
            break

if frontend_dist and os.path.isdir(frontend_dist):
    logger.info("Serving frontend static files from: %s", frontend_dist)
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
else:
    logger.info("No frontend dist found — running API-only mode")
