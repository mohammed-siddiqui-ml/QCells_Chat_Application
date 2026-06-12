"""
Authentication service for OAuth2 integration, JWT token management, and user session handling.

This module provides:
- OAuth2 integration with Google and Azure AD providers using authlib
- JWT token generation and validation (access and refresh tokens)
- Password hashing using bcrypt with 12 salt rounds
- Token revocation and refresh token rotation
- User session management
"""
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlencode

from authlib.integrations.httpx_client import AsyncOAuth2Client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
)
from app.models import User, UserRole, RefreshToken
from app.utils.redis_client import redis_client


class AuthenticationError(Exception):
    """Base exception for authentication errors"""
    pass


class OAuth2Service:
    """Service for OAuth2 authentication with multiple providers"""

    def __init__(self):
        self.provider = settings.OAUTH2_PROVIDER
        self.client_id = settings.OAUTH2_CLIENT_ID
        self.client_secret = settings.OAUTH2_CLIENT_SECRET
        self.redirect_uri = settings.OAUTH2_REDIRECT_URI
        self.scopes = settings.OAUTH2_SCOPES.split()

        # Provider-specific endpoints
        self.authorization_endpoint = settings.OAUTH2_AUTHORIZATION_ENDPOINT
        self.token_endpoint = settings.OAUTH2_TOKEN_ENDPOINT
        self.userinfo_endpoint = settings.OAUTH2_USERINFO_ENDPOINT

    async def get_authorization_url(self, state: Optional[str] = None) -> Tuple[str, str]:
        """
        Generate OAuth2 authorization URL for redirecting users.

        Args:
            state: Optional CSRF state token (generated if not provided)

        Returns:
            Tuple of (authorization_url, state)
        """
        if not state:
            state = secrets.token_urlsafe(32)

        client = AsyncOAuth2Client(
            client_id=self.client_id,
            redirect_uri=self.redirect_uri,
            scope=" ".join(self.scopes),
        )

        authorization_url, _ = client.create_authorization_url(
            self.authorization_endpoint,
            state=state,
        )

        logger.info(f"Generated OAuth2 authorization URL for provider: {self.provider}")
        return authorization_url, state

    async def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth2 callback

        Returns:
            Token response dictionary
        """
        client = AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
        )

        token = await client.fetch_token(
            self.token_endpoint,
            code=code,
            grant_type="authorization_code",
        )

        logger.info(f"Successfully exchanged code for token with provider: {self.provider}")
        return token

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Fetch user information from OAuth2 provider.

        Args:
            access_token: OAuth2 access token

        Returns:
            User information dictionary
        """
        client = AsyncOAuth2Client(token={"access_token": access_token})

        response = await client.get(self.userinfo_endpoint)
        response.raise_for_status()

        user_info = response.json()
        logger.info(f"Retrieved user info for: {user_info.get('email', 'unknown')}")
        return user_info


class AuthService:
    """Main authentication service handling JWT tokens and user management"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.oauth2_service = OAuth2Service()

    async def create_user_from_oauth(
        self,
        email: str,
        role: UserRole = UserRole.USER
    ) -> User:
        """
        Create a new user from OAuth2 login.

        Args:
            email: User email from OAuth2 provider
            role: User role (default: USER)

        Returns:
            Created User object
        """
        user = User(
            email=email,
            role=role,
            is_active=True,
            last_login=datetime.utcnow()
        )

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"Created new user from OAuth2: {email}")
        return user

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Retrieve user by email address.

        Args:
            email: User email

        Returns:
            User object or None if not found
        """
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """
        Authenticate user with email and password.

        Args:
            email: User email
            password: Plain text password

        Returns:
            User object if authentication successful, None otherwise
        """
        user = await self.get_user_by_email(email)

        if not user:
            logger.warning(f"Authentication failed: user not found - {email}")
            return None

        if not user.password_hash:
            logger.warning(f"Authentication failed: no password set - {email}")
            return None

        if not verify_password(password, user.password_hash):
            logger.warning(f"Authentication failed: invalid password - {email}")
            return None

        if not user.is_active:
            logger.warning(f"Authentication failed: user inactive - {email}")
            return None

        # Update last login
        user.last_login = datetime.utcnow()
        await self.db.commit()

        logger.info(f"User authenticated successfully: {email}")
        return user

    async def create_tokens(
        self,
        user: User,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Create access and refresh tokens for a user.

        Args:
            user: User object
            user_agent: Client user agent string
            ip_address: Client IP address

        Returns:
            Tuple of (access_token, refresh_token)
        """
        # Create access token with user claims
        access_token_data = {
            "user_id": str(user.id),
            "email": user.email,
            "role": user.role.value,
        }
        access_token = create_access_token(access_token_data)

        # Create refresh token with minimal claims
        refresh_token_data = {
            "user_id": str(user.id),
        }
        refresh_token = create_refresh_token(refresh_token_data)

        # Store refresh token in database for rotation and revocation
        token_hash = self._hash_token(refresh_token)
        expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        db_refresh_token = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        self.db.add(db_refresh_token)
        await self.db.commit()

        logger.info(f"Created tokens for user: {user.email}")
        return access_token, refresh_token

    async def refresh_access_token(self, refresh_token: str) -> Tuple[str, str]:
        """
        Refresh access token using refresh token (with token rotation).

        Args:
            refresh_token: Current refresh token

        Returns:
            Tuple of (new_access_token, new_refresh_token)

        Raises:
            AuthenticationError: If refresh token is invalid or revoked
        """
        # Verify refresh token
        payload = verify_token(refresh_token, expected_type="refresh")
        if not payload:
            raise AuthenticationError("Invalid refresh token")

        user_id = payload.get("user_id")
        if not user_id:
            raise AuthenticationError("Invalid token payload")

        # Check if token exists in database and is not revoked
        token_hash = self._hash_token(refresh_token)
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.is_revoked == False
            )
        )
        db_token = result.scalar_one_or_none()

        if not db_token:
            raise AuthenticationError("Refresh token not found or revoked")

        if not db_token.is_valid():
            raise AuthenticationError("Refresh token expired")

        # Get user
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise AuthenticationError("User not found or inactive")

        # Revoke old refresh token
        db_token.is_revoked = True
        db_token.revoked_at = datetime.utcnow()

        # Create new tokens (rotation)
        access_token, new_refresh_token = await self.create_tokens(
            user,
            user_agent=db_token.user_agent,
            ip_address=db_token.ip_address
        )

        await self.db.commit()

        logger.info(f"Refreshed tokens for user: {user.email}")
        return access_token, new_refresh_token

    async def revoke_refresh_token(self, refresh_token: str) -> bool:
        """
        Revoke a specific refresh token.

        Args:
            refresh_token: Refresh token to revoke

        Returns:
            True if token was revoked, False if not found
        """
        token_hash = self._hash_token(refresh_token)

        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        db_token = result.scalar_one_or_none()

        if not db_token:
            logger.warning("Attempted to revoke non-existent token")
            return False

        db_token.is_revoked = True
        db_token.revoked_at = datetime.utcnow()
        await self.db.commit()

        logger.info(f"Revoked refresh token for user_id: {db_token.user_id}")
        return True

    async def revoke_all_user_tokens(self, user_id: str) -> int:
        """
        Revoke all refresh tokens for a user (e.g., on password change).

        Args:
            user_id: User UUID string

        Returns:
            Number of tokens revoked
        """
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.is_revoked == False
            )
        )
        tokens = result.scalars().all()

        count = 0
        for token in tokens:
            token.is_revoked = True
            token.revoked_at = datetime.utcnow()
            count += 1

        await self.db.commit()

        logger.info(f"Revoked {count} tokens for user_id: {user_id}")
        return count

    async def validate_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Validate access token and check for revocation.

        Args:
            token: Access token to validate

        Returns:
            Token payload if valid, None otherwise
        """
        # Verify JWT signature and expiration
        payload = verify_token(token, expected_type="access")
        if not payload:
            return None

        user_id = payload.get("user_id")
        if not user_id:
            return None

        # Check if user is still active
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            logger.warning(f"Token validation failed: user inactive - {user_id}")
            return None

        # Check token blacklist in Redis (for immediate revocation)
        is_blacklisted = await self._is_token_blacklisted(token)
        if is_blacklisted:
            logger.warning(f"Token validation failed: token blacklisted - {user_id}")
            return None

        return payload

    async def blacklist_token(self, token: str, ttl: Optional[int] = None) -> bool:
        """
        Add token to Redis blacklist for immediate revocation.

        Args:
            token: Token to blacklist
            ttl: Time-to-live in seconds (default: remaining token lifetime)

        Returns:
            True if successful
        """
        if not ttl:
            # Calculate remaining token lifetime
            payload = verify_token(token)
            if payload:
                exp = payload.get("exp", 0)
                ttl = max(0, exp - int(datetime.utcnow().timestamp()))
            else:
                ttl = 900  # Default 15 minutes

        token_hash = self._hash_token(token)
        key = f"blacklist:{token_hash}"

        await redis_client.client.setex(key, ttl, "1")
        logger.info("Token added to blacklist")
        return True

    async def _is_token_blacklisted(self, token: str) -> bool:
        """
        Check if token is in Redis blacklist.

        Args:
            token: Token to check

        Returns:
            True if blacklisted, False otherwise
        """
        token_hash = self._hash_token(token)
        key = f"blacklist:{token_hash}"

        result = await redis_client.client.exists(key)
        return result > 0

    @staticmethod
    def _hash_token(token: str) -> str:
        """
        Hash token for storage (prevents token leakage in database).

        Args:
            token: JWT token string

        Returns:
            SHA-256 hash of token
        """
        return hashlib.sha256(token.encode()).hexdigest()

    async def set_user_password(self, user_id: str, password: str) -> bool:
        """
        Set or update user password.

        Args:
            user_id: User UUID string
            password: Plain text password

        Returns:
            True if successful
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise AuthenticationError(f"User not found: {user_id}")

        user.password_hash = get_password_hash(password)
        await self.db.commit()

        # Revoke all existing tokens for security
        await self.revoke_all_user_tokens(user_id)

        logger.info(f"Password updated for user: {user.email}")
        return True

