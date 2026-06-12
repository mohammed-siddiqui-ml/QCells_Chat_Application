#!/bin/bash

# ============================================================================
# Docker Compose Override Validation Script
# ============================================================================
# This script validates the Docker Compose override files for different
# environments (dev, prod, test) by checking YAML syntax and configuration
# merging.
#
# Usage: ./validate-docker-overrides.sh
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"

cd "$INFRA_DIR"

echo "============================================================================"
echo "Docker Compose Override Validation"
echo "============================================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to validate YAML syntax
validate_yaml() {
    local file=$1
    echo -n "Validating YAML syntax: $file... "
    
    if python3 -c "import yaml; yaml.safe_load(open('$file'))" 2>/dev/null; then
        echo -e "${GREEN}✓${NC}"
        return 0
    else
        echo -e "${RED}✗${NC}"
        return 1
    fi
}

# Function to validate docker-compose config merge
validate_compose_merge() {
    local env=$1
    local override_file=$2
    echo -n "Validating compose merge: $env... "
    
    # Check if docker compose command is available
    if command -v docker &> /dev/null; then
        if docker compose -f docker-compose.yml -f "$override_file" config > /dev/null 2>&1; then
            echo -e "${GREEN}✓${NC}"
            return 0
        else
            echo -e "${RED}✗${NC}"
            echo -e "${YELLOW}Warning: Docker compose merge validation failed${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}⊘ (Docker not available)${NC}"
        return 0
    fi
}

# Validate base docker-compose.yml
echo "=== Base Configuration ==="
validate_yaml "docker-compose.yml" || exit 1
echo ""

# Validate development override
echo "=== Development Environment ==="
validate_yaml "docker-compose.dev.yml" || exit 1
validate_compose_merge "development" "docker-compose.dev.yml"
echo ""

# Validate production override
echo "=== Production Environment ==="
validate_yaml "docker-compose.prod.yml" || exit 1
validate_compose_merge "production" "docker-compose.prod.yml"
echo ""

# Validate test override
echo "=== Test Environment ==="
validate_yaml "docker-compose.test.yml" || exit 1
validate_compose_merge "test" "docker-compose.test.yml"
echo ""

# Additional checks using Python
echo "=== Configuration Verification ==="
python3 << 'PYTHON_SCRIPT'
import yaml

def check_dev_config():
    with open('docker-compose.dev.yml', 'r') as f:
        dev = yaml.safe_load(f)
    
    # Check hot-reload volume mounts
    backend_vols = dev['services']['backend']['volumes']
    assert any('../backend:/app' in str(v) for v in backend_vols), "Backend hot-reload missing"
    
    frontend_vols = dev['services']['frontend']['volumes']
    assert any('frontend/src:/app/src' in str(v) for v in frontend_vols), "Frontend hot-reload missing"
    
    # Check debug logging
    assert dev['services']['backend']['environment']['LOG_LEVEL'] == 'DEBUG', "Debug logging not enabled"
    
    print("✓ Development config verified")

def check_prod_config():
    with open('docker-compose.prod.yml', 'r') as f:
        prod = yaml.safe_load(f)
    
    # Check replicas
    assert prod['services']['backend']['deploy']['replicas'] == 3, "Backend replicas != 3"
    assert prod['services']['celery-worker']['deploy']['replicas'] == 4, "Celery replicas != 4"
    
    # Check resource limits
    backend = prod['services']['backend']['deploy']['resources']
    assert backend['limits']['cpus'] == '2', "Backend CPU limit != 2"
    assert backend['limits']['memory'] == '4G', "Backend memory limit != 4G"
    
    # Check restart policy
    assert prod['services']['backend']['restart'] == 'always', "Restart policy != always"
    
    # Check no code volume mounts
    backend_vols = prod['services']['backend']['volumes']
    assert not any('../backend:/app' in str(v) for v in backend_vols), "Code mount should not exist in prod"
    
    print("✓ Production config verified")

def check_test_config():
    with open('docker-compose.test.yml', 'r') as f:
        test = yaml.safe_load(f)
    
    # Check isolated test database
    postgres_env = test['services']['postgres']['environment']
    assert 'test' in postgres_env['POSTGRES_DB'].lower(), "Test database not isolated"
    
    # Check minimal resources
    backend = test['services']['backend']['deploy']['resources']
    assert float(backend['limits']['cpus']) <= 0.5, "Test resources too high"
    
    # Check test volumes exist
    assert 'volumes' in test, "Test volumes not defined"
    assert 'postgres_test_data' in test['volumes'], "Test postgres volume missing"
    
    print("✓ Test config verified")

try:
    check_dev_config()
    check_prod_config()
    check_test_config()
except AssertionError as e:
    print(f"✗ Configuration check failed: {e}")
    exit(1)
PYTHON_SCRIPT

echo ""
echo "============================================================================"
echo -e "${GREEN}All validations passed!${NC}"
echo "============================================================================"
echo ""
echo "Usage examples:"
echo "  Development: docker compose -f docker-compose.yml -f docker-compose.dev.yml up"
echo "  Production:  docker compose -f docker-compose.yml -f docker-compose.prod.yml up"
echo "  Testing:     docker compose -f docker-compose.yml -f docker-compose.test.yml up"
echo ""
