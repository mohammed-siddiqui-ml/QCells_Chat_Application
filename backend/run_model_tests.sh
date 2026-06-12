#!/bin/bash

# Script to run SQLAlchemy model tests for task-009
# This script provides various test execution modes

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}SQLAlchemy Model Test Runner${NC}"
echo -e "${GREEN}Task: task-009 - Database Schema Setup${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if pytest is installed
if ! python3 -c "import pytest" 2>/dev/null; then
    echo -e "${RED}Error: pytest is not installed${NC}"
    echo "Please install dependencies first:"
    echo "  pip install -r requirements-dev.txt"
    exit 1
fi

# Default to SQLite in-memory
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-sqlite+aiosqlite:///:memory:}"

echo -e "\n${YELLOW}Test Database:${NC} $TEST_DATABASE_URL"
echo -e "${YELLOW}Working Directory:${NC} $(pwd)"

# Parse command line arguments
MODE="${1:-all}"

case $MODE in
    "all")
        echo -e "\n${GREEN}Running all model tests...${NC}"
        python3 -m pytest tests/unit/models/ tests/integration/models/ \
            -v \
            --cov=app/models \
            --cov-report=term-missing \
            --cov-report=html:htmlcov \
            --tb=short \
            -ra
        ;;
    
    "unit")
        echo -e "\n${GREEN}Running unit tests only...${NC}"
        python3 -m pytest tests/unit/models/ \
            -v \
            -m "unit and database" \
            --tb=short
        ;;
    
    "integration")
        echo -e "\n${GREEN}Running integration tests...${NC}"
        python3 -m pytest tests/integration/models/ \
            -v \
            -m integration \
            --tb=short
        ;;
    
    "user")
        echo -e "\n${GREEN}Running User model tests...${NC}"
        python3 -m pytest tests/unit/models/test_user.py -v --tb=short
        ;;
    
    "chat")
        echo -e "\n${GREEN}Running Chat/Message model tests...${NC}"
        python3 -m pytest tests/unit/models/test_chat.py -v --tb=short
        ;;
    
    "source")
        echo -e "\n${GREEN}Running DataSource/SyncLog model tests...${NC}"
        python3 -m pytest tests/unit/models/test_source.py -v --tb=short
        ;;
    
    "document")
        echo -e "\n${GREEN}Running Document/DocumentChunk model tests...${NC}"
        python3 -m pytest tests/unit/models/test_document.py -v --tb=short
        ;;
    
    "relationships")
        echo -e "\n${GREEN}Running relationship tests...${NC}"
        python3 -m pytest tests/unit/models/test_relationships.py -v --tb=short
        ;;
    
    "quick")
        echo -e "\n${GREEN}Running quick test (no coverage)...${NC}"
        python3 -m pytest tests/unit/models/ \
            -v \
            --tb=line \
            -x
        ;;
    
    "verbose")
        echo -e "\n${GREEN}Running tests with verbose output...${NC}"
        python3 -m pytest tests/unit/models/ tests/integration/models/ \
            -vv \
            --tb=long \
            -ra \
            --showlocals
        ;;
    
    "postgres")
        echo -e "\n${GREEN}Running tests with PostgreSQL (requires setup)...${NC}"
        if [ -z "$TEST_DATABASE_URL" ] || [[ ! "$TEST_DATABASE_URL" == postgresql* ]]; then
            echo -e "${YELLOW}Note: TEST_DATABASE_URL not set to PostgreSQL${NC}"
            echo "Example: export TEST_DATABASE_URL='postgresql+asyncpg://postgres:postgres@localhost:5432/chatapp_test'"
        fi
        python3 -m pytest tests/unit/models/ tests/integration/models/ \
            -v \
            --cov=app/models \
            --cov-report=term-missing \
            --tb=short
        ;;
    
    "help")
        echo ""
        echo "Usage: ./run_model_tests.sh [MODE]"
        echo ""
        echo "Modes:"
        echo "  all          - Run all tests with coverage (default)"
        echo "  unit         - Run only unit tests"
        echo "  integration  - Run only integration tests"
        echo "  user         - Run User model tests only"
        echo "  chat         - Run ChatSession/Message tests only"
        echo "  source       - Run DataSource/SyncLog tests only"
        echo "  document     - Run Document/DocumentChunk tests only"
        echo "  relationships - Run relationship tests only"
        echo "  quick        - Quick run without coverage"
        echo "  verbose      - Run with detailed output"
        echo "  postgres     - Run with PostgreSQL database"
        echo "  help         - Show this help message"
        echo ""
        echo "Environment Variables:"
        echo "  TEST_DATABASE_URL - Database connection string (default: SQLite in-memory)"
        echo ""
        echo "Examples:"
        echo "  ./run_model_tests.sh all"
        echo "  ./run_model_tests.sh unit"
        echo "  TEST_DATABASE_URL='postgresql+asyncpg://...' ./run_model_tests.sh postgres"
        ;;
    
    *)
        echo -e "${RED}Unknown mode: $MODE${NC}"
        echo "Run './run_model_tests.sh help' for usage information"
        exit 1
        ;;
esac

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Test execution complete!${NC}"
echo -e "${GREEN}========================================${NC}"
