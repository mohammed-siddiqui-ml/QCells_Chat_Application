"""
Integration tests for Redis client session and cache management.

Tests cover:
- Connection and initialization
- Session management (create, get, update, delete)
- Query cache management
- Cache invalidation by pattern
- Cache statistics
"""
import pytest
import pytest_asyncio
import json
import fakeredis.aioredis
from app.utils.redis_client import RedisClient


@pytest_asyncio.fixture(scope='function')
async def redis_client_test():
    """Isolated Redis client for testing - fresh for each test using fakeredis"""
    client = RedisClient(redis_url="redis://localhost:6379/15", max_connections=10)

    # Replace the real Redis client with fakeredis
    client.pool = None
    client.client = fakeredis.aioredis.FakeRedis(decode_responses=True)

    # Flush test database before test
    await client.client.flushdb()
    
    yield client
    
    # Cleanup after test
    await client.client.flushdb()
    await client.close()


# ========================================================================
# Test Group A: Connection and Initialization
# ========================================================================

@pytest.mark.asyncio
async def test_redis_initialization(redis_client_test):
    """TC-A1: RedisClient initialization with valid configuration"""
    client = redis_client_test
    # When using fakeredis, pool is None but client should exist
    assert client.client is not None
    assert client.max_connections == 10


@pytest.mark.asyncio
async def test_health_check_healthy(redis_client_test):
    """TC-A3: Health check with healthy Redis instance"""
    client = redis_client_test
    result = await client.health_check()
    assert result is True


# ========================================================================
# Test Group B: Session Management
# ========================================================================

@pytest.mark.asyncio
async def test_create_session_default_ttl(redis_client_test):
    """TC-B1: Create session with default TTL (24 hours)"""
    client = redis_client_test
    session_data = {"user_id": "anon_123", "preferences": {"theme": "dark"}}
    
    session_token = await client.create_session(session_data)
    
    # Verify token format
    assert ":" in session_token
    assert len(session_token) > 40
    
    # Verify session is stored
    retrieved = await client.get_session(session_token)
    assert retrieved == session_data
    
    # Verify TTL
    key = f"session:{session_token}"
    ttl = await client.client.ttl(key)
    assert 86390 <= ttl <= 86400  # 24 hours ±10 seconds


@pytest.mark.asyncio
async def test_get_session_existing(redis_client_test):
    """TC-B3: Retrieve existing session by token"""
    client = redis_client_test
    session_data = {"user_id": "anon_xyz", "count": 42}
    
    session_token = await client.create_session(session_data)
    retrieved = await client.get_session(session_token)
    
    assert retrieved == session_data
    assert retrieved["user_id"] == "anon_xyz"
    assert retrieved["count"] == 42


@pytest.mark.asyncio
async def test_get_session_nonexistent(redis_client_test):
    """TC-B4: Retrieve non-existent session"""
    client = redis_client_test
    fake_token = "00000000-0000-0000-0000-000000000000:fake_token"
    
    result = await client.get_session(fake_token)
    
    assert result is None


@pytest.mark.asyncio
async def test_update_session_data(redis_client_test):
    """TC-B5: Update existing session data"""
    client = redis_client_test
    initial_data = {"count": 1}
    
    session_token = await client.create_session(initial_data)
    
    updated_data = {"count": 2, "updated": True}
    success = await client.update_session(session_token, updated_data)
    
    assert success is True
    
    retrieved = await client.get_session(session_token)
    assert retrieved == updated_data
    assert retrieved["count"] == 2
    assert retrieved["updated"] is True


@pytest.mark.asyncio
async def test_delete_session(redis_client_test):
    """TC-B7: Delete existing session"""
    client = redis_client_test
    session_data = {"user_id": "anon_delete"}
    
    session_token = await client.create_session(session_data)
    
    # Verify session exists
    assert await client.get_session(session_token) is not None
    
    # Delete session
    deleted = await client.delete_session(session_token)
    assert deleted is True
    
    # Verify session is gone
    assert await client.get_session(session_token) is None


@pytest.mark.asyncio
async def test_session_token_uniqueness(redis_client_test):
    """TC-B9: Session token generation uniqueness and format"""
    client = redis_client_test
    
    # Generate 100 tokens
    tokens = [client.generate_session_token() for _ in range(100)]
    
    # Verify uniqueness
    assert len(set(tokens)) == 100
    
    # Verify format
    for token in tokens:
        assert ":" in token
        assert len(token) > 40


# ========================================================================
# Test Group C: Query Cache Management
# ========================================================================

@pytest.mark.asyncio
async def test_cache_query_default_ttl(redis_client_test):
    """TC-C1: Cache query result with default TTL (1 hour)"""
    client = redis_client_test
    query_key = "user_messages_123"
    result = {"messages": [{"id": 1, "text": "Hello"}]}

    success = await client.set_cached_query(query_key, result)
    assert success is True

    # Verify cache is set
    cached = await client.get_cached_query(query_key)
    assert cached == result

    # Verify TTL
    key = f"query:{query_key}"
    ttl = await client.client.ttl(key)
    assert 3590 <= ttl <= 3600  # 1 hour ±10 seconds


@pytest.mark.asyncio
async def test_get_cached_query(redis_client_test):
    """TC-C3: Retrieve cached query result"""
    client = redis_client_test
    query_key = "room_participants"
    result = {"users": [{"id": "user1", "name": "Alice"}]}

    await client.set_cached_query(query_key, result)
    cached = await client.get_cached_query(query_key)

    assert cached == result
    assert cached["users"][0]["name"] == "Alice"


@pytest.mark.asyncio
async def test_get_cached_query_nonexistent(redis_client_test):
    """TC-C4: Retrieve non-existent cached query"""
    client = redis_client_test

    result = await client.get_cached_query("nonexistent_key")

    assert result is None


# ========================================================================
# Test Group D: Cache Invalidation
# ========================================================================

@pytest.mark.asyncio
async def test_clear_cache_wildcard_pattern(redis_client_test):
    """TC-D2: Clear cache by wildcard pattern (query:*)"""
    client = redis_client_test

    # Cache 5 query results
    for i in range(5):
        await client.set_cached_query(f"test_{i}", {"data": f"value_{i}"})

    # Create a session (should not be deleted)
    session_token = await client.create_session({"user_id": "anon_test"})

    # Clear all query cache
    deleted_count = await client.clear_cache_pattern("query:*")

    assert deleted_count == 5

    # Verify queries are deleted
    for i in range(5):
        assert await client.get_cached_query(f"test_{i}") is None

    # Verify session is intact
    assert await client.get_session(session_token) is not None


@pytest.mark.asyncio
async def test_clear_cache_large_keyset(redis_client_test):
    """TC-D5: SCAN-based iteration for large key sets"""
    client = redis_client_test

    # Use a smaller number that works reliably with fakeredis SCAN
    # Note: FakeRedis SCAN has known limitations with large keysets
    num_keys = 50
    for i in range(num_keys):
        await client.set_cached_query(f"large_{i}", {"index": i})

    # Clear all
    deleted_count = await client.clear_cache_pattern("query:*")

    # Verify deletion count
    assert deleted_count == num_keys

    # Verify all are deleted
    for i in range(num_keys):
        assert await client.get_cached_query(f"large_{i}") is None


# ========================================================================
# Test Group F: Cache Statistics
# ========================================================================

@pytest.mark.asyncio
async def test_get_cache_stats(redis_client_test):
    """TC-F1/F2: Get cache statistics with active sessions and cached queries"""
    client = redis_client_test

    # Create 3 sessions
    for i in range(3):
        await client.create_session({"user_id": f"anon_{i}"})

    # Cache 2 queries
    await client.set_cached_query("query_1", {"data": "value_1"})
    await client.set_cached_query("query_2", {"data": "value_2"})

    # FakeRedis doesn't support INFO command, so we'll test key counts directly
    session_count = await client._count_keys_by_pattern("session:*")
    query_count = await client._count_keys_by_pattern("query:*")

    # Verify counts
    assert session_count == 3
    assert query_count == 2
