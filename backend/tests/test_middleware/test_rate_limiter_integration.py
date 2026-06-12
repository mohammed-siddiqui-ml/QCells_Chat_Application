"""
Integration tests for Rate Limiting Middleware.

Tests end-to-end rate limiting behavior with FastAPI application:
- Rate limit enforcement across multiple requests
- Different limits for different user roles
- Header injection verification
- HTTP 429 response validation
- Bypass paths
"""
import pytest
import time
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from httpx import AsyncClient
import fakeredis.aioredis
from fakeredis import FakeServer
from app.middleware.rate_limiter import rate_limiter, RateLimiter
from app.models.user import UserRole
from app.core.security import create_access_token
from app.utils.redis_client import redis_client


# Create a test FastAPI app
@pytest.fixture
def test_app():
    """Create a FastAPI app with rate limiter middleware."""
    app = FastAPI()
    
    # Add rate limiter middleware
    app.middleware("http")(rate_limiter)
    
    # Add test endpoints
    @app.get("/api/test")
    async def test_endpoint():
        return {"message": "success"}
    
    @app.get("/health")
    async def health_endpoint():
        return {"status": "healthy"}
    
    @app.get("/ready")
    async def ready_endpoint():
        return {"status": "ready"}
    
    return app


@pytest.fixture
def client(test_app):
    """Create a test client."""
    return TestClient(test_app)


@pytest.fixture
async def async_client(test_app):
    """Create an async test client."""
    async with AsyncClient(app=test_app, base_url="http://test") as ac:
        yield ac


class FakeRedisPipeline:
    """Fake Redis pipeline for testing that works across event loops."""
    def __init__(self, storage):
        self.storage = storage
        self.commands = []

    def hgetall(self, key):
        self.commands.append(('hgetall', key))
        return self

    def ttl(self, key):
        self.commands.append(('ttl', key))
        return self

    async def execute(self):
        results = []
        for cmd, key in self.commands:
            if cmd == 'hgetall':
                results.append(self.storage.get(key, {}))
            elif cmd == 'ttl':
                ttl_key = f"{key}:ttl"
                results.append(self.storage.get(ttl_key, -2))
        return results


class FakeRedisClient:
    """Fake Redis client that works across event loops using simple dict storage."""
    def __init__(self):
        self.storage = {}

    def pipeline(self):
        return FakeRedisPipeline(self.storage)

    async def hset(self, key, *args, **kwargs):
        if 'mapping' in kwargs:
            if key not in self.storage:
                self.storage[key] = {}
            self.storage[key].update(kwargs['mapping'])
        elif len(args) == 2:
            # hset(key, field, value)
            if key not in self.storage:
                self.storage[key] = {}
            self.storage[key][args[0]] = args[1]
        return 1

    async def expire(self, key, seconds):
        # Store TTL separately
        ttl_key = f"{key}:ttl"
        self.storage[ttl_key] = seconds
        return 1

    async def keys(self, pattern):
        import re
        pattern_re = pattern.replace('*', '.*').replace('?', '.')
        return [k for k in self.storage.keys() if re.match(pattern_re, k) and not k.endswith(':ttl')]

    async def delete(self, *keys):
        deleted = 0
        for key in keys:
            if key in self.storage:
                del self.storage[key]
                deleted += 1
            ttl_key = f"{key}:ttl"
            if ttl_key in self.storage:
                del self.storage[ttl_key]
        return deleted

    async def close(self):
        pass


@pytest.fixture(scope="function", autouse=True)
def init_redis():
    """Initialize Redis client with fake client before tests and cleanup after."""
    # Store the original client (if any)
    original_client = redis_client.client
    original_pool = redis_client.pool

    # Create a fake Redis client
    fake_redis = FakeRedisClient()

    # Replace the redis_client's client with our fake one
    redis_client.client = fake_redis

    yield

    # Restore original client
    redis_client.client = original_client
    redis_client.pool = original_pool


@pytest.fixture
async def clear_redis():
    """Clear Redis test data before each test (deprecated, use init_redis)."""
    # This fixture is kept for backward compatibility but init_redis handles initialization
    yield


def create_test_token(user_id: str, role: str):
    """Helper to create test JWT tokens."""
    return create_access_token({"user_id": user_id, "role": role})


class TestAnonymousRateLimit:
    """Test rate limiting for anonymous users."""
    
    @pytest.mark.asyncio
    async def test_anonymous_user_20_requests_limit(self, client, clear_redis):
        """Test that anonymous users are limited to 20 requests per minute."""
        # Make 20 requests
        for i in range(20):
            response = client.get("/api/test")
            assert response.status_code == 200
            assert "X-RateLimit-Limit" in response.headers
            assert response.headers["X-RateLimit-Limit"] == "20"
            assert "X-RateLimit-Remaining" in response.headers
            assert "X-RateLimit-Reset" in response.headers
        
        # 21st request should be rate limited
        response = client.get("/api/test")
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert response.headers["X-RateLimit-Remaining"] == "0"
    
    @pytest.mark.asyncio
    async def test_rate_limit_headers_present(self, client, clear_redis):
        """Test that rate limit headers are present in responses."""
        response = client.get("/api/test")
        
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        
        assert response.headers["X-RateLimit-Limit"] == "20"
        assert response.headers["X-RateLimit-Remaining"] == "19"
        
        # Reset time should be in the future
        reset_time = int(response.headers["X-RateLimit-Reset"])
        assert reset_time > int(time.time())
    
    @pytest.mark.asyncio
    async def test_http_429_response_format(self, client, clear_redis):
        """Test that HTTP 429 response has correct format."""
        # Exhaust rate limit
        for i in range(20):
            client.get("/api/test")
        
        # Get 429 response
        response = client.get("/api/test")
        
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert response.headers["X-RateLimit-Remaining"] == "0"
        
        # Check response body
        data = response.json()
        assert "error" in data or "message" in data
        assert "retry_after" in data
        assert isinstance(data["retry_after"], int)


class TestAuthenticatedRateLimit:
    """Test rate limiting for authenticated users."""
    
    @pytest.mark.asyncio
    async def test_authenticated_user_100_requests_limit(self, client, clear_redis):
        """Test that authenticated users get 100 requests per minute."""
        token = create_test_token("test-user-123", "user")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Make 100 requests
        for i in range(100):
            response = client.get("/api/test", headers=headers)
            assert response.status_code == 200
            assert response.headers["X-RateLimit-Limit"] == "100"
        
        # 101st request should be rate limited
        response = client.get("/api/test", headers=headers)
        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_user_id_based_tracking(self, client, clear_redis):
        """Test that authenticated users are tracked by user_id, not IP."""
        token = create_test_token("user-789", "user")
        headers = {"Authorization": f"Bearer {token}"}

        # Anonymous user exhausts their limit (20 requests)
        for i in range(20):
            response = client.get("/api/test")
            assert response.status_code == 200

        # Anonymous should be rate limited now
        response = client.get("/api/test")
        assert response.status_code == 429

        # But authenticated user from same IP should still work
        response = client.get("/api/test", headers=headers)
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "100"


class TestAdminRateLimit:
    """Test rate limiting for admin users."""

    @pytest.mark.asyncio
    async def test_admin_user_300_requests_limit(self, client, clear_redis):
        """Test that admin users get 300 requests per minute."""
        token = create_test_token("admin-user-456", "admin")
        headers = {"Authorization": f"Bearer {token}"}

        # Make 300 requests
        for i in range(300):
            response = client.get("/api/test", headers=headers)
            assert response.status_code == 200
            assert response.headers["X-RateLimit-Limit"] == "300"

        # 301st request should be rate limited
        response = client.get("/api/test", headers=headers)
        assert response.status_code == 429


class TestBypassPaths:
    """Test that certain paths bypass rate limiting."""

    @pytest.mark.asyncio
    async def test_health_endpoint_bypasses_rate_limit(self, client, clear_redis):
        """Test that /health endpoint bypasses rate limiting."""
        # Make 25 requests (more than anonymous limit of 20)
        for i in range(25):
            response = client.get("/health")
            assert response.status_code == 200

        # All should succeed
        response = client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_ready_endpoint_bypasses_rate_limit(self, client, clear_redis):
        """Test that /ready endpoint bypasses rate limiting."""
        for i in range(25):
            response = client.get("/ready")
            assert response.status_code == 200

        response = client.get("/ready")
        assert response.status_code == 200


class TestIPExtraction:
    """Test IP address extraction from various headers."""

    @pytest.mark.asyncio
    async def test_x_forwarded_for_extraction(self, client, clear_redis):
        """Test IP extraction from X-Forwarded-For header."""
        headers = {"X-Forwarded-For": "203.0.113.45, 198.51.100.1"}

        # Make 20 requests with this IP
        for i in range(20):
            response = client.get("/api/test", headers=headers)
            assert response.status_code == 200

        # 21st should be rate limited
        response = client.get("/api/test", headers=headers)
        assert response.status_code == 429

        # Different IP should have separate limit
        different_headers = {"X-Forwarded-For": "203.0.113.99"}
        response = client.get("/api/test", headers=different_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_x_real_ip_extraction(self, client, clear_redis):
        """Test IP extraction from X-Real-IP header."""
        headers = {"X-Real-IP": "198.51.100.50"}

        # Make 20 requests
        for i in range(20):
            response = client.get("/api/test", headers=headers)
            assert response.status_code == 200

        # 21st should be rate limited
        response = client.get("/api/test", headers=headers)
        assert response.status_code == 429


class TestMultipleClients:
    """Test concurrent rate limiting for multiple clients."""

    @pytest.mark.asyncio
    async def test_independent_rate_limits_per_user(self, client, clear_redis):
        """Test that different users have independent rate limits."""
        user1_token = create_test_token("user-1", "user")
        user2_token = create_test_token("user-2", "user")

        user1_headers = {"Authorization": f"Bearer {user1_token}"}
        user2_headers = {"Authorization": f"Bearer {user2_token}"}

        # Each user makes 25 requests
        for i in range(25):
            response1 = client.get("/api/test", headers=user1_headers)
            response2 = client.get("/api/test", headers=user2_headers)
            assert response1.status_code == 200
            assert response2.status_code == 200

        # Both should still have tokens remaining (100 limit each)
        response1 = client.get("/api/test", headers=user1_headers)
        response2 = client.get("/api/test", headers=user2_headers)
        assert response1.status_code == 200
        assert response2.status_code == 200
