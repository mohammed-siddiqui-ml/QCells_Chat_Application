#!/bin/bash
#
# Database Migration Downgrade Script
# This script runs Alembic migrations to downgrade the database by one revision
#

set -e  # Exit on error

# Change to the backend directory
cd "$(dirname "$0")"

echo "=========================================="
echo "Database Migration Downgrade"
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

# Confirm downgrade
read -p "Are you sure you want to downgrade by one revision? (y/N): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Downgrade cancelled."
    exit 0
fi

# Run downgrade
echo "Running database downgrade by 1 revision..."
$ALEMBIC_CMD downgrade -1

echo ""
echo "=========================================="
echo "Migration downgrade completed successfully!"
echo "=========================================="
echo ""

# Show new database revision
echo "New database revision:"
$ALEMBIC_CMD current
echo ""
