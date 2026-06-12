"""
Rate limiting middleware using Redis-based token bucket algorithm.

This module provides:
- RateLimiter class with distributed rate limiting using Redis
- Token bucket algorithm implementation
- Per-user/IP rate tracking
- Configurable limits for different user roles
- Rate limit headers in responses
"""
import time
from typing import Optional, Callable
from fastapi import Request, HTTPException, status, Response
from fastapi.responses import JSONResponse

from app.core.logging import logger
from app.core.security import decode_token_unsafe
from app.utils.redis_client import redis_client
from app.models.user import UserRole


class RateLimiter:
    """
    Rate limiter implementing token bucket algorithm with Redis for distributed state.
    
    Supports different rate limits based on user roles:
    - Anonymous users: 20 requests/minute
    - Authenticated users: 100 requests/minute
    - Admin users: 300 requests/minute
    """
    
    # Rate limits per minute for different user types
    RATE_LIMITS = {
        UserRole.ANONYMOUS: 20,
        UserRole.USER: 100,
        UserRole.ADMIN: 300,
    }
    
    # Paths that bypass rate limiting
    BYPASS_PATHS = ["/health", "/ready", "/", "/docs", "/redoc", "/openapi.json"]
    
    def __init__(self):
        """Initialize rate limiter with Redis client."""
        self.redis = redis_client
    
    async def _get_client_identifier(self, request: Request, user_id: Optional[str] = None) -> str:
        """
        Get unique identifier for the client (user ID or IP address).

        Args:
            request: FastAPI request object
            user_id: User ID from JWT token (if available)

        Returns:
            Unique identifier string for rate limiting
        """
        # If we have a user ID from JWT, use it
        if user_id:
            return f"user:{user_id}"

        # For anonymous users, use IP address
        # Handle X-Forwarded-For header for proxied requests
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain (client IP)
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            # Use X-Real-IP if available
            client_ip = request.headers.get("X-Real-IP")
            if not client_ip and request.client:
                client_ip = request.client.host
            elif not client_ip:
                client_ip = "unknown"

        return f"ip:{client_ip}"

    async def _get_user_info(self, request: Request) -> tuple[UserRole, Optional[str]]:
        """
        Extract user role and ID from JWT token in Authorization header.

        Args:
            request: FastAPI request object

        Returns:
            Tuple of (UserRole, user_id or None)
        """
        # Try to get Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return UserRole.ANONYMOUS, None

        # Extract token
        token = auth_header.replace("Bearer ", "").strip()
        if not token:
            return UserRole.ANONYMOUS, None

        # Decode token (unsafe - no verification, just for rate limiting)
        try:
            payload = decode_token_unsafe(token)
            if not payload:
                return UserRole.ANONYMOUS, None

            # Extract user info from token
            user_id = payload.get("user_id")
            role_str = payload.get("role", "anonymous")

            # Convert role string to UserRole enum
            try:
                user_role = UserRole(role_str)
            except ValueError:
                user_role = UserRole.ANONYMOUS

            return user_role, user_id
        except Exception as e:
            logger.debug(f"Failed to decode token for rate limiting: {e}")
            return UserRole.ANONYMOUS, None
    
    async def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window: int = 60
    ) -> tuple[bool, int, int, int]:
        """
        Check rate limit using token bucket algorithm.
        
        Args:
            identifier: Unique identifier for the client
            limit: Maximum number of requests allowed in the window
            window: Time window in seconds (default: 60)
            
        Returns:
            Tuple of (allowed, remaining, reset_time, limit)
        """
        now = int(time.time())
        key = f"rate_limit:{identifier}"
        
        try:
            # Use Redis pipeline for atomic operations
            pipe = self.redis.client.pipeline()
            
            # Get current bucket state
            pipe.hgetall(key)
            pipe.ttl(key)
            results = await pipe.execute()
            
            bucket = results[0]
            ttl = results[1]

            # Initialize bucket if it doesn't exist or is expired
            if not bucket or ttl == -2:  # -2 means key doesn't exist
                tokens = limit - 1
                last_refill = now
                reset_time = now + window

                # Store new bucket state
                await self.redis.client.hset(
                    key,
                    mapping={
                        "tokens": str(tokens),
                        "last_refill": str(last_refill),
                        "reset_time": str(reset_time)
                    }
                )
                await self.redis.client.expire(key, window)

                return True, tokens, reset_time, limit

            # Parse bucket state
            tokens = int(bucket.get("tokens", 0))
            last_refill = int(bucket.get("last_refill", now))
            reset_time = int(bucket.get("reset_time", now + window))

            # Check if we need to refill tokens (new window)
            if now >= reset_time:
                tokens = limit - 1
                last_refill = now
                reset_time = now + window

                await self.redis.client.hset(
                    key,
                    mapping={
                        "tokens": str(tokens),
                        "last_refill": str(last_refill),
                        "reset_time": str(reset_time)
                    }
                )
                await self.redis.client.expire(key, window)

                return True, tokens, reset_time, limit

            # Check if we have tokens available
            if tokens > 0:
                tokens -= 1
                await self.redis.client.hset(key, "tokens", str(tokens))
                return True, tokens, reset_time, limit

            # Rate limit exceeded
            return False, 0, reset_time, limit

        except Exception as e:
            logger.error(f"Rate limit check failed for {identifier}: {e}")
            # On error, allow the request (fail open)
            return True, limit - 1, now + window, limit

    async def __call__(self, request: Request, call_next: Callable) -> Response:
        """
        Middleware function to check rate limits for incoming requests.

        Args:
            request: FastAPI request object
            call_next: Next middleware/route handler in the chain

        Returns:
            Response with rate limit headers

        Raises:
            HTTPException: 429 Too Many Requests if rate limit exceeded
        """
        # Bypass rate limiting for health check and docs endpoints
        if request.url.path in self.BYPASS_PATHS:
            return await call_next(request)

        # Get user role and ID from JWT token
        user_role, user_id = await self._get_user_info(request)
        identifier = await self._get_client_identifier(request, user_id)
        limit = self.RATE_LIMITS[user_role]

        # Check rate limit
        allowed, remaining, reset_time, limit_value = await self.check_rate_limit(
            identifier, limit
        )

        # Add rate limit headers
        headers = {
            "X-RateLimit-Limit": str(limit_value),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_time),
        }

        if not allowed:
            # Calculate retry-after in seconds
            retry_after = reset_time - int(time.time())
            headers["Retry-After"] = str(retry_after)

            logger.warning(
                f"Rate limit exceeded for {identifier} "
                f"(role: {user_role.value}, path: {request.url.path})"
            )

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Too Many Requests",
                    "message": f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    "retry_after": retry_after
                },
                headers=headers
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to successful response
        for key, value in headers.items():
            response.headers[key] = value

        return response


# Create rate limiter instance
rate_limiter = RateLimiter()
