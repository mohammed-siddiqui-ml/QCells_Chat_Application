#!/bin/bash

# Validation script for frontend Dockerfile
# This script validates the Dockerfile configuration meets all acceptance criteria

echo "=== Frontend Dockerfile Validation ==="
echo ""

# Check if Dockerfile exists
if [ ! -f "Dockerfile" ]; then
    echo "❌ ERROR: Dockerfile not found"
    exit 1
fi
echo "✅ Dockerfile exists"

# Check if nginx.conf exists
if [ ! -f "nginx.conf" ]; then
    echo "❌ ERROR: nginx.conf not found"
    exit 1
fi
echo "✅ nginx.conf exists"

# Validate Dockerfile content
echo ""
echo "=== Dockerfile Configuration ==="

# Check for node:20-alpine base image
if grep -q "FROM node:20-alpine" Dockerfile; then
    echo "✅ Using node:20-alpine for build stage"
else
    echo "❌ ERROR: Not using node:20-alpine"
    exit 1
fi

# Check for nginx:1.25-alpine
if grep -q "FROM nginx:1.25-alpine" Dockerfile; then
    echo "✅ Using nginx:1.25-alpine for production stage"
else
    echo "❌ ERROR: Not using nginx:1.25-alpine"
    exit 1
fi

# Check for npm ci (reproducible builds)
if grep -q "npm ci" Dockerfile; then
    echo "✅ Using npm ci for reproducible builds"
else
    echo "❌ ERROR: Not using npm ci"
    exit 1
fi

# Check for npm run build
if grep -q "npm run build" Dockerfile; then
    echo "✅ Using npm run build"
else
    echo "❌ ERROR: Not using npm run build"
    exit 1
fi

# Check multi-stage build
if grep -q "COPY --from=builder" Dockerfile; then
    echo "✅ Multi-stage build configured"
else
    echo "❌ ERROR: Multi-stage build not configured"
    exit 1
fi

echo ""
echo "=== nginx.conf Configuration ==="

# Check SPA routing (try_files with fallback to index.html)
if grep -q "try_files.*index.html" nginx.conf; then
    echo "✅ SPA routing configured (try_files with fallback to index.html)"
else
    echo "❌ ERROR: SPA routing not configured"
    exit 1
fi

# Check GZIP compression
if grep -q "gzip on" nginx.conf; then
    echo "✅ GZIP compression enabled"
else
    echo "❌ ERROR: GZIP compression not enabled"
    exit 1
fi

# Check GZIP types for text assets
if grep -q "gzip_types.*text/html.*text/css.*application/javascript" nginx.conf; then
    echo "✅ GZIP configured for text assets (text/html, text/css, application/javascript)"
else
    echo "❌ ERROR: GZIP types not properly configured"
    exit 1
fi

# Check X-Content-Type-Options header
if grep -q 'X-Content-Type-Options.*"nosniff"' nginx.conf; then
    echo "✅ X-Content-Type-Options: nosniff header configured"
else
    echo "❌ ERROR: X-Content-Type-Options header not configured"
    exit 1
fi

# Check X-Frame-Options header
if grep -q 'X-Frame-Options.*"DENY"' nginx.conf; then
    echo "✅ X-Frame-Options: DENY header configured"
else
    echo "❌ ERROR: X-Frame-Options header not set to DENY"
    exit 1
fi

# Check Content-Security-Policy header
if grep -q "Content-Security-Policy" nginx.conf; then
    echo "✅ Content-Security-Policy (CSP) header configured"
else
    echo "❌ ERROR: CSP header not configured"
    exit 1
fi

# Check API proxy configuration
if grep -q "location /api" nginx.conf && grep -q "proxy_pass http://backend:8000" nginx.conf; then
    echo "✅ API proxy configured (/api/* -> http://backend:8000)"
else
    echo "❌ ERROR: API proxy not configured"
    exit 1
fi

echo ""
echo "=== All validations passed! ==="
echo ""
echo "To build the image, run:"
echo "  docker build -t chat-frontend ./frontend"
echo ""
echo "Expected final image size: <50MB (nginx:1.25-alpine ~40MB + static files)"
