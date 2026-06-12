"""
Unit tests for RateLimiter class.

Tests individual components:
- Token bucket algorithm
- Client identifier extraction
- Role detection from JWT tokens
- Redis state management
"""
import pytest
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi import Request
from app.middleware.rate_limiter import RateLimiter
from app.models.user import UserRole


@pytest.fixture
def rate_limiter():
    """Create a RateLimiter instance for testing."""
    return RateLimiter()


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    mock_client = AsyncMock()
    mock_client.pipeline = MagicMock()
    
    # Mock pipeline
    mock_pipe = AsyncMock()
    mock_pipe.hgetall = MagicMock()
    mock_pipe.ttl = MagicMock()
    mock_pipe.execute = AsyncMock()
    mock_client.pipeline.return_value = mock_pipe
    
    return mock_client


@pytest.fixture
def mock_request():
    """Create a mock FastAPI request."""
    request = Mock(spec=Request)
    request.headers = {}
    request.client = Mock()
    request.client.host = "192.168.1.100"
    request.url = Mock()
    request.url.path = "/api/test"
    return request


class TestClientIdentifier:
    """Test client identifier extraction logic."""
    
    @pytest.mark.asyncio
    async def test_user_id_identifier(self, rate_limiter, mock_request):
        """Test that user ID is used when available."""
        identifier = await rate_limiter._get_client_identifier(mock_request, user_id="test-user-123")
        assert identifier == "user:test-user-123"
    
    @pytest.mark.asyncio
    async def test_ip_identifier_direct_connection(self, rate_limiter, mock_request):
        """Test IP extraction from direct connection."""
        identifier = await rate_limiter._get_client_identifier(mock_request, user_id=None)
        assert identifier == "ip:192.168.1.100"
    
    @pytest.mark.asyncio
    async def test_ip_extraction_x_forwarded_for(self, rate_limiter, mock_request):
        """Test IP extraction from X-Forwarded-For header."""
        mock_request.headers = {"X-Forwarded-For": "203.0.113.45, 198.51.100.1"}
        identifier = await rate_limiter._get_client_identifier(mock_request, user_id=None)
        assert identifier == "ip:203.0.113.45"
    
    @pytest.mark.asyncio
    async def test_ip_extraction_x_real_ip(self, rate_limiter, mock_request):
        """Test IP extraction from X-Real-IP header."""
        mock_request.headers = {"X-Real-IP": "198.51.100.50"}
        identifier = await rate_limiter._get_client_identifier(mock_request, user_id=None)
        assert identifier == "ip:198.51.100.50"
    
    @pytest.mark.asyncio
    async def test_ip_extraction_priority(self, rate_limiter, mock_request):
        """Test that X-Forwarded-For takes priority over X-Real-IP."""
        mock_request.headers = {
            "X-Forwarded-For": "203.0.113.45",
            "X-Real-IP": "198.51.100.50"
        }
        identifier = await rate_limiter._get_client_identifier(mock_request, user_id=None)
        assert identifier == "ip:203.0.113.45"


class TestUserInfoExtraction:
    """Test user role and ID extraction from JWT tokens."""
    
    @pytest.mark.asyncio
    async def test_no_authorization_header(self, rate_limiter, mock_request):
        """Test fallback to anonymous when no auth header."""
        role, user_id = await rate_limiter._get_user_info(mock_request)
        assert role == UserRole.ANONYMOUS
        assert user_id is None
    
    @pytest.mark.asyncio
    async def test_invalid_authorization_header(self, rate_limiter, mock_request):
        """Test fallback to anonymous with invalid auth header."""
        mock_request.headers = {"Authorization": "InvalidFormat"}
        role, user_id = await rate_limiter._get_user_info(mock_request)
        assert role == UserRole.ANONYMOUS
        assert user_id is None
    
    @pytest.mark.asyncio
    async def test_valid_user_token(self, rate_limiter, mock_request):
        """Test extraction of USER role from valid token."""
        with patch('app.middleware.rate_limiter.decode_token_unsafe') as mock_decode:
            mock_decode.return_value = {"user_id": "test-user-123", "role": "user"}
            mock_request.headers = {"Authorization": "Bearer valid.token.here"}
            
            role, user_id = await rate_limiter._get_user_info(mock_request)
            assert role == UserRole.USER
            assert user_id == "test-user-123"
    
    @pytest.mark.asyncio
    async def test_valid_admin_token(self, rate_limiter, mock_request):
        """Test extraction of ADMIN role from valid token."""
        with patch('app.middleware.rate_limiter.decode_token_unsafe') as mock_decode:
            mock_decode.return_value = {"user_id": "admin-user-456", "role": "admin"}
            mock_request.headers = {"Authorization": "Bearer valid.admin.token"}
            
            role, user_id = await rate_limiter._get_user_info(mock_request)
            assert role == UserRole.ADMIN
            assert user_id == "admin-user-456"
    
    @pytest.mark.asyncio
    async def test_token_decode_failure(self, rate_limiter, mock_request):
        """Test fallback to anonymous on token decode failure."""
        with patch('app.middleware.rate_limiter.decode_token_unsafe') as mock_decode:
            mock_decode.side_effect = Exception("Decode error")
            mock_request.headers = {"Authorization": "Bearer invalid.token"}

            role, user_id = await rate_limiter._get_user_info(mock_request)
            assert role == UserRole.ANONYMOUS
            assert user_id is None


class TestTokenBucketAlgorithm:
    """Test token bucket rate limiting algorithm."""

    @pytest.mark.asyncio
    async def test_first_request_creates_bucket(self, rate_limiter):
        """Test that first request creates a new bucket."""
        with patch.object(rate_limiter.redis, 'client') as mock_redis:
            # Mock empty bucket (key doesn't exist)
            mock_pipe = AsyncMock()
            mock_pipe.execute = AsyncMock(return_value=[{}, -2])  # Empty bucket, TTL -2
            mock_redis.pipeline.return_value = mock_pipe
            mock_redis.hset = AsyncMock()
            mock_redis.expire = AsyncMock()

            allowed, remaining, reset_time, limit = await rate_limiter.check_rate_limit(
                "user:test-123", limit=100, window=60
            )

            assert allowed is True
            assert remaining == 99  # limit - 1
            assert limit == 100
            mock_redis.hset.assert_called_once()
            mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_tokens_decrement_on_requests(self, rate_limiter):
        """Test that tokens decrement with each request."""
        with patch.object(rate_limiter.redis, 'client') as mock_redis:
            now = int(time.time())

            # Mock existing bucket with 50 tokens
            mock_pipe = AsyncMock()
            mock_pipe.execute = AsyncMock(return_value=[
                {"tokens": "50", "last_refill": str(now), "reset_time": str(now + 60)},
                30  # TTL
            ])
            mock_redis.pipeline.return_value = mock_pipe
            mock_redis.hset = AsyncMock()

            allowed, remaining, reset_time, limit = await rate_limiter.check_rate_limit(
                "user:test-123", limit=100, window=60
            )

            assert allowed is True
            assert remaining == 49  # 50 - 1
            mock_redis.hset.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, rate_limiter):
        """Test that requests are denied when tokens exhausted."""
        with patch.object(rate_limiter.redis, 'client') as mock_redis:
            now = int(time.time())

            # Mock bucket with 0 tokens
            mock_pipe = AsyncMock()
            mock_pipe.execute = AsyncMock(return_value=[
                {"tokens": "0", "last_refill": str(now), "reset_time": str(now + 60)},
                30  # TTL
            ])
            mock_redis.pipeline.return_value = mock_pipe

            allowed, remaining, reset_time, limit = await rate_limiter.check_rate_limit(
                "user:test-123", limit=100, window=60
            )

            assert allowed is False
            assert remaining == 0

    @pytest.mark.asyncio
    async def test_bucket_refills_after_window(self, rate_limiter):
        """Test that bucket refills after window expires."""
        with patch.object(rate_limiter.redis, 'client') as mock_redis:
            now = int(time.time())
            past_time = now - 120  # 2 minutes ago

            # Mock expired bucket
            mock_pipe = AsyncMock()
            mock_pipe.execute = AsyncMock(return_value=[
                {"tokens": "0", "last_refill": str(past_time), "reset_time": str(past_time + 60)},
                30  # TTL
            ])
            mock_redis.pipeline.return_value = mock_pipe
            mock_redis.hset = AsyncMock()
            mock_redis.expire = AsyncMock()

            allowed, remaining, reset_time, limit = await rate_limiter.check_rate_limit(
                "user:test-123", limit=100, window=60
            )

            assert allowed is True
            assert remaining == 99  # Refilled to limit - 1
            mock_redis.hset.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_failure_allows_request(self, rate_limiter):
        """Test fail-open behavior on Redis errors."""
        with patch.object(rate_limiter.redis, 'client') as mock_redis:
            mock_redis.pipeline.side_effect = Exception("Redis connection error")

            allowed, remaining, reset_time, limit = await rate_limiter.check_rate_limit(
                "user:test-123", limit=100, window=60
            )

            assert allowed is True  # Fail-open
            assert remaining == 99
