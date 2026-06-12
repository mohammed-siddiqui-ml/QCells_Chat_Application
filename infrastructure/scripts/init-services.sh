#!/bin/bash

# ============================================================================
# GenAI KB - Service Initialization Script
# ============================================================================
# This script initializes all required services and performs health checks
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$INFRA_DIR")"

cd "$INFRA_DIR"

echo "============================================================================"
echo "GenAI Knowledge Retrieval System - Infrastructure Initialization"
echo "============================================================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Copying from .env.example..."
    cp .env.example .env
    echo "✅ Created .env file. Please review and update credentials if needed."
    echo ""
fi

# Check if backend .env exists
if [ ! -f ../backend/.env ]; then
    echo "⚠️  Backend .env file not found."
    if [ -f ../backend/.env.local ]; then
        echo "   Copying from .env.local..."
        cp ../backend/.env.local ../backend/.env
        echo "✅ Created backend .env file."
    elif [ -f ../backend/.env.example ]; then
        echo "   Copying from .env.example..."
        cp ../backend/.env.example ../backend/.env
        echo "✅ Created backend .env file."
    else
        echo "❌ No backend .env template found. Please create ../backend/.env manually."
        exit 1
    fi
    echo ""
fi

# Pull images
echo "📦 Pulling Docker images..."
docker-compose pull
echo ""

# Start infrastructure services first
echo "🚀 Starting infrastructure services (PostgreSQL, Redis, Elasticsearch, MinIO, RabbitMQ)..."
docker-compose up -d postgres redis elasticsearch minio rabbitmq
echo ""

# Wait for infrastructure services to be healthy
echo "⏳ Waiting for infrastructure services to be healthy..."
sleep 10

# Check PostgreSQL
echo -n "   Checking PostgreSQL... "
if docker-compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
    echo "✅"
else
    echo "❌ (may need more time)"
fi

# Check Redis
echo -n "   Checking Redis... "
if docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; then
    echo "✅"
else
    echo "❌ (may need more time)"
fi

# Check Elasticsearch (may take longer)
echo -n "   Checking Elasticsearch... "
sleep 20  # ES needs more time
if docker-compose exec -T elasticsearch curl -f http://localhost:9200/_cluster/health > /dev/null 2>&1; then
    echo "✅"
else
    echo "❌ (may need more time - Elasticsearch can take 60-90 seconds)"
fi

echo ""

# Start monitoring services
echo "📊 Starting monitoring services (Prometheus, Grafana)..."
docker-compose up -d prometheus grafana
echo ""

# Start application services
echo "🎯 Starting application services (Backend, Celery, Frontend, Nginx)..."
docker-compose up -d backend celery-worker celery-beat frontend nginx
echo ""

# Show status
echo "============================================================================"
echo "Service Status"
echo "============================================================================"
docker-compose ps
echo ""

# Display access URLs
echo "============================================================================"
echo "Access URLs"
echo "============================================================================"
echo "Frontend:              http://localhost:3000"
echo "Backend API:           http://localhost:8000"
echo "API Documentation:     http://localhost:8000/docs"
echo "MinIO Console:         http://localhost:9001"
echo "RabbitMQ Management:   http://localhost:15672"
echo "Prometheus:            http://localhost:9090"
echo "Grafana:               http://localhost:3001"
echo "Elasticsearch:         http://localhost:9200"
echo ""
echo "Default Credentials:"
echo "  MinIO:     minioadmin / minioadmin"
echo "  RabbitMQ:  guest / guest"
echo "  Grafana:   admin / admin"
echo ""
echo "============================================================================"
echo "✅ Initialization complete!"
echo "============================================================================"
echo ""
echo "Useful commands:"
echo "  View logs:        docker-compose logs -f [service]"
echo "  Restart service:  docker-compose restart [service]"
echo "  Stop all:         docker-compose down"
echo ""
