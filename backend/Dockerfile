# ============================================================================
# Stage 1: Builder - Install dependencies
# ============================================================================
FROM python:3.11-slim AS builder

# Set working directory
WORKDIR /app

# Install system dependencies required for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file for dependency installation
COPY requirements.txt .

# Install Python dependencies with --user flag for isolation
# This installs packages to /root/.local
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --user --no-cache-dir -r requirements.txt

# ============================================================================
# Stage 2: Runtime - Minimal production image
# ============================================================================
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install only runtime dependencies (postgresql-client for DB connectivity)
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user 'app' for security
RUN groupadd -r app && useradd -r -g app app

# Copy installed Python packages from builder stage
COPY --from=builder /root/.local /home/app/.local

# Copy application code
COPY --chown=app:app . .

# Create necessary directories with proper permissions
RUN mkdir -p logs data/chroma && \
    chown -R app:app logs data

# Set environment variables
ENV PATH=/home/app/.local/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER app

# Expose port
EXPOSE 8000

# Health check - uses curl instead of Python for lighter health checks
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
