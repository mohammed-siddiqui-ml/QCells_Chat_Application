#!/bin/bash
#
# Database Migration Upgrade Script
# This script runs Alembic migrations to upgrade the database to the latest version
#

set -e  # Exit on error

# Change to the backend directory
cd "$(dirname "$0")"

echo "=========================================="
echo "Database Migration Upgrade"
echo "=========================================="
echo ""

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "Using virtual environment..."
    ALEMBIC_CMD="venv/bin/alembic"
    PYTHON_CMD="venv/bin/python"
elif command -v alembic &> /dev/null; then
    echo "Using system alembic..."
    ALEMBIC_CMD="alembic"
    PYTHON_CMD="python"
else
    echo "Error: Alembic not found. Please install alembic or create a virtual environment."
    exit 1
fi

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "Warning: DATABASE_URL environment variable not set."
    echo "Make sure it's configured in your .env file or environment."
    echo ""
fi

# Show current database revision
echo "Current database revision:"
$ALEMBIC_CMD current 2>/dev/null || echo "  (No revision applied yet)"
echo ""

# Show pending migrations
echo "Pending migrations:"
$ALEMBIC_CMD history --verbose 2>/dev/null || echo "  (Unable to retrieve history)"
echo ""

# Run upgrade
echo "Running database upgrade to HEAD..."
$ALEMBIC_CMD upgrade head

echo ""
echo "=========================================="
echo "Migration upgrade completed successfully!"
echo "=========================================="
echo ""

# Show new database revision
echo "New database revision:"
$ALEMBIC_CMD current
echo ""
