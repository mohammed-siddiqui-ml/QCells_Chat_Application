#!/bin/bash

# ============================================================================
# Docker Compose Configuration Validation Script
# ============================================================================
# Validates the docker-compose.yml configuration
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"

cd "$INFRA_DIR"

echo "============================================================================"
echo "Docker Compose Configuration Validation"
echo "============================================================================"
echo ""

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    if ! command -v docker &> /dev/null; then
        echo "❌ Docker is not installed"
        exit 1
    fi
    # Try docker compose (v2 syntax)
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
        echo "✅ Docker Compose V2 detected"
    else
        echo "❌ Docker Compose is not available"
        exit 1
    fi
else
    COMPOSE_CMD="docker-compose"
    echo "✅ Docker Compose V1 detected"
fi
echo ""

# Validate docker-compose.yml syntax
echo "📝 Validating docker-compose.yml syntax..."
if $COMPOSE_CMD config > /dev/null 2>&1; then
    echo "✅ docker-compose.yml syntax is valid"
else
    echo "❌ docker-compose.yml has syntax errors:"
    $COMPOSE_CMD config
    exit 1
fi
echo ""

# Count services
echo "🔍 Analyzing configuration..."
SERVICE_COUNT=$($COMPOSE_CMD config --services | wc -l)
echo "   Services defined: $SERVICE_COUNT"

# List services
echo "   Service list:"
$COMPOSE_CMD config --services | while read service; do
    echo "      - $service"
done
echo ""

# Count volumes
VOLUME_COUNT=$($COMPOSE_CMD config --volumes | wc -l)
echo "   Volumes defined: $VOLUME_COUNT"
echo ""

# Check required services
echo "🎯 Checking required services..."
REQUIRED_SERVICES=("postgres" "redis" "elasticsearch" "minio" "rabbitmq" "prometheus" "grafana" "backend" "celery-worker" "frontend" "nginx")
ALL_SERVICES_PRESENT=true

for service in "${REQUIRED_SERVICES[@]}"; do
    if $COMPOSE_CMD config --services | grep -q "^${service}$"; then
        echo "   ✅ $service"
    else
        echo "   ❌ $service - MISSING"
        ALL_SERVICES_PRESENT=false
    fi
done
echo ""

# Check key requirements
echo "🔍 Verifying acceptance criteria..."

# Check PostgreSQL image
if grep -q "pgvector/pgvector:pg15" docker-compose.yml; then
    echo "   ✅ PostgreSQL uses pgvector/pgvector:pg15 image"
else
    echo "   ❌ PostgreSQL image requirement not met"
fi

# Check Elasticsearch configuration
if grep -q "discovery.type=single-node" docker-compose.yml; then
    echo "   ✅ Elasticsearch has discovery.type=single-node"
else
    echo "   ❌ Elasticsearch discovery.type not configured"
fi

if grep -q "ES_JAVA_OPTS=-Xms2g -Xmx2g" docker-compose.yml; then
    echo "   ✅ Elasticsearch has ES_JAVA_OPTS=-Xms2g -Xmx2g"
else
    echo "   ❌ Elasticsearch Java options not configured"
fi

# Check MinIO console port
if grep -q "9001:9001" docker-compose.yml; then
    echo "   ✅ MinIO console accessible on port 9001"
else
    echo "   ❌ MinIO console port not configured"
fi

# Check RabbitMQ management port
if grep -q "15672:15672" docker-compose.yml; then
    echo "   ✅ RabbitMQ management interface on port 15672"
else
    echo "   ❌ RabbitMQ management port not configured"
fi

# Check health checks
HEALTHCHECK_COUNT=$(grep -c "healthcheck:" docker-compose.yml || true)
echo "   ℹ️  Health checks configured: $HEALTHCHECK_COUNT services"

echo ""

# Final summary
echo "============================================================================"
if [ "$ALL_SERVICES_PRESENT" = true ] && [ "$SERVICE_COUNT" -ge 9 ]; then
    echo "✅ Configuration validation PASSED"
    echo ""
    echo "Summary:"
    echo "  - $SERVICE_COUNT services defined (requirement: 9+)"
    echo "  - $VOLUME_COUNT persistent volumes"
    echo "  - $HEALTHCHECK_COUNT health checks"
    echo "  - All required services present"
else
    echo "❌ Configuration validation FAILED"
    echo ""
    echo "Issues found:"
    if [ "$SERVICE_COUNT" -lt 9 ]; then
        echo "  - Insufficient services: $SERVICE_COUNT (required: 9+)"
    fi
    if [ "$ALL_SERVICES_PRESENT" = false ]; then
        echo "  - Missing required services"
    fi
fi
echo "============================================================================"
