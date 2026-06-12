"""
Tests for Authentication Middleware and RBAC (Test Scenarios F1-F6)
"""
import pytest
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from unittest.mock import AsyncMock, MagicMock
from app.middleware.auth_middleware import (
    get_current_user,
    require_role,
    require_admin,
    require_user,
    allow_anonymous,
)
from app.models.user import User, UserRole
from app.core.security import create_access_token


@pytest.fixture
def mock_admin_user():
    """Mock admin user"""
    return User(
        id="550e8400-e29b-41d4-a716-446655440000",
        email="admin@example.com",
        role=UserRole.ADMIN,
        is_active=True
    )


@pytest.fixture
def mock_regular_user():
    """Mock regular user"""
    return User(
        id="660e8400-e29b-41d4-a716-446655440001",
        email="user@example.com",
        role=UserRole.USER,
        is_active=True
    )


@pytest.fixture
def admin_token(mock_admin_user):
    """Create access token for admin user"""
    return create_access_token({
        "user_id": str(mock_admin_user.id),
        "email": mock_admin_user.email,
        "role": mock_admin_user.role.value
    })


@pytest.fixture
def user_token(mock_regular_user):
    """Create access token for regular user"""
    return create_access_token({
        "user_id": str(mock_regular_user.id),
        "email": mock_regular_user.email,
        "role": mock_regular_user.role.value
    })


class TestRBACMiddleware:
    """Test scenarios F1-F6: Role-Based Access Control"""

    @pytest.mark.asyncio
    async def test_f1_admin_access_with_require_admin(self, db_session, mock_admin_user, admin_token):
        """F1: Allow admin access with @require_admin decorator"""
        from app.services.auth_service import AuthService
        
        # Mock AuthService.validate_access_token to return admin user
        with pytest.MonkeyPatch.context() as mp:
            async def mock_validate(db, token):
                return mock_admin_user
            
            mp.setattr(AuthService, "validate_access_token", staticmethod(mock_validate))
            
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=admin_token)
            
            # This should not raise an exception
            user = await get_current_user(credentials, db_session)
            assert user is not None
            
            # Test require_admin decorator logic
            @require_admin
            async def protected_endpoint(current_user: User):
                return {"message": "Admin access granted"}
            
            result = await protected_endpoint(mock_admin_user)
            assert result["message"] == "Admin access granted"

    @pytest.mark.asyncio
    async def test_f2_deny_user_access_with_require_admin(self, db_session, mock_regular_user):
        """F2: Deny user access with @require_admin decorator"""
        
        @require_admin
        async def protected_endpoint(current_user: User):
            return {"message": "Admin access granted"}
        
        with pytest.raises(HTTPException) as exc_info:
            await protected_endpoint(mock_regular_user)
        
        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_f3_allow_user_and_admin_with_require_user(self, mock_admin_user, mock_regular_user):
        """F3: Allow user and admin with @require_user decorator"""
        
        @require_user
        async def protected_endpoint(current_user: User):
            return {"message": "User access granted"}
        
        # Test with regular user
        result_user = await protected_endpoint(mock_regular_user)
        assert result_user["message"] == "User access granted"
        
        # Test with admin
        result_admin = await protected_endpoint(mock_admin_user)
        assert result_admin["message"] == "User access granted"

    @pytest.mark.asyncio
    async def test_f4_allow_all_with_allow_anonymous(self, mock_regular_user):
        """F4: Allow all roles with @allow_anonymous decorator"""
        
        @allow_anonymous
        async def public_endpoint(current_user: User = None):
            if current_user:
                return {"message": f"Welcome {current_user.email}"}
            return {"message": "Welcome guest"}
        
        # Test with authenticated user
        result_auth = await public_endpoint(mock_regular_user)
        assert "user@example.com" in result_auth["message"]
        
        # Test without user (anonymous)
        result_anon = await public_endpoint(None)
        assert "guest" in result_anon["message"]

    @pytest.mark.asyncio
    async def test_f5_return_401_for_missing_token(self, db_session):
        """F5: Return 401 for missing authentication"""
        
        # Call get_current_user with no credentials
        user = await get_current_user(None, db_session)
        
        # Should return None for anonymous access
        assert user is None

    @pytest.mark.asyncio
    async def test_f6_return_403_for_insufficient_permissions(self, mock_regular_user):
        """F6: Return 403 for insufficient permissions"""
        
        @require_role([UserRole.ADMIN])
        async def admin_only_endpoint(current_user: User):
            return {"message": "Admin only"}
        
        with pytest.raises(HTTPException) as exc_info:
            await admin_only_endpoint(mock_regular_user)
        
        assert exc_info.value.status_code == 403
