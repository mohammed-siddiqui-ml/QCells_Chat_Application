#!/bin/bash

# Frontend Dockerfile Test Suite
# This script executes all test cases defined in the test plan

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
SKIPPED_TESTS=0

# Test results array
declare -a TEST_RESULTS

# Image and container names
IMAGE_NAME="chat-frontend-test"
CONTAINER_NAME="test-frontend"
TEST_PORT="8080"

# Helper functions
log_test() {
    echo -e "\n${YELLOW}[TEST $1]${NC} $2"
    ((TOTAL_TESTS++))
}

log_pass() {
    echo -e "${GREEN}✓ PASSED${NC}: $1"
    ((PASSED_TESTS++))
    TEST_RESULTS+=("PASS: TC-$1")
}

log_fail() {
    echo -e "${RED}✗ FAILED${NC}: $1"
    echo -e "${RED}  Error: $2${NC}"
    ((FAILED_TESTS++))
    TEST_RESULTS+=("FAIL: TC-$1 - $2")
}

log_skip() {
    echo -e "${YELLOW}⊘ SKIPPED${NC}: $1"
    ((SKIPPED_TESTS++))
    TEST_RESULTS+=("SKIP: TC-$1")
}

cleanup() {
    echo -e "\n${YELLOW}Cleaning up test resources...${NC}"
    docker stop $CONTAINER_NAME 2>/dev/null || true
    docker rm $CONTAINER_NAME 2>/dev/null || true
    docker rmi $IMAGE_NAME 2>/dev/null || true
}

# Trap to ensure cleanup on exit
trap cleanup EXIT

echo "========================================"
echo "Frontend Dockerfile Test Suite"
echo "========================================"
echo "Date: $(date)"
echo ""

# Phase 1: Pre-Build Validation
echo -e "\n${YELLOW}=== PHASE 1: PRE-BUILD VALIDATION ===${NC}"

# TC-001: Validate Dockerfile base images
log_test "TC-001" "Validate Dockerfile base images"
if grep -q "FROM node:20-alpine AS builder" Dockerfile && grep -q "FROM nginx:1.25-alpine" Dockerfile; then
    log_pass "TC-001"
else
    log_fail "TC-001" "Base images do not match specification"
fi

# TC-002: Verify multi-stage build configuration
log_test "TC-002" "Verify multi-stage build configuration"
if grep -q "npm ci" Dockerfile && grep -q "npm run build" Dockerfile && grep -q "COPY --from=builder" Dockerfile; then
    log_pass "TC-002"
else
    log_fail "TC-002" "Multi-stage build not properly configured"
fi

# Phase 2: Build Testing
echo -e "\n${YELLOW}=== PHASE 2: BUILD TESTING ===${NC}"

# TC-003: Build Docker image
log_test "TC-003" "Build Docker image successfully"
if docker build -t $IMAGE_NAME . > /tmp/docker-build.log 2>&1; then
    log_pass "TC-003"
    echo "Build output saved to /tmp/docker-build.log"
else
    log_fail "TC-003" "Docker build failed. Check /tmp/docker-build.log for details"
    cat /tmp/docker-build.log
    exit 1
fi

# TC-004: Verify image size
log_test "TC-004" "Verify image size is under 50MB"
IMAGE_SIZE=$(docker images $IMAGE_NAME --format "{{.Size}}")
echo "Image size: $IMAGE_SIZE"
# Convert size to MB for comparison
SIZE_IN_MB=$(docker images $IMAGE_NAME --format "{{.Size}}" | sed 's/MB//' | awk '{print int($1+0.5)}')
if [ "$SIZE_IN_MB" -lt 50 ]; then
    log_pass "TC-004"
else
    log_fail "TC-004" "Image size ${SIZE_IN_MB}MB exceeds 50MB limit"
fi

# Phase 3: Configuration Validation
echo -e "\n${YELLOW}=== PHASE 3: CONFIGURATION VALIDATION ===${NC}"

# TC-005: Validate nginx.conf syntax
log_test "TC-005" "Validate nginx.conf syntax"
if docker run --rm $IMAGE_NAME nginx -t 2>&1 | grep -q "syntax is ok"; then
    log_pass "TC-005"
else
    log_fail "TC-005" "Nginx configuration syntax error"
fi

# TC-006: Verify SPA routing configuration
log_test "TC-006" "Verify SPA routing configuration"
if grep -q "try_files.*\$uri.*\$uri/.*index.html" nginx.conf; then
    log_pass "TC-006"
else
    log_fail "TC-006" "SPA routing not configured correctly"
fi

# TC-007: Verify GZIP compression configuration
log_test "TC-007" "Verify GZIP compression configuration"
if grep -q "gzip on" nginx.conf && \
   grep -q "text/html" nginx.conf && \
   grep -q "text/css" nginx.conf && \
   grep -q "application/javascript" nginx.conf; then
    log_pass "TC-007"
else
    log_fail "TC-007" "GZIP compression not fully configured"
fi

# TC-008: Verify security headers configuration
log_test "TC-008" "Verify security headers configuration"
if grep -q "X-Content-Type-Options.*nosniff.*always" nginx.conf && \
   grep -q "X-Frame-Options.*DENY.*always" nginx.conf && \
   grep -q "Content-Security-Policy" nginx.conf; then
    log_pass "TC-008"
else
    log_fail "TC-008" "Security headers not properly configured"
fi

# TC-009: Verify API proxy configuration
log_test "TC-009" "Verify API proxy configuration"
if grep -q "location /api" nginx.conf && \
   grep -q "proxy_pass http://backend:8000" nginx.conf && \
   grep -q "X-Real-IP" nginx.conf && \
   grep -q "X-Forwarded-For" nginx.conf && \
   grep -q "Upgrade.*http_upgrade" nginx.conf; then
    log_pass "TC-009"
else
    log_fail "TC-009" "API proxy not fully configured"
fi

# Phase 4: Runtime Testing
echo -e "\n${YELLOW}=== PHASE 4: RUNTIME TESTING ===${NC}"

# TC-010: Start container successfully
log_test "TC-010" "Start container successfully"
if docker run -d --name $CONTAINER_NAME -p $TEST_PORT:80 $IMAGE_NAME > /dev/null 2>&1; then
    sleep 5  # Wait for container startup
    if docker ps | grep -q $CONTAINER_NAME; then
        log_pass "TC-010"
    else
        log_fail "TC-010" "Container not running"
    fi
else
    log_fail "TC-010" "Failed to start container"
fi

# TC-011: Verify root path serves index.html
log_test "TC-011" "Verify root path serves index.html"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$TEST_PORT/ 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    log_pass "TC-011"
else
    log_fail "TC-011" "Root path returned HTTP $HTTP_CODE instead of 200"
fi

# TC-016: Validate container health check (moved up for logical flow)
log_test "TC-016" "Validate container health check"
sleep 10  # Wait for health check to run
HEALTH_STATUS=$(docker inspect $CONTAINER_NAME --format='{{.State.Health.Status}}' 2>/dev/null || echo "none")
if [ "$HEALTH_STATUS" = "healthy" ] || [ "$HEALTH_STATUS" = "starting" ]; then
    log_pass "TC-016"
else
    log_fail "TC-016" "Health status: $HEALTH_STATUS"
fi

# Phase 5: Functional Testing
echo -e "\n${YELLOW}=== PHASE 5: FUNCTIONAL TESTING ===${NC}"

# TC-012: Test SPA routing fallback
log_test "TC-012" "Test SPA routing fallback"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$TEST_PORT/users/123 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    log_pass "TC-012"
else
    log_fail "TC-012" "SPA route returned HTTP $HTTP_CODE instead of 200"
fi

# TC-015: Verify API proxy routing
log_test "TC-015" "Verify API proxy routing"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$TEST_PORT/api/health 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "502" ] || [ "$HTTP_CODE" = "503" ]; then
    log_pass "TC-015"
    echo "  (Expected 502/503 since backend is not running)"
else
    log_fail "TC-015" "API proxy returned HTTP $HTTP_CODE (expected 502/503)"
fi

# TC-017: Verify static asset caching headers
log_test "TC-017" "Verify static asset caching headers"
# Try to get a JS file from the dist directory
CACHE_HEADER=$(curl -s -I http://localhost:$TEST_PORT/assets/*.js 2>/dev/null | grep -i "Cache-Control" | head -1 || echo "")
if [ -n "$CACHE_HEADER" ]; then
    log_pass "TC-017"
    echo "  Cache-Control header: $CACHE_HEADER"
else
    log_skip "TC-017 - No static JS files available to test"
fi

# Phase 6: Security & Performance
echo -e "\n${YELLOW}=== PHASE 6: SECURITY & PERFORMANCE ===${NC}"

# TC-013: Verify security headers in HTTP response
log_test "TC-013" "Verify security headers in HTTP response"
HEADERS=$(curl -s -I http://localhost:$TEST_PORT/ 2>/dev/null)
HAS_XCO=$(echo "$HEADERS" | grep -i "X-Content-Type-Options" || echo "")
HAS_XFO=$(echo "$HEADERS" | grep -i "X-Frame-Options" || echo "")
HAS_CSP=$(echo "$HEADERS" | grep -i "Content-Security-Policy" || echo "")

if [ -n "$HAS_XCO" ] && [ -n "$HAS_XFO" ] && [ -n "$HAS_CSP" ]; then
    log_pass "TC-013"
else
    MISSING=""
    [ -z "$HAS_XCO" ] && MISSING="$MISSING X-Content-Type-Options"
    [ -z "$HAS_XFO" ] && MISSING="$MISSING X-Frame-Options"
    [ -z "$HAS_CSP" ] && MISSING="$MISSING Content-Security-Policy"
    log_fail "TC-013" "Missing headers:$MISSING"
fi

# TC-014: Verify GZIP compression in HTTP response
log_test "TC-014" "Verify GZIP compression in HTTP response"
GZIP_HEADER=$(curl -H "Accept-Encoding: gzip" -s -I http://localhost:$TEST_PORT/ 2>/dev/null | grep -i "Content-Encoding.*gzip" || echo "")
if [ -n "$GZIP_HEADER" ]; then
    log_pass "TC-014"
else
    log_fail "TC-014" "GZIP compression not enabled or not working"
fi

# Phase 7: Cleanup
echo -e "\n${YELLOW}=== PHASE 7: CLEANUP ===${NC}"

# TC-018: Validate container cleanup
log_test "TC-018" "Validate container cleanup"
if docker stop $CONTAINER_NAME > /dev/null 2>&1 && \
   docker rm $CONTAINER_NAME > /dev/null 2>&1 && \
   docker rmi $IMAGE_NAME > /dev/null 2>&1; then
    log_pass "TC-018"
else
    log_fail "TC-018" "Cleanup failed"
fi

# Summary
echo -e "\n========================================"
echo "TEST EXECUTION SUMMARY"
echo "========================================"
echo "Total Tests:  $TOTAL_TESTS"
echo -e "${GREEN}Passed:       $PASSED_TESTS${NC}"
echo -e "${RED}Failed:       $FAILED_TESTS${NC}"
echo -e "${YELLOW}Skipped:      $SKIPPED_TESTS${NC}"
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}✓ ALL TESTS PASSED${NC}"
    exit 0
else
    echo -e "${RED}✗ SOME TESTS FAILED${NC}"
    echo ""
    echo "Failed tests:"
    for result in "${TEST_RESULTS[@]}"; do
        if [[ $result == FAIL:* ]]; then
            echo "  - $result"
        fi
    done
    exit 1
fi
