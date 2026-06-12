"""
Authentication and authorization middleware for JWT validation and RBAC.

This module provides:
- JWT token validation middleware
- @require_role decorator for role-based access control
- Current user extraction from request
"""
from functools import wraps
from typing import Optional, List, Callable
from fastapi import HTTPException, Request, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.logging import logger
from app.core.security import verify_token
from app.db.session import get_db
from app.models import User, UserRole
from app.services.auth_service import AuthService
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


# HTTP Bearer security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Extract and validate current user from JWT token.
    
    Args:
        credentials: HTTP Authorization credentials
        db: Database session
        
    Returns:
        User object if authenticated, None for anonymous
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    if not credentials:
        # Allow anonymous access
        return None
    
    token = credentials.credentials
    
    # Validate token using auth service
    auth_service = AuthService(db)
    payload = await auth_service.validate_access_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract user_id from payload
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    
    logger.debug(f"Authenticated user: {user.email} (role: {user.role.value})")
    return user


async def get_current_active_user(
    current_user: Optional[User] = Depends(get_current_user)
) -> User:
    """
    Require an authenticated active user (no anonymous access).
    
    Args:
        current_user: Current user from token
        
    Returns:
        User object
        
    Raises:
        HTTPException: If user is not authenticated
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return current_user


def require_role(allowed_roles: List[UserRole]) -> Callable:
    """
    Decorator factory for role-based access control.
    
    Usage:
        @router.get("/admin/dashboard")
        @require_role([UserRole.ADMIN])
        async def admin_dashboard(current_user: User = Depends(get_current_active_user)):
            ...
    
    Args:
        allowed_roles: List of allowed user roles
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user from kwargs (injected by dependency)
            current_user = kwargs.get('current_user')
            
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Check if user role is in allowed roles
            if current_user.role not in allowed_roles:
                logger.warning(
                    f"Access denied for user {current_user.email}: "
                    f"role {current_user.role.value} not in {[r.value for r in allowed_roles]}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Required roles: {[r.value for r in allowed_roles]}",
                )
            
            # User has required role, proceed with function
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


# Convenience decorators for common roles
def require_admin(func: Callable) -> Callable:
    """Decorator requiring admin role"""
    return require_role([UserRole.ADMIN])(func)


def require_user(func: Callable) -> Callable:
    """Decorator requiring user or admin role"""
    return require_role([UserRole.USER, UserRole.ADMIN])(func)


def allow_anonymous(func: Callable) -> Callable:
    """Decorator allowing anonymous access (all roles including anonymous)"""
    return require_role([UserRole.ANONYMOUS, UserRole.USER, UserRole.ADMIN])(func)
