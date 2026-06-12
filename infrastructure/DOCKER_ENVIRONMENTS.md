# Docker Compose Environment Overrides

This directory contains environment-specific Docker Compose override files that extend the base `docker-compose.yml` configuration.

## Available Environments

### 🔧 Development (`docker-compose.dev.yml`)
Optimized for local development with hot-reload and debugging capabilities.

**Features:**
- ✅ Hot-reload enabled for backend and frontend
- ✅ Debug logging (LOG_LEVEL=DEBUG)
- ✅ Reduced resource limits for local machines
- ✅ Volume mounts for source code
- ✅ Development-optimized commands

**Usage:**
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

**Key Configurations:**
- Backend: `../backend:/app` (hot-reload)
- Frontend: `../frontend/src:/app/src` (hot-reload)
- Celery: 2 workers (vs 4 in prod)
- Logs: DEBUG level

---

### 🚀 Production (`docker-compose.prod.yml`)
Optimized for production deployment with high availability and performance.

**Features:**
- ✅ Backend: 3 replicas
- ✅ Celery workers: 4 replicas
- ✅ Resource limits: CPU 2, Memory 4G for backend
- ✅ Restart policy: always
- ✅ No code volume mounts (baked into images)
- ✅ Enhanced health checks
- ✅ Rolling update strategy

**Usage:**
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

**Key Configurations:**
- Backend: 3 replicas, 2 CPU, 4G RAM
- Celery: 4 replicas, 8 workers each
- Frontend: 2 replicas
- Nginx: 2 replicas
- All services: restart=always

---

### 🧪 Test (`docker-compose.test.yml`)
Optimized for CI/CD testing with isolation and minimal resources.

**Features:**
- ✅ Isolated test database
- ✅ Minimal resource allocation
- ✅ Test-specific environment variables
- ✅ Separate volumes for clean state
- ✅ Fast startup and teardown

**Usage:**
```bash
docker compose -f docker-compose.yml -f docker-compose.test.yml up --abort-on-container-exit
```

**Key Configurations:**
- Database: `genai_kb_test` (isolated)
- Backend: pytest with coverage
- Celery: 1 worker (minimal)
- Redis: No persistence

---

## Validation

Validate all override files before deployment:

```bash
cd infrastructure/scripts
./validate-docker-overrides.sh
```

This script checks:
- ✅ YAML syntax validity
- ✅ Docker Compose merge compatibility
- ✅ Configuration requirements per environment
- ✅ Resource limits and replica counts
- ✅ Volume mount configurations

---

## Environment-Specific Commands

### Development
```bash
# Start services
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Rebuild and start
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# View logs
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f backend

# Stop services
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

### Production
```bash
# Start services (detached)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Scale services
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale backend=5

# Rolling restart
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart backend

# View resource usage
docker stats

# Stop services
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```

### Test
```bash
# Run tests
docker compose -f docker-compose.yml -f docker-compose.test.yml up --abort-on-container-exit

# Clean up test volumes
docker compose -f docker-compose.yml -f docker-compose.test.yml down -v

# Run specific service tests
docker compose -f docker-compose.yml -f docker-compose.test.yml run backend pytest tests/api/
```

---

## Configuration Matrix

| Feature | Development | Production | Test |
|---------|------------|------------|------|
| **Backend Replicas** | 1 | 3 | 1 |
| **Celery Replicas** | 1 | 4 | 1 |
| **Backend CPU** | 1 | 2 | 0.5 |
| **Backend Memory** | 1G | 4G | 512M |
| **Hot-reload** | ✅ Yes | ❌ No | ❌ No |
| **Log Level** | DEBUG | INFO | DEBUG |
| **Restart Policy** | unless-stopped | always | no |
| **Code Volumes** | ✅ Mounted | ❌ Baked | ✅ Mounted |
| **Database** | genai_kb | genai_kb | genai_kb_test |
| **Persistence** | ✅ Yes | ✅ Yes | ⚠️  Ephemeral |

---

## Tips

### For Developers
1. Always use the dev override for local development
2. Backend changes auto-reload when you edit Python files
3. Frontend changes auto-reload via Vite HMR
4. Use `docker compose logs -f <service>` to watch logs

### For DevOps
1. Test production configuration locally before deploying
2. Monitor resource usage with `docker stats`
3. Use `--scale` to adjust replica counts
4. Validate configs with the validation script
5. Set environment variables in `.env` file

### For CI/CD
1. Always use test override in pipelines
2. Clean volumes between test runs with `-v` flag
3. Use `--abort-on-container-exit` to stop on test completion
4. Collect coverage reports from mounted volumes

---

## Troubleshooting

**Issue:** Hot-reload not working in development
- **Solution:** Ensure volume mounts are correct and not cached

**Issue:** Out of memory in production
- **Solution:** Adjust resource limits in override file or scale down replicas

**Issue:** Test database has stale data
- **Solution:** Run `docker compose -f docker-compose.yml -f docker-compose.test.yml down -v`

**Issue:** Services fail to start
- **Solution:** Check logs and validate configuration with validation script

---

## Contributing

When modifying override files:
1. Maintain backward compatibility with base `docker-compose.yml`
2. Run validation script before committing
3. Update this documentation
4. Test all three environments
