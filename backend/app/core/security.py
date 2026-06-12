"""
Security utilities for authentication and authorization
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings
from app.core.logging import logger

# Password hashing context with configured bcrypt rounds
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.BCRYPT_ROUNDS
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt with configured salt rounds.

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    return pwd_context.hash(password)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    algorithm: Optional[str] = None
) -> str:
    """
    Create a JWT access token with proper claims.

    Args:
        data: Dictionary containing token claims (should include user_id, email, role)
        expires_delta: Optional custom expiration timedelta
        algorithm: Optional algorithm override (default: HS256)

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()

    # Set expiration time
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    # Set issued at time
    iat = datetime.utcnow()

    # Update token with standard claims
    to_encode.update({
        "exp": expire,
        "iat": iat,
        "type": "access"
    })

    # Use specified algorithm or default from settings
    algo = algorithm or settings.ALGORITHM

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=algo)
    logger.debug(f"Created access token for user: {data.get('email', 'unknown')}")
    return encoded_jwt


def create_refresh_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    algorithm: Optional[str] = None
) -> str:
    """
    Create a JWT refresh token with extended expiry.

    Args:
        data: Dictionary containing token claims (should include user_id)
        expires_delta: Optional custom expiration timedelta
        algorithm: Optional algorithm override (default: HS256)

    Returns:
        Encoded JWT refresh token string
    """
    to_encode = data.copy()

    # Set expiration time
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    # Set issued at time
    iat = datetime.utcnow()

    # Update token with standard claims
    to_encode.update({
        "exp": expire,
        "iat": iat,
        "type": "refresh"
    })

    # Use specified algorithm or default from settings
    algo = algorithm or settings.ALGORITHM

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=algo)
    logger.debug(f"Created refresh token for user: {data.get('user_id', 'unknown')}")
    return encoded_jwt


def verify_token(token: str, expected_type: str = "access") -> Optional[Dict[str, Any]]:
    """
    Verify and decode a JWT token with type validation.

    Args:
        token: JWT token string
        expected_type: Expected token type ('access' or 'refresh')

    Returns:
        Decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        # Validate token type
        token_type = payload.get("type")
        if token_type != expected_type:
            logger.warning(f"Token type mismatch: expected {expected_type}, got {token_type}")
            return None

        return payload
    except JWTError as e:
        logger.warning(f"Token verification failed: {e}")
        return None


def decode_token_unsafe(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode a JWT token without verification (for inspection only).

    Args:
        token: JWT token string

    Returns:
        Decoded token payload or None if invalid format
    """
    try:
        # Decode without verification
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM], options={"verify_signature": False})
        return payload
    except JWTError as e:
        logger.warning(f"Token decoding failed: {e}")
        return None
