#!/bin/bash

# Frontend Dockerfile Static Test Suite
# Tests that can be performed without Docker runtime

# Don't exit on error - we want to capture all test results
set +e

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

# Helper functions
log_test() {
    echo -e "\n${YELLOW}[TEST $1]${NC} $2"
    ((TOTAL_TESTS++))
}

log_pass() {
    echo -e "${GREEN}✓ PASSED${NC}: $1"
    ((PASSED_TESTS++))
    TEST_RESULTS+=("PASS: $1")
}

log_fail() {
    echo -e "${RED}✗ FAILED${NC}: $1"
    echo -e "${RED}  Error: $2${NC}"
    ((FAILED_TESTS++))
    TEST_RESULTS+=("FAIL: $1 - $2")
}

log_skip() {
    echo -e "${YELLOW}⊘ SKIPPED${NC}: $1 - $2"
    ((SKIPPED_TESTS++))
    TEST_RESULTS+=("SKIP: $1")
}

echo "========================================"
echo "Frontend Dockerfile Static Test Suite"
echo "========================================"
echo "Date: $(date)"
echo ""

# Phase 1: Pre-Build Validation
echo -e "\n${YELLOW}=== PHASE 1: DOCKERFILE VALIDATION ===${NC}"

# TC-001: Validate Dockerfile base images
log_test "TC-001" "Validate Dockerfile base images"
if [ ! -f "Dockerfile" ]; then
    log_fail "TC-001" "Dockerfile does not exist"
else
    BUILDER_IMAGE=$(grep "FROM.*AS builder" Dockerfile | awk '{print $2}')
    PROD_IMAGE=$(grep "FROM nginx" Dockerfile | awk '{print $2}')
    
    if [ "$BUILDER_IMAGE" = "node:20-alpine" ] && [ "$PROD_IMAGE" = "nginx:1.25-alpine" ]; then
        log_pass "TC-001"
        echo "  Builder image: $BUILDER_IMAGE"
        echo "  Production image: $PROD_IMAGE"
    else
        log_fail "TC-001" "Base images incorrect. Found: builder=$BUILDER_IMAGE, prod=$PROD_IMAGE"
    fi
fi

# TC-002: Verify multi-stage build configuration
log_test "TC-002" "Verify multi-stage build configuration"
if [ ! -f "Dockerfile" ]; then
    log_fail "TC-002" "Dockerfile does not exist"
else
    HAS_NPM_CI=$(grep -c "npm ci" Dockerfile || echo "0")
    HAS_NPM_BUILD=$(grep -c "npm run build" Dockerfile || echo "0")
    HAS_COPY_FROM=$(grep -c "COPY --from=builder" Dockerfile || echo "0")
    
    if [ "$HAS_NPM_CI" -gt 0 ] && [ "$HAS_NPM_BUILD" -gt 0 ] && [ "$HAS_COPY_FROM" -gt 0 ]; then
        log_pass "TC-002"
        echo "  ✓ npm ci command found"
        echo "  ✓ npm run build command found"
        echo "  ✓ COPY --from=builder found"
    else
        MISSING=""
        [ "$HAS_NPM_CI" -eq 0 ] && MISSING="$MISSING npm-ci"
        [ "$HAS_NPM_BUILD" -eq 0 ] && MISSING="$MISSING npm-run-build"
        [ "$HAS_COPY_FROM" -eq 0 ] && MISSING="$MISSING copy-from-builder"
        log_fail "TC-002" "Missing components:$MISSING"
    fi
fi

# TC-003: Verify Dockerfile WORKDIR
log_test "TC-003" "Verify Dockerfile WORKDIR configuration"
if grep -q "WORKDIR /app" Dockerfile; then
    log_pass "TC-003"
else
    log_fail "TC-003" "WORKDIR not set to /app"
fi

# TC-004: Verify EXPOSE port
log_test "TC-004" "Verify EXPOSE port 80"
if grep -q "EXPOSE 80" Dockerfile; then
    log_pass "TC-004"
else
    log_fail "TC-004" "EXPOSE 80 not found"
fi

# TC-005: Verify HEALTHCHECK configuration
log_test "TC-005" "Verify HEALTHCHECK configuration"
if grep -q "HEALTHCHECK" Dockerfile; then
    log_pass "TC-005"
    HEALTHCHECK=$(grep "HEALTHCHECK" Dockerfile)
    echo "  $HEALTHCHECK"
else
    log_fail "TC-005" "HEALTHCHECK not configured"
fi

# TC-006: Verify CMD instruction
log_test "TC-006" "Verify CMD starts nginx"
if grep -q 'CMD.*nginx.*daemon off' Dockerfile; then
    log_pass "TC-006"
else
    log_fail "TC-006" "CMD does not start nginx correctly"
fi

# Phase 2: Nginx Configuration Validation
echo -e "\n${YELLOW}=== PHASE 2: NGINX CONFIGURATION VALIDATION ===${NC}"

# TC-007: Check nginx.conf exists
log_test "TC-007" "Verify nginx.conf exists"
if [ -f "nginx.conf" ]; then
    log_pass "TC-007"
else
    log_fail "TC-007" "nginx.conf does not exist"
fi

# TC-008: Verify SPA routing configuration
log_test "TC-008" "Verify SPA routing configuration"
if grep -q "try_files.*\$uri.*\$uri/.*index.html" nginx.conf; then
    log_pass "TC-008"
    grep "try_files" nginx.conf | head -1 | sed 's/^/  /'
else
    log_fail "TC-008" "SPA routing try_files not configured correctly"
fi

# TC-009: Verify GZIP compression configuration
log_test "TC-009" "Verify GZIP compression configuration"
HAS_GZIP_ON=$(grep -c "gzip on" nginx.conf || echo "0")
HAS_TEXT_HTML=$(grep "gzip_types" nginx.conf | grep -c "text/html" || echo "0")
HAS_TEXT_CSS=$(grep "gzip_types" nginx.conf | grep -c "text/css" || echo "0")
HAS_APP_JS=$(grep "gzip_types" nginx.conf | grep -c "application/javascript" || echo "0")

if [ "$HAS_GZIP_ON" -gt 0 ] && [ "$HAS_TEXT_HTML" -gt 0 ] && [ "$HAS_TEXT_CSS" -gt 0 ] && [ "$HAS_APP_JS" -gt 0 ]; then
    log_pass "TC-009"
    grep "gzip" nginx.conf | grep -v "^#" | sed 's/^/  /'
else
    log_fail "TC-009" "GZIP compression not fully configured"
fi

# TC-010: Verify security headers configuration
log_test "TC-010" "Verify security headers configuration"
HAS_XCO=$(grep -c "X-Content-Type-Options.*nosniff.*always" nginx.conf || echo "0")
HAS_XFO=$(grep -c "X-Frame-Options.*DENY.*always" nginx.conf || echo "0")
HAS_CSP=$(grep -c "Content-Security-Policy" nginx.conf || echo "0")

if [ "$HAS_XCO" -gt 0 ] && [ "$HAS_XFO" -gt 0 ] && [ "$HAS_CSP" -gt 0 ]; then
    log_pass "TC-010"
    echo "  ✓ X-Content-Type-Options: nosniff"
    echo "  ✓ X-Frame-Options: DENY"
    echo "  ✓ Content-Security-Policy configured"
else
    MISSING=""
    [ "$HAS_XCO" -eq 0 ] && MISSING="$MISSING X-Content-Type-Options"
    [ "$HAS_XFO" -eq 0 ] && MISSING="$MISSING X-Frame-Options"
    [ "$HAS_CSP" -eq 0 ] && MISSING="$MISSING Content-Security-Policy"
    log_fail "TC-010" "Missing security headers:$MISSING"
fi

# TC-011: Verify API proxy configuration
log_test "TC-011" "Verify API proxy configuration"
HAS_API_LOCATION=$(grep -c "location /api" nginx.conf || echo "0")
HAS_PROXY_PASS=$(grep -c "proxy_pass http://backend:8000" nginx.conf || echo "0")
HAS_REAL_IP=$(grep -c "X-Real-IP" nginx.conf || echo "0")
HAS_FORWARDED=$(grep -c "X-Forwarded-For" nginx.conf || echo "0")
HAS_UPGRADE=$(grep -c "Upgrade.*http_upgrade" nginx.conf || echo "0")

if [ "$HAS_API_LOCATION" -gt 0 ] && [ "$HAS_PROXY_PASS" -gt 0 ] && [ "$HAS_REAL_IP" -gt 0 ] && [ "$HAS_FORWARDED" -gt 0 ] && [ "$HAS_UPGRADE" -gt 0 ]; then
    log_pass "TC-011"
    echo "  ✓ /api location configured"
    echo "  ✓ proxy_pass to backend:8000"
    echo "  ✓ Proxy headers configured"
    echo "  ✓ WebSocket upgrade support"
else
    MISSING=""
    [ "$HAS_API_LOCATION" -eq 0 ] && MISSING="$MISSING location-/api"
    [ "$HAS_PROXY_PASS" -eq 0 ] && MISSING="$MISSING proxy_pass"
    [ "$HAS_REAL_IP" -eq 0 ] && MISSING="$MISSING X-Real-IP"
    [ "$HAS_FORWARDED" -eq 0 ] && MISSING="$MISSING X-Forwarded-For"
    [ "$HAS_UPGRADE" -eq 0 ] && MISSING="$MISSING WebSocket-upgrade"
    log_fail "TC-011" "Missing API proxy components:$MISSING"
fi

# TC-012: Verify static asset caching
log_test "TC-012" "Verify static asset caching configuration"
if grep -q "location.*\.(js|css|png" nginx.conf && grep -q "expires.*1y" nginx.conf; then
    log_pass "TC-012"
    grep "location.*\.(js|css" nginx.conf | head -1 | sed 's/^/  /'
    grep "expires" nginx.conf | grep -v "^#" | head -1 | sed 's/^/  /'
else
    log_fail "TC-012" "Static asset caching not configured"
fi

# TC-013: Verify listen port
log_test "TC-013" "Verify nginx listens on port 80"
if grep -q "listen 80" nginx.conf; then
    log_pass "TC-013"
else
    log_fail "TC-013" "Nginx not configured to listen on port 80"
fi

# TC-014: Verify root directory
log_test "TC-014" "Verify root directory configuration"
if grep -q "root /usr/share/nginx/html" nginx.conf; then
    log_pass "TC-014"
else
    log_fail "TC-014" "Root directory not set to /usr/share/nginx/html"
fi

# TC-015: Verify index file
log_test "TC-015" "Verify index file configuration"
if grep -q "index index.html" nginx.conf; then
    log_pass "TC-015"
else
    log_fail "TC-015" "Index file not set to index.html"
fi

# Phase 3: Source Files Validation
echo -e "\n${YELLOW}=== PHASE 3: SOURCE FILES VALIDATION ===${NC}"

# TC-016: Verify package.json exists
log_test "TC-016" "Verify package.json exists"
if [ -f "package.json" ]; then
    log_pass "TC-016"
else
    log_fail "TC-016" "package.json not found"
fi

# TC-017: Verify build script in package.json
log_test "TC-017" "Verify build script in package.json"
if [ -f "package.json" ]; then
    if grep -q '"build"' package.json; then
        log_pass "TC-017"
        BUILD_SCRIPT=$(grep '"build"' package.json | head -1)
        echo "  $BUILD_SCRIPT"
    else
        log_fail "TC-017" "Build script not found in package.json"
    fi
else
    log_skip "TC-017" "package.json not found"
fi

# TC-018: Verify source files exist
log_test "TC-018" "Verify source files directory exists"
if [ -d "src" ]; then
    log_pass "TC-018"
    echo "  Source directory: src/"
    echo "  Files found: $(find src -type f | wc -l)"
else
    log_fail "TC-018" "src directory not found"
fi

# Phase 4: Docker Build Context Validation
echo -e "\n${YELLOW}=== PHASE 4: BUILD CONTEXT VALIDATION ===${NC}"

# TC-019: Verify Dockerfile copies nginx.conf
log_test "TC-019" "Verify Dockerfile copies nginx.conf"
if grep -q "COPY nginx.conf" Dockerfile; then
    log_pass "TC-019"
    grep "COPY nginx.conf" Dockerfile | sed 's/^/  /'
else
    log_fail "TC-019" "Dockerfile does not copy nginx.conf"
fi

# TC-020: Verify Dockerfile copies built files
log_test "TC-020" "Verify Dockerfile copies built files from builder"
if grep -q "COPY --from=builder /app/dist /usr/share/nginx/html" Dockerfile; then
    log_pass "TC-020"
else
    log_fail "TC-020" "Dockerfile does not copy built files correctly"
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

# Calculate pass rate
if [ $TOTAL_TESTS -gt 0 ]; then
    PASS_RATE=$((PASSED_TESTS * 100 / TOTAL_TESTS))
    echo "Pass Rate:    $PASS_RATE%"
fi

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
