"""
Redis client wrapper with connection pooling, async support, and session management.

This module provides:
- Async Redis client with connection pooling
- Session management for anonymous users
- Query result caching with configurable TTL
- Cache invalidation by pattern matching
- Health check and retry logic with exponential backoff
"""
import asyncio
import json
import secrets
import uuid
from typing import Any, Dict, Optional
from datetime import timedelta

import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import ConnectionError, RedisError

from app.core.config import settings
from app.core.logging import logger


class RedisClient:
    """
    Async Redis client with connection pooling and retry logic.
    
    Provides methods for session management, caching, and health checks.
    """
    
    def __init__(self, redis_url: str = settings.REDIS_URL, max_connections: int = 50):
        """
        Initialize Redis client with connection pool.
        
        Args:
            redis_url: Redis connection URL
            max_connections: Maximum number of connections in the pool
        """
        self.redis_url = redis_url
        self.max_connections = max_connections
        self.pool: Optional[ConnectionPool] = None
        self.client: Optional[aioredis.Redis] = None
        
        # Default TTL values (in seconds)
        self.SESSION_TTL = 86400  # 24 hours
        self.QUERY_CACHE_TTL = 3600  # 1 hour
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delays = [1, 2, 4]  # Exponential backoff in seconds
    
    async def initialize(self) -> None:
        """Initialize connection pool and Redis client."""
        if self.pool is None:
            self.pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.max_connections,
                decode_responses=True
            )
            self.client = aioredis.Redis(connection_pool=self.pool)
            logger.info(f"Redis client initialized with max_connections={self.max_connections}")
    
    async def close(self) -> None:
        """Close Redis connections and cleanup."""
        if self.client:
            await self.client.close()
        if self.pool:
            await self.pool.disconnect()
        logger.info("Redis client closed")
    
    async def _execute_with_retry(self, operation, *args, **kwargs) -> Any:
        """
        Execute Redis operation with retry logic and exponential backoff.
        
        Args:
            operation: Redis operation to execute
            *args: Positional arguments for the operation
            **kwargs: Keyword arguments for the operation
            
        Returns:
            Result of the operation
            
        Raises:
            ConnectionError: If all retries fail
        """
        for attempt in range(self.max_retries):
            try:
                return await operation(*args, **kwargs)
            except ConnectionError as e:
                if attempt < self.max_retries - 1:
                    delay = self.retry_delays[attempt]
                    logger.warning(
                        f"Redis connection error (attempt {attempt + 1}/{self.max_retries}): {e}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Redis connection failed after {self.max_retries} retries: {e}")
                    raise
            except RedisError as e:
                logger.error(f"Redis error: {e}")
                raise
    
    async def health_check(self) -> bool:
        """
        Check Redis connection health.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            await self._execute_with_retry(self.client.ping)
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
    
    # ========================================================================
    # Session Management
    # ========================================================================
    
    def generate_session_token(self) -> str:
        """
        Generate a secure session token for anonymous users.
        
        Returns:
            Unique session token combining UUID and url-safe random string
        """
        unique_id = str(uuid.uuid4())
        random_token = secrets.token_urlsafe(32)
        return f"{unique_id}:{random_token}"
    
    async def create_session(self, session_data: Dict[str, Any], ttl: Optional[int] = None) -> str:
        """
        Create a new session with the given data.
        
        Args:
            session_data: Dictionary containing session data
            ttl: Time-to-live in seconds (default: 24 hours)
            
        Returns:
            Session token
        """
        session_token = self.generate_session_token()
        ttl = ttl or self.SESSION_TTL
        key = f"session:{session_token}"
        
        await self._execute_with_retry(
            self.client.setex,
            key,
            ttl,
            json.dumps(session_data)
        )
        logger.debug(f"Session created: {session_token} (TTL: {ttl}s)")
        return session_token

    async def get_session(self, session_token: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session data by token.

        Args:
            session_token: Session token

        Returns:
            Session data dictionary or None if not found
        """
        key = f"session:{session_token}"
        data = await self._execute_with_retry(self.client.get, key)

        if data:
            return json.loads(data)
        return None

    async def update_session(
        self,
        session_token: str,
        session_data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Update existing session data.

        Args:
            session_token: Session token
            session_data: Updated session data
            ttl: Time-to-live in seconds (default: 24 hours)

        Returns:
            True if successful, False otherwise
        """
        key = f"session:{session_token}"
        ttl = ttl or self.SESSION_TTL

        # Check if session exists
        exists = await self._execute_with_retry(self.client.exists, key)
        if not exists:
            logger.warning(f"Session not found for update: {session_token}")
            return False

        await self._execute_with_retry(
            self.client.setex,
            key,
            ttl,
            json.dumps(session_data)
        )
        logger.debug(f"Session updated: {session_token}")
        return True

    async def delete_session(self, session_token: str) -> bool:
        """
        Delete a session.

        Args:
            session_token: Session token

        Returns:
            True if deleted, False if not found
        """
        key = f"session:{session_token}"
        result = await self._execute_with_retry(self.client.delete, key)

        if result:
            logger.debug(f"Session deleted: {session_token}")
            return True
        return False

    # ========================================================================
    # Query Cache Management
    # ========================================================================

    async def get_cached_query(self, query_key: str) -> Optional[Any]:
        """
        Retrieve cached query result.

        Args:
            query_key: Cache key for the query

        Returns:
            Cached result or None if not found
        """
        key = f"query:{query_key}"
        data = await self._execute_with_retry(self.client.get, key)

        if data:
            return json.loads(data)
        return None

    async def set_cached_query(
        self,
        query_key: str,
        result: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache a query result with configurable TTL.

        Args:
            query_key: Cache key for the query
            result: Query result to cache
            ttl: Time-to-live in seconds (default: 1 hour)

        Returns:
            True if successful
        """
        key = f"query:{query_key}"
        ttl = ttl or self.QUERY_CACHE_TTL

        await self._execute_with_retry(
            self.client.setex,
            key,
            ttl,
            json.dumps(result)
        )
        logger.debug(f"Query cached: {query_key} (TTL: {ttl}s)")
        return True

    # ========================================================================
    # Cache Invalidation
    # ========================================================================

    async def clear_cache_pattern(self, pattern: str) -> int:
        """
        Clear cache entries matching a pattern using SCAN for safe deletion.

        Args:
            pattern: Pattern to match (e.g., "query:*")

        Returns:
            Number of keys deleted
        """
        deleted_count = 0
        cursor = 0

        while True:
            # Use SCAN for safe iteration without blocking
            cursor, keys = await self._execute_with_retry(
                self.client.scan,
                cursor=cursor,
                match=pattern,
                count=100
            )

            if keys:
                # Delete matched keys
                deleted = await self._execute_with_retry(self.client.delete, *keys)
                deleted_count += deleted

            # Break when cursor returns to 0
            if cursor == 0:
                break

        logger.info(f"Cleared {deleted_count} cache entries matching pattern: {pattern}")
        return deleted_count

    # ========================================================================
    # Cache Statistics
    # ========================================================================

    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary containing cache statistics
        """
        info = await self._execute_with_retry(self.client.info, "stats")

        # Count keys by pattern
        session_count = await self._count_keys_by_pattern("session:*")
        query_count = await self._count_keys_by_pattern("query:*")

        return {
            "total_connections": info.get("total_connections_received", 0),
            "total_commands": info.get("total_commands_processed", 0),
            "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
            "session_count": session_count,
            "query_cache_count": query_count,
        }

    async def _count_keys_by_pattern(self, pattern: str) -> int:
        """
        Count keys matching a pattern using SCAN.

        Args:
            pattern: Pattern to match

        Returns:
            Number of matching keys
        """
        count = 0
        cursor = 0

        while True:
            cursor, keys = await self._execute_with_retry(
                self.client.scan,
                cursor=cursor,
                match=pattern,
                count=100
            )
            count += len(keys)

            if cursor == 0:
                break

        return count


# Global Redis client instance
redis_client = RedisClient()
