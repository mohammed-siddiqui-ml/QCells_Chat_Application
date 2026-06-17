"""
Authentication API endpoints for OAuth2 login, logout, token refresh, and user info.

This module provides:
- POST /login - Initiate OAuth2 login flow
- GET /callback - Handle OAuth2 callback and issue JWT tokens
- POST /logout - Invalidate refresh token
- POST /refresh - Refresh access token
- GET /me - Get current user information
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_db
from app.middleware.auth_middleware import get_current_user
from app.models import User, UserRole
from app.schemas.auth import (
    OAuth2LoginResponse,
    TokenResponse,
    RefreshTokenRequest,
    UserInfo,
)
from app.services.auth_service import AuthService, OAuth2Service, AuthenticationError


router = APIRouter()


@router.post(
    "/login",
    response_model=OAuth2LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Initiate OAuth2 login flow",
    description="Generate OAuth2 authorization URL for Google login. Returns redirect URL and state token.",
)
async def login() -> OAuth2LoginResponse:
    """
    Initiate OAuth2 login flow with Google.
    
    Returns:
        OAuth2LoginResponse: Contains authorization URL and CSRF state token
        
    Example:
        POST /api/v1/auth/login
        Response:
        {
            "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
            "state": "random-state-token"
        }
    """
    try:
        oauth2_service = OAuth2Service()
        authorization_url, state = await oauth2_service.get_authorization_url()
        
        logger.info("OAuth2 login initiated successfully")
        return OAuth2LoginResponse(
            authorization_url=authorization_url,
            state=state
        )
    except Exception as e:
        logger.error(f"Failed to initiate OAuth2 login: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate OAuth2 login flow"
        )


@router.get(
    "/callback",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Handle OAuth2 callback",
    description="Process OAuth2 callback, exchange code for tokens, create/retrieve user, and issue JWT tokens.",
)
async def oauth_callback(
    code: str = Query(..., description="Authorization code from OAuth2 provider"),
    state: Optional[str] = Query(None, description="CSRF state token"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Handle OAuth2 callback and issue JWT tokens.
    
    Args:
        code: Authorization code from OAuth2 provider
        state: CSRF state token for validation
        request: FastAPI request object
        db: Database session
        
    Returns:
        TokenResponse: Contains access_token, refresh_token, token_type, and expires_in
        
    Raises:
        HTTPException: 400 if code is missing, 401 if OAuth2 exchange fails
        
    Example:
        GET /api/v1/auth/callback?code=AUTH_CODE&state=STATE_TOKEN
        Response:
        {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "bearer",
            "expires_in": 900
        }
    """
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code is required"
        )
    
    try:
        # Initialize services
        oauth2_service = OAuth2Service()
        auth_service = AuthService(db)
        
        # Exchange code for OAuth2 token
        token_response = await oauth2_service.exchange_code_for_token(code)
        
        # Get user info from OAuth2 provider
        user_info = await oauth2_service.get_user_info(token_response["access_token"])
        email = user_info.get("email")
        
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to retrieve email from OAuth2 provider"
            )
        
        # Get or create user
        user = await auth_service.get_user_by_email(email)
        if not user:
            # Create new user with ADMIN role (as per task requirements for admin authentication)
            user = await auth_service.create_user_from_oauth(email, role=UserRole.ADMIN)
            logger.info(f"Created new admin user from OAuth2: {email}")
        else:
            # Update last login
            from datetime import datetime
            user.last_login = datetime.utcnow()
            await db.commit()
            logger.info(f"Existing user logged in via OAuth2: {email}")

        # Extract client info for token metadata
        user_agent = request.headers.get("user-agent") if request else None
        ip_address = request.client.host if request and request.client else None

        # Create JWT tokens
        access_token, refresh_token = await auth_service.create_tokens(
            user,
            user_agent=user_agent,
            ip_address=ip_address
        )

        logger.info(f"OAuth2 callback successful for user: {email}")
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth2 callback failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OAuth2 authentication failed"
        )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout and invalidate refresh token",
    description="Invalidate refresh token by adding it to Redis blacklist and marking as revoked in database.",
)
async def logout(
    refresh_request: RefreshTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Logout user and invalidate refresh token.

    Args:
        refresh_request: Request containing refresh token to revoke
        current_user: Current authenticated user
        db: Database session

    Returns:
        JSONResponse: Success message

    Raises:
        HTTPException: 401 if not authenticated, 403 if forbidden

    Example:
        POST /api/v1/auth/logout
        Headers: Authorization: Bearer <access_token>
        Body:
        {
            "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        }
        Response:
        {
            "message": "Logged out successfully"
        }
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    try:
        auth_service = AuthService(db)

        # Revoke refresh token (marks as revoked in database)
        revoked = await auth_service.revoke_refresh_token(refresh_request.refresh_token)

        # Also blacklist the refresh token in Redis for immediate invalidation
        await auth_service.blacklist_token(refresh_request.refresh_token)

        if revoked:
            logger.info(f"User logged out successfully: {current_user.email}")
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"message": "Logged out successfully"}
            )
        else:
            logger.warning(f"Logout attempted with invalid token: {current_user.email}")
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"message": "Logged out successfully"}
            )

    except Exception as e:
        logger.error(f"Logout failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description="Exchange refresh token for new access and refresh tokens (token rotation).",
)
async def refresh_token(
    refresh_request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Refresh access token using refresh token.

    Implements token rotation: old refresh token is revoked and new one is issued.

    Args:
        refresh_request: Request containing refresh token
        db: Database session

    Returns:
        TokenResponse: New access and refresh tokens

    Raises:
        HTTPException: 401 if refresh token is invalid or revoked, 422 if validation fails

    Example:
        POST /api/v1/auth/refresh
        Body:
        {
            "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        }
        Response:
        {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "bearer",
            "expires_in": 900
        }
    """
    try:
        auth_service = AuthService(db)

        # Refresh tokens (implements token rotation)
        access_token, new_refresh_token = await auth_service.refresh_access_token(
            refresh_request.refresh_token
        )

        logger.info("Access token refreshed successfully")
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

    except AuthenticationError as e:
        logger.warning(f"Token refresh failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Token refresh error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )


@router.get(
    "/me",
    response_model=UserInfo,
    status_code=status.HTTP_200_OK,
    summary="Get current user information",
    description="Retrieve current authenticated user profile information.",
)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
) -> UserInfo:
    """
    Get current user profile information.

    Requires valid access token in Authorization header.

    Args:
        current_user: Current authenticated user from JWT token

    Returns:
        UserInfo: User profile information

    Raises:
        HTTPException: 401 if not authenticated or token invalid

    Example:
        GET /api/v1/auth/me
        Headers: Authorization: Bearer <access_token>
        Response:
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "email": "admin@example.com",
            "role": "admin",
            "is_active": true,
            "created_at": "2024-01-01T00:00:00Z",
            "last_login": "2024-01-15T10:30:00Z"
        }
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info(f"User info requested: {current_user.email}")
    return UserInfo(
        id=str(current_user.id),
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        last_login=current_user.last_login,
    )

