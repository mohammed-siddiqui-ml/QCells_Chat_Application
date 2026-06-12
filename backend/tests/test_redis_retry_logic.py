"""
Tests for Redis retry logic and error handling.

Tests cover:
- Retry on transient ConnectionError
- Exponential backoff delays
- Max retries exceeded
- Non-ConnectionError exceptions are not retried
"""
import pytest
import pytest_asyncio
import asyncio
import fakeredis.aioredis
from unittest.mock import AsyncMock, patch, MagicMock
from redis.exceptions import ConnectionError, RedisError
from app.utils.redis_client import RedisClient


@pytest_asyncio.fixture(scope='function')
async def redis_client_mock():
    """Redis client with fakeredis for testing"""
    client = RedisClient(redis_url="redis://localhost:6379/15", max_connections=10)

    # Replace the real Redis client with fakeredis
    client.pool = None
    client.client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.close()


# ========================================================================
# Test Group E: Retry Logic and Error Handling
# ========================================================================

@pytest.mark.asyncio
async def test_retry_on_connection_error_success(redis_client_mock):
    """TC-E2: Retry on transient ConnectionError (success on retry)"""
    client = redis_client_mock
    
    # Mock to fail once, then succeed
    call_count = 0
    
    async def mock_operation():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("Connection refused")
        return "success"
    
    # Execute with retry
    result = await client._execute_with_retry(mock_operation)
    
    assert result == "success"
    assert call_count == 2  # 1 initial + 1 retry


@pytest.mark.asyncio
async def test_exponential_backoff_delays(redis_client_mock):
    """TC-E3: Exponential backoff delays (1s, 2s)"""
    client = redis_client_mock

    call_count = 0

    async def mock_operation():
        nonlocal call_count
        call_count += 1
        if call_count < 3:  # Fail first 2 attempts, succeed on 3rd
            raise ConnectionError("Connection refused")
        return "success"

    # Mock sleep to avoid actual delays but capture them
    original_sleep = asyncio.sleep
    sleep_delays = []

    async def mock_sleep(delay):
        sleep_delays.append(delay)
        # Don't actually sleep in tests
        await original_sleep(0.01)

    with patch('asyncio.sleep', mock_sleep):
        result = await client._execute_with_retry(mock_operation)

    assert result == "success"
    assert call_count == 3  # 1 initial + 2 retries
    assert sleep_delays == [1, 2]  # Exponential backoff


@pytest.mark.asyncio
async def test_max_retries_exceeded(redis_client_mock):
    """TC-E4: Max retries exceeded (3 attempts) - raises error"""
    client = redis_client_mock
    
    call_count = 0
    
    async def mock_operation():
        nonlocal call_count
        call_count += 1
        raise ConnectionError("Connection refused")
    
    # Mock sleep to avoid delays
    with patch('asyncio.sleep', AsyncMock()):
        with pytest.raises(ConnectionError):
            await client._execute_with_retry(mock_operation)
    
    assert call_count == 3  # 1 initial + 2 retries (max_retries=3 means 3 total attempts)


@pytest.mark.asyncio
async def test_non_connection_error_not_retried(redis_client_mock):
    """TC-E5: Non-ConnectionError exceptions are not retried"""
    client = redis_client_mock
    
    call_count = 0
    
    async def mock_operation():
        nonlocal call_count
        call_count += 1
        raise RedisError("Some other Redis error")
    
    with pytest.raises(RedisError):
        await client._execute_with_retry(mock_operation)
    
    assert call_count == 1  # No retries for non-ConnectionError


# ========================================================================
# Additional Edge Cases
# ========================================================================

@pytest.mark.asyncio
async def test_create_session_with_custom_ttl(redis_client_mock):
    """TC-B2: Create session with custom TTL"""
    client = redis_client_mock
    
    # Flush DB first
    await client.client.flushdb()
    
    session_data = {"user_id": "anon_custom"}
    custom_ttl = 300  # 5 minutes
    
    session_token = await client.create_session(session_data, ttl=custom_ttl)
    
    # Verify TTL
    key = f"session:{session_token}"
    ttl = await client.client.ttl(key)
    assert 290 <= ttl <= 300  # ±10 seconds
    
    # Cleanup
    await client.client.flushdb()


@pytest.mark.asyncio
async def test_cache_query_with_custom_ttl(redis_client_mock):
    """TC-C2: Cache query result with custom TTL"""
    client = redis_client_mock
    
    # Flush DB first
    await client.client.flushdb()
    
    query_key = "custom_ttl_query"
    result = {"data": "test"}
    custom_ttl = 600  # 10 minutes
    
    await client.set_cached_query(query_key, result, ttl=custom_ttl)
    
    # Verify TTL
    key = f"query:{query_key}"
    ttl = await client.client.ttl(key)
    assert 590 <= ttl <= 600  # ±10 seconds
    
    # Cleanup
    await client.client.flushdb()


@pytest.mark.asyncio
async def test_update_session_nonexistent(redis_client_mock):
    """TC-B6: Update non-existent session returns False"""
    client = redis_client_mock
    
    # Flush DB first
    await client.client.flushdb()
    
    fake_token = "00000000-0000-0000-0000-000000000000:fake"
    result = await client.update_session(fake_token, {"data": "test"})
    
    assert result is False
    
    # Cleanup
    await client.client.flushdb()
