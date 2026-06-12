# Infrastructure Setup Guide

This directory contains the Docker Compose configuration and related infrastructure files for the GenAI Knowledge Retrieval System.

## Overview

The infrastructure consists of 11 services:

### Core Services
- **PostgreSQL 15.5** with pgvector extension - Primary database with vector search capabilities
- **Redis 7.2** - Caching and message broker for Celery
- **Elasticsearch 8.11** - Full-text search engine
- **MinIO** - S3-compatible object storage
- **RabbitMQ 3.12** - Message queue with management plugin

### Monitoring Services
- **Prometheus 2.48** - Metrics collection and storage
- **Grafana 10.2** - Monitoring dashboards and visualization

### Application Services
- **Backend API** - FastAPI application
- **Celery Worker** - Background task processing
- **Celery Beat** - Task scheduler
- **Frontend** - React web application
- **Nginx** - Reverse proxy and load balancer

## Quick Start

### Prerequisites
- Docker 20.10 or higher
- Docker Compose 2.0 or higher
- At least 8GB RAM available for Docker
- At least 20GB disk space

### Initial Setup

1. Copy the environment file:
   ```bash
   cd infrastructure
   cp .env.example .env
   ```

2. Update credentials in `.env` (especially for production):
   - PostgreSQL credentials
   - MinIO credentials
   - RabbitMQ credentials
   - Grafana admin password

3. Start all services:
   ```bash
   docker-compose up -d
   ```

4. Check service health:
   ```bash
   docker-compose ps
   ```

### Accessing Services

| Service | URL | Credentials |
|---------|-----|-------------|
| Frontend | http://localhost:3000 | N/A |
| Backend API | http://localhost:8000 | N/A |
| API Docs | http://localhost:8000/docs | N/A |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| RabbitMQ Management | http://localhost:15672 | guest / guest |
| Prometheus | http://localhost:9090 | N/A |
| Grafana | http://localhost:3001 | admin / admin |
| Elasticsearch | http://localhost:9200 | N/A |

## Service Details

### PostgreSQL with pgvector
- **Image**: pgvector/pgvector:pg15
- **Port**: 5432
- **Volume**: postgres_data
- **Health Check**: pg_isready every 10s
- **Resources**: 2 CPU / 2GB RAM (max)

### Redis
- **Image**: redis:7.2-alpine
- **Port**: 6379
- **Volume**: redis_data
- **Health Check**: redis-cli ping every 10s
- **Resources**: 1 CPU / 1GB RAM (max)
- **Configuration**: AOF persistence, 512MB max memory with LRU eviction

### Elasticsearch
- **Image**: elasticsearch:8.11.0
- **Ports**: 9200 (HTTP), 9300 (Transport)
- **Volume**: es_data
- **Health Check**: Cluster health every 30s
- **Resources**: 2 CPU / 4GB RAM (max)
- **Configuration**: Single-node, 2GB heap, security disabled

### MinIO
- **Image**: minio/minio:latest
- **Ports**: 9000 (API), 9001 (Console)
- **Volume**: minio_data
- **Health Check**: Health endpoint every 30s
- **Resources**: 1 CPU / 1GB RAM (max)

### RabbitMQ
- **Image**: rabbitmq:3.12-management-alpine
- **Ports**: 5672 (AMQP), 15672 (Management UI)
- **Volume**: rabbitmq_data
- **Health Check**: Diagnostic ping every 30s
- **Resources**: 1 CPU / 1GB RAM (max)

### Prometheus
- **Image**: prom/prometheus:v2.48.0
- **Port**: 9090
- **Volume**: prometheus_data
- **Health Check**: Health endpoint every 30s
- **Resources**: 1 CPU / 1GB RAM (max)
- **Retention**: 30 days

### Grafana
- **Image**: grafana/grafana:10.2.0
- **Port**: 3001
- **Volume**: grafana_data
- **Health Check**: Health endpoint every 30s
- **Resources**: 1 CPU / 512MB RAM (max)

## Data Persistence

All critical data is stored in named Docker volumes:

- `postgres_data` - Database data
- `redis_data` - Redis persistence
- `es_data` - Elasticsearch indices
- `minio_data` - Object storage
- `rabbitmq_data` - Message queue data
- `prometheus_data` - Metrics data
- `grafana_data` - Dashboards and settings
- `backend_logs` - Application logs
- `chroma_data` - Vector database
- `celery_logs` - Background task logs
- `nginx_logs` - Web server logs

## Management Commands

### Start services
```bash
docker-compose up -d
```

### Stop services
```bash
docker-compose down
```

### Stop and remove volumes (WARNING: deletes all data)
```bash
docker-compose down -v
```

### View logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
```

### Restart a service
```bash
docker-compose restart backend
```

### Scale workers
```bash
docker-compose up -d --scale celery-worker=3
```

### Execute commands in containers
```bash
# PostgreSQL
docker-compose exec postgres psql -U postgres -d genai_kb

# Redis
docker-compose exec redis redis-cli

# Backend shell
docker-compose exec backend bash
```

## Health Checks

All critical services have health checks configured:

- **PostgreSQL**: `pg_isready` every 10s
- **Redis**: `redis-cli ping` every 10s
- **Elasticsearch**: Cluster health API every 30s
- **MinIO**: Health endpoint every 30s
- **RabbitMQ**: Diagnostic ping every 30s
- **Backend**: Health endpoint every 30s
- **Frontend**: HTTP check every 30s
- **Nginx**: Health endpoint every 30s

## Resource Limits

Each service has defined resource limits to prevent resource exhaustion:

| Service | CPU Limit | Memory Limit | CPU Reserved | Memory Reserved |
|---------|-----------|--------------|--------------|-----------------|
| PostgreSQL | 2 | 2GB | 0.5 | 512MB |
| Redis | 1 | 1GB | 0.25 | 256MB |
| Elasticsearch | 2 | 4GB | 1 | 2GB |
| MinIO | 1 | 1GB | 0.25 | 256MB |
| RabbitMQ | 1 | 1GB | 0.25 | 256MB |
| Prometheus | 1 | 1GB | 0.25 | 256MB |
| Grafana | 1 | 512MB | 0.25 | 128MB |
| Backend | 2 | 2GB | 0.5 | 512MB |
| Celery Worker | 2 | 2GB | 0.5 | 512MB |
| Frontend | 0.5 | 256MB | 0.1 | 64MB |
| Nginx | 0.5 | 256MB | 0.1 | 64MB |

**Total**: ~15GB RAM, ~13 CPUs (limits)

## Troubleshooting

### Services won't start
```bash
# Check logs
docker-compose logs

# Check resource usage
docker stats

# Verify Docker has enough resources allocated
docker system df
```

### Database connection issues
```bash
# Verify PostgreSQL is healthy
docker-compose ps postgres

# Check logs
docker-compose logs postgres

# Test connection
docker-compose exec postgres pg_isready -U postgres
```

### Elasticsearch fails to start
```bash
# Increase vm.max_map_count (Linux)
sudo sysctl -w vm.max_map_count=262144

# Make it permanent
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
```

### Out of disk space
```bash
# Clean up unused resources
docker system prune -a

# Remove old volumes
docker volume prune
```

## Security Considerations

### Development Environment
- Default credentials are acceptable
- Services exposed on localhost only
- SSL/TLS not required

### Production Environment
- Change ALL default credentials
- Use strong passwords (16+ characters)
- Enable SSL/TLS for all services
- Restrict network access
- Use secrets management (Docker secrets, Vault)
- Enable Elasticsearch security features
- Configure proper firewall rules
- Regular security updates

## Backup and Recovery

### Database Backup
```bash
docker-compose exec postgres pg_dump -U postgres genai_kb > backup.sql
```

### Database Restore
```bash
docker-compose exec -T postgres psql -U postgres genai_kb < backup.sql
```

### Volume Backup
```bash
docker run --rm -v postgres_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/postgres_data.tar.gz /data
```

## Monitoring

### Prometheus Metrics
Access metrics at http://localhost:9090

Key metrics to monitor:
- System resources (CPU, memory, disk)
- Service health status
- Request rates and latencies
- Database connections
- Cache hit rates

### Grafana Dashboards
Access dashboards at http://localhost:3001

Pre-configured datasource connects to Prometheus automatically.

## Network Configuration

All services are connected via the `genai-network` bridge network with subnet `172.20.0.0/16`.

Services can communicate using service names (e.g., `postgres`, `redis`, `elasticsearch`).

## Support

For issues:
1. Check service logs: `docker-compose logs [service]`
2. Verify health status: `docker-compose ps`
3. Review this documentation
4. Check Docker resources
5. Consult application documentation
