# Backend Docker Build Guide

## Quick Start

### Build the Docker Image
```bash
cd /path/to/project-code
docker build -t chat-backend ./backend
```

### Run the Container
```bash
docker run -d -p 8000:8000 --name backend-app chat-backend
```

### Check Health Status
```bash
# Wait for startup (40 seconds)
sleep 45

# Check health
curl http://localhost:8000/health

# Or use Docker inspect
docker inspect --format='{{.State.Health.Status}}' backend-app
```

### View Logs
```bash
docker logs -f backend-app
```

### Stop and Remove
```bash
docker stop backend-app
docker rm backend-app
```

---

## Multi-Stage Build Details

This Dockerfile uses a two-stage build process:

### Stage 1: Builder
- Base: `python:3.11-slim`
- Installs build tools (gcc, g++, libpq-dev)
- Installs Python dependencies with `--user` flag
- Dependencies stored in `/root/.local`

### Stage 2: Runtime
- Base: `python:3.11-slim` (fresh image)
- Installs only runtime dependencies (postgresql-client, curl)
- Copies compiled packages from builder stage
- Creates non-root user `app`
- Runs application as `app` user

---

## Image Optimization

### Size Reduction
- **Original**: ~1300 MB (with build tools)
- **Optimized**: ~600 MB (53.8% reduction)

### Techniques Used
1. Multi-stage build to exclude build tools
2. Comprehensive .dockerignore file
3. `--no-install-recommends` for apt packages
4. `--no-cache-dir` for pip installations
5. Layer caching optimization

---

## Security Features

### Non-Root User
The container runs as user `app` (not root):
```dockerfile
RUN groupadd -r app && useradd -r -g app app
USER app
```

### File Permissions
All application files owned by `app:app`:
```dockerfile
COPY --chown=app:app . .
```

### Minimal Attack Surface
- No build tools in final image
- Only necessary runtime dependencies
- Read-only application code

---

## Environment Variables

The following environment variables are set:

| Variable | Value | Purpose |
|----------|-------|---------|
| `PATH` | `/home/app/.local/bin:$PATH` | Include user Python packages |
| `PYTHONPATH` | `/app` | Module resolution |
| `PYTHONUNBUFFERED` | `1` | Real-time log output |
| `PYTHONDONTWRITEBYTECODE` | `1` | Prevent .pyc file generation |

---

## Health Check

### Configuration
- **Endpoint**: `GET /health`
- **Interval**: 30 seconds
- **Timeout**: 10 seconds
- **Start Period**: 40 seconds
- **Retries**: 3

### Manual Health Check
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "environment": "development"
}
```

---

## Docker Compose Integration

Example docker-compose.yml:
```yaml
services:
  backend:
    build: ./backend
    image: chat-backend
    container_name: backend-app
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/chatdb
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

---

## Troubleshooting

### Build Fails
1. Check Docker is running: `docker info`
2. Check disk space: `df -h`
3. Clear build cache: `docker builder prune`

### Container Won't Start
1. Check logs: `docker logs backend-app`
2. Check port availability: `lsof -i :8000`
3. Verify environment variables

### Health Check Fails
1. Check if app is running: `docker exec backend-app ps aux`
2. Test endpoint manually: `docker exec backend-app curl http://localhost:8000/health`
3. Check application logs for errors

### Permission Errors
The container runs as non-root user `app`. If you need to mount volumes:
```bash
docker run -v $(pwd)/data:/app/data:rw \
  --user $(id -u):$(id -g) \
  -p 8000:8000 chat-backend
```

---

## Development vs Production

### Development
```bash
# Mount source code for live reload
docker run -v $(pwd)/app:/app/app -p 8000:8000 chat-backend
```

### Production
```bash
# Use built image with no volumes
docker run -d --restart=unless-stopped -p 8000:8000 chat-backend
```

---

## Validation

To validate the Dockerfile implementation:
```bash
cd backend
./validate-dockerfile.sh
```

This script checks:
- ✅ Dockerfile syntax
- ✅ Build completion
- ✅ Image size
- ✅ Non-root user
- ✅ Environment variables
- ✅ Health check configuration
- ✅ Port exposure

---

## Best Practices Applied

1. ✅ Multi-stage build for smaller images
2. ✅ Non-root user for security
3. ✅ Health checks for monitoring
4. ✅ Layer caching optimization
5. ✅ Comprehensive .dockerignore
6. ✅ Proper environment configuration
7. ✅ Minimal base image (slim variant)
8. ✅ No cache directories in final image

---

## References

- [Docker Multi-Stage Builds](https://docs.docker.com/build/building/multi-stage/)
- [Docker Security Best Practices](https://docs.docker.com/develop/security-best-practices/)
- [Dockerfile Reference](https://docs.docker.com/engine/reference/builder/)
