"""
Main FastAPI application entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.utils.minio_client import minio_client

# Initialize logging
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events.
    """
    # Startup: Initialize MinIO bucket
    logger.info("Application startup: Initializing MinIO bucket...")
    bucket_initialized = minio_client.ensure_bucket_exists()
    if bucket_initialized:
        logger.info(f"MinIO bucket '{settings.MINIO_BUCKET_NAME}' is ready")
    else:
        logger.warning(f"Failed to initialize MinIO bucket '{settings.MINIO_BUCKET_NAME}'")

    yield

    # Shutdown: Cleanup if needed
    logger.info("Application shutdown")

# Create FastAPI app with lifespan manager
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="GenAI Intelligent Chat-Based Knowledge Retrieval System",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "GenAI Knowledge Retrieval System API",
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT
    }


# Import and include routers
# from app.api.routes import chat, admin, health
# app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
# app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
# app.include_router(health.router, prefix="/api/v1/health", tags=["health"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
