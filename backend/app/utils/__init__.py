"""
Utilities package for common helper functions.

This package contains utility modules for:
- Text processing and normalization
- Date/time handling
- Data validation
- Helper functions for various operations
- Redis client with session and cache management
"""

from app.utils.redis_client import RedisClient, redis_client

__all__ = ["RedisClient", "redis_client"]
