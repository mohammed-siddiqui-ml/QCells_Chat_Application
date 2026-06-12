#!/bin/bash
# Dockerfile Validation Script for Multi-Stage Build
# This script validates the Dockerfile implementation for task-006

set -e

echo "=================================="
echo "Dockerfile Validation Script"
echo "=================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker is not installed or not in PATH${NC}"
    echo "Please install Docker to run this validation"
    exit 1
fi

echo -e "${GREEN}✓ Docker is available${NC}"
echo ""

# Validate Dockerfile syntax
echo "1. Validating Dockerfile syntax..."
if docker build --no-cache -t chat-backend-validation ./backend --target builder > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Builder stage syntax is valid${NC}"
else
    echo -e "${RED}✗ Builder stage has syntax errors${NC}"
    exit 1
fi

echo ""
echo "2. Building multi-stage image..."
echo "   Building full image (this may take a few minutes)..."

# Build the full image
if docker build --no-cache -t chat-backend ./backend; then
    echo -e "${GREEN}✓ Full multi-stage build completed successfully${NC}"
else
    echo -e "${RED}✗ Build failed${NC}"
    exit 1
fi

echo ""
echo "3. Analyzing image size..."

# Get image size
IMAGE_SIZE=$(docker images chat-backend --format "{{.Size}}")
echo "   Final image size: ${IMAGE_SIZE}"

# Check for non-root user
echo ""
echo "4. Verifying security configuration..."
USER_CHECK=$(docker run --rm chat-backend whoami)
if [ "$USER_CHECK" = "app" ]; then
    echo -e "${GREEN}✓ Container runs as non-root user 'app'${NC}"
else
    echo -e "${RED}✗ Container is not running as 'app' user (found: ${USER_CHECK})${NC}"
fi

# Verify environment variables
echo ""
echo "5. Verifying environment variables..."
docker run --rm chat-backend env | grep -E "PYTHONPATH|PYTHONUNBUFFERED|PYTHONDONTWRITEBYTECODE" || true

# Check health check configuration
echo ""
echo "6. Verifying HEALTHCHECK configuration..."
HEALTHCHECK=$(docker inspect chat-backend | grep -A 5 '"Healthcheck"' || echo "No healthcheck found")
if echo "$HEALTHCHECK" | grep -q "health"; then
    echo -e "${GREEN}✓ HEALTHCHECK is configured${NC}"
else
    echo -e "${YELLOW}⚠ HEALTHCHECK configuration not found${NC}"
fi

# Verify exposed port
echo ""
echo "7. Verifying exposed port..."
EXPOSED_PORT=$(docker inspect chat-backend | grep -o '"8000/tcp"' || echo "")
if [ -n "$EXPOSED_PORT" ]; then
    echo -e "${GREEN}✓ Port 8000 is exposed${NC}"
else
    echo -e "${RED}✗ Port 8000 is not exposed${NC}"
fi

echo ""
echo "=================================="
echo "Validation Complete!"
echo "=================================="
echo ""
echo "To run the container:"
echo "  docker run -d -p 8000:8000 --name backend chat-backend"
echo ""
echo "To check health:"
echo "  docker inspect --format='{{.State.Health.Status}}' backend"
echo ""
echo "To clean up:"
echo "  docker rm -f backend"
echo "  docker rmi chat-backend"
