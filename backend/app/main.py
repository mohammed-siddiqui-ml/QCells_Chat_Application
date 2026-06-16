"""
Main FastAPI application entry point
"""
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.db.session import engine, Base
from app.utils.minio_client import minio_client
from app.utils.redis_client import redis_client
from app.utils.elasticsearch_client import elasticsearch_client
from app.middleware.rate_limiter import rate_limiter

# Initialize logging
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events.
    Handles initialization of database, Redis, Elasticsearch, and MinIO.
    """
    # Startup
    logger.info("=" * 80)
    logger.info("Application startup initiated")
    logger.info("=" * 80)

    # Initialize database connection pool
    try:
        logger.info("Initializing database connection pool...")
        async with engine.begin() as conn:
            # Create tables if they don't exist
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database connection pool initialized successfully")
        logger.info("Database tables created/verified successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    # Initialize Redis client
    try:
        logger.info("Initializing Redis client...")
        await redis_client.initialize()
        # Test Redis connection
        await redis_client.health_check()
        logger.info("Redis client initialized and connection verified")
    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}")
        raise

    # Initialize Elasticsearch client
    try:
        logger.info("Initializing Elasticsearch client...")
        await elasticsearch_client.initialize()
        # Test Elasticsearch connection
        await elasticsearch_client.health_check()
        logger.info("Elasticsearch client initialized and connection verified")
    except Exception as e:
        logger.error(f"Failed to initialize Elasticsearch: {e}")
        raise

    # Initialize MinIO bucket
    try:
        logger.info("Initializing MinIO bucket...")
        bucket_initialized = minio_client.ensure_bucket_exists()
        if bucket_initialized:
            logger.info(f"MinIO bucket '{settings.MINIO_BUCKET_NAME}' is ready")
        else:
            logger.warning(f"Failed to initialize MinIO bucket '{settings.MINIO_BUCKET_NAME}'")
    except Exception as e:
        logger.warning(f"MinIO initialization error (non-critical): {e}")

    logger.info("=" * 80)
    logger.info("Application startup completed successfully")
    logger.info("=" * 80)

    yield

    # Shutdown
    logger.info("=" * 80)
    logger.info("Application shutdown initiated")
    logger.info("=" * 80)

    # Close Redis connection
    try:
        logger.info("Closing Redis connection...")
        await redis_client.close()
        logger.info("Redis connection closed")
    except Exception as e:
        logger.error(f"Error closing Redis connection: {e}")

    # Close Elasticsearch connection
    try:
        logger.info("Closing Elasticsearch connection...")
        await elasticsearch_client.close()
        logger.info("Elasticsearch connection closed")
    except Exception as e:
        logger.error(f"Error closing Elasticsearch connection: {e}")

    # Dispose database engine
    try:
        logger.info("Disposing database engine...")
        await engine.dispose()
        logger.info("Database engine disposed")
    except Exception as e:
        logger.error(f"Error disposing database engine: {e}")

    logger.info("=" * 80)
    logger.info("Application shutdown completed")
    logger.info("=" * 80)


# Create FastAPI app with lifespan manager
app = FastAPI(
    title="GenAI Chat API",
    version="1.0.0",
    description="GenAI Intelligent Chat-Based Knowledge Retrieval System - A powerful AI-driven chat application for querying and retrieving information from multiple knowledge sources including Confluence, Jira, and onboarding materials.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)


# ============================================================================
# Middleware Registration
# ============================================================================

# CORS Middleware
# Note: Task specifies ALLOWED_ORIGINS environment variable
# Use ALLOWED_ORIGINS if provided, otherwise fall back to CORS_ORIGINS
allowed_origins = settings.ALLOWED_ORIGINS if settings.ALLOWED_ORIGINS else settings.CORS_ORIGINS
logger.info(f"Configuring CORS with allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request Logging Middleware
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """
    Middleware for logging HTTP requests and responses.
    """
    # Log incoming request
    logger.info(
        f"Incoming request: {request.method} {request.url.path}",
        extra={
            "method": request.method,
            "path": request.url.path,
            "client_host": request.client.host if request.client else None,
        }
    )

    # Process request
    response = await call_next(request)

    # Log response
    logger.info(
        f"Response: {request.method} {request.url.path} - Status: {response.status_code}",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
        }
    )

    return response


# Rate Limiting Middleware
@app.middleware("http")
async def rate_limiting_middleware(request: Request, call_next):
    """
    Middleware for rate limiting requests using token bucket algorithm.
    """
    return await rate_limiter(request, call_next)


# ============================================================================
# Exception Handlers
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Global exception handler for HTTPException.
    Returns standardized error responses for HTTP exceptions.
    """
    logger.warning(
        f"HTTP exception: {exc.status_code} - {exc.detail}",
        extra={
            "status_code": exc.status_code,
            "detail": exc.detail,
            "path": request.url.path,
        }
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "type": "HTTPException",
                "status_code": exc.status_code,
                "message": exc.detail,
                "path": request.url.path,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Global exception handler for FastAPI RequestValidationError.
    Returns standardized error responses for validation failures.
    """
    logger.warning(
        f"Validation error: {exc}",
        extra={
            "errors": exc.errors(),
            "path": request.url.path,
        }
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "type": "ValidationError",
                "status_code": 422,
                "message": "Request validation failed",
                "details": exc.errors(),
                "path": request.url.path,
            }
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """
    Global exception handler for SQLAlchemy database errors.
    Returns standardized error responses for database failures.
    """
    logger.error(
        f"Database error: {exc}",
        extra={
            "error_type": type(exc).__name__,
            "path": request.url.path,
        },
        exc_info=True,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "type": "DatabaseError",
                "status_code": 500,
                "message": "A database error occurred. Please try again later.",
                "path": request.url.path,
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Global exception handler for unexpected exceptions.
    Returns standardized error responses for unhandled errors.
    """
    logger.error(
        f"Unhandled exception: {exc}",
        extra={
            "error_type": type(exc).__name__,
            "path": request.url.path,
        },
        exc_info=True,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "type": "InternalServerError",
                "status_code": 500,
                "message": "An unexpected error occurred. Please try again later.",
                "path": request.url.path,
            }
        },
    )


# ============================================================================
# Health Check Endpoints
# ============================================================================

@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, str]:
    """
    Basic health check endpoint.
    Returns OK status if the application is running.

    Returns:
        dict: Status information with "ok" status
    """
    return {"status": "ok"}


@app.get("/ready", tags=["Health"])
async def readiness_check() -> Dict[str, Any]:
    """
    Readiness check endpoint.
    Verifies that all critical services (PostgreSQL, Redis, Elasticsearch) are accessible.
    Returns 200 if all services are healthy, 503 if any service is down.

    Returns:
        dict: Detailed status of all services

    Raises:
        HTTPException: 503 if any critical service is unavailable
    """
    services_status = {
        "status": "ready",
        "services": {}
    }

    all_healthy = True

    # Check PostgreSQL
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        services_status["services"]["postgresql"] = {
            "status": "healthy",
            "message": "Connected"
        }
        logger.debug("PostgreSQL health check: healthy")
    except Exception as e:
        all_healthy = False
        services_status["services"]["postgresql"] = {
            "status": "unhealthy",
            "message": str(e)
        }
        logger.error(f"PostgreSQL health check failed: {e}")

    # Check Redis
    try:
        is_healthy = await redis_client.health_check()
        if is_healthy:
            services_status["services"]["redis"] = {
                "status": "healthy",
                "message": "Connected"
            }
            logger.debug("Redis health check: healthy")
        else:
            all_healthy = False
            services_status["services"]["redis"] = {
                "status": "unhealthy",
                "message": "Connection failed"
            }
            logger.error("Redis health check failed")
    except Exception as e:
        all_healthy = False
        services_status["services"]["redis"] = {
            "status": "unhealthy",
            "message": str(e)
        }
        logger.error(f"Redis health check failed: {e}")

    # Check Elasticsearch
    try:
        is_healthy = await elasticsearch_client.health_check()
        if is_healthy:
            services_status["services"]["elasticsearch"] = {
                "status": "healthy",
                "message": "Connected"
            }
            logger.debug("Elasticsearch health check: healthy")
        else:
            all_healthy = False
            services_status["services"]["elasticsearch"] = {
                "status": "unhealthy",
                "message": "Connection failed"
            }
            logger.error("Elasticsearch health check failed")
    except Exception as e:
        all_healthy = False
        services_status["services"]["elasticsearch"] = {
            "status": "unhealthy",
            "message": str(e)
        }
        logger.error(f"Elasticsearch health check failed: {e}")

    # Return 503 if any service is unhealthy
    if not all_healthy:
        services_status["status"] = "not_ready"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=services_status
        )

    return services_status


@app.get("/", tags=["Root"])
async def root() -> Dict[str, str]:
    """
    Root endpoint providing basic API information.

    Returns:
        dict: API information including name, version, and status
    """
    return {
        "message": "GenAI Knowledge Retrieval System API",
        "version": settings.APP_VERSION,
        "status": "running"
    }


# ============================================================================
# Router Registration
# ============================================================================

# Import and include routers
from app.api.routes import chat

app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
# app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
# app.include_router(health.router, prefix="/api/v1/health", tags=["health"])


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
