"""
Comprehensive tests for Admin Authentication API Endpoints

Tests all 5 endpoints with happy path, error cases, and edge cases:
- POST /api/v1/auth/login
- GET /api/v1/auth/callback
- POST /api/v1/auth/refresh
- POST /api/v1/auth/logout
- GET /api/v1/auth/me
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager

# ⚠️ CRITICAL: Mock the lifespan manager BEFORE importing app
# This prevents the app from trying to connect to Redis, Elasticsearch, MinIO during tests
@asynccontextmanager
async def mock_lifespan(app: FastAPI):
    """Mock lifespan that does nothing - prevents external service connections during tests"""
    yield

# Import the app module and patch the lifespan
import sys
import app.main
app.main.lifespan = mock_lifespan

from app.main import app
from app.models import User, UserRole, RefreshToken
from app.core.security import create_access_token, create_refresh_token
from app.db.session import get_db
import hashlib


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """Create async HTTP client for API testing with database override"""
    # Override the get_db dependency to use test database
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    # Clear overrides after test
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession):
    """Create an admin user for testing"""
    user = User(
        email="admin@example.com",
        password_hash="dummy_hash",
        role=UserRole.ADMIN,
        is_active=True,
        last_login=None
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def inactive_user(db_session: AsyncSession):
    """Create an inactive user for testing"""
    user = User(
        email="inactive@example.com",
        password_hash="dummy_hash",
        role=UserRole.ADMIN,
        is_active=False
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def mock_oauth2_service():
    """Mock OAuth2Service for testing without external dependencies"""
    with patch("app.api.routes.auth.OAuth2Service") as mock:
        instance = MagicMock()
        mock.return_value = instance
        
        # Default successful responses
        instance.get_authorization_url = AsyncMock(return_value=(
            "https://accounts.google.com/o/oauth2/v2/auth?client_id=test&scope=openid+email",
            "random_state_token_32_characters_long"
        ))
        
        instance.exchange_code_for_token = AsyncMock(return_value={
            "access_token": "ya29.mock_oauth_access_token",
            "token_type": "Bearer",
            "expires_in": 3600
        })
        
        instance.get_user_info = AsyncMock(return_value={
            "email": "newuser@oauth.com",
            "verified_email": True
        })
        
        yield instance


@pytest.fixture
def mock_redis():
    """Mock Redis client for token blacklisting"""
    # Patch BOTH the original module AND where it's imported in auth_service
    # This is necessary because auth_service imports redis_client at module level,
    # binding the name before the test fixture runs
    with patch("app.utils.redis_client.redis_client") as mock1, \
         patch("app.services.auth_service.redis_client") as mock2:
        # Create a mock client attribute with async methods
        mock1.client = MagicMock()
        mock1.client.exists = AsyncMock(return_value=0)  # Token not blacklisted by default
        mock1.client.setex = AsyncMock(return_value=True)
        mock1.client.get = AsyncMock(return_value=None)

        # Make mock2 (auth_service import) identical to mock1
        mock2.client = mock1.client

        yield mock1


@pytest_asyncio.fixture
async def valid_access_token(admin_user: User):
    """Generate valid access token for testing"""
    return create_access_token(
        data={
            "user_id": str(admin_user.id),
            "email": admin_user.email,
            "role": admin_user.role.value
        }
    )


@pytest_asyncio.fixture
async def valid_refresh_token_obj(db_session: AsyncSession, admin_user: User):
    """Create valid refresh token in database"""
    token_str = create_refresh_token(
        data={
            "user_id": str(admin_user.id),
            "email": admin_user.email,
            "role": admin_user.role.value
        }
    )

    # Hash the token for storage (RefreshToken model stores token_hash, not token)
    token_hash = hashlib.sha256(token_str.encode()).hexdigest()

    refresh_token = RefreshToken(
        user_id=admin_user.id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(days=7),
        is_revoked=False
    )
    db_session.add(refresh_token)
    await db_session.commit()
    await db_session.refresh(refresh_token)

    # Attach the plain token string as an attribute for test usage
    refresh_token.token = token_str

    return refresh_token


# ============================================================================
# TEST GROUP A: POST /api/v1/auth/login
# ============================================================================

@pytest.mark.asyncio
async def test_login_generates_authorization_url(client: AsyncClient, mock_oauth2_service):
    """TC-A01: Generate Authorization URL"""
    response = await client.post("/api/v1/auth/login")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "authorization_url" in data
    assert "state" in data
    assert data["authorization_url"].startswith("https://accounts.google.com")
    assert len(data["state"]) >= 32
    
    mock_oauth2_service.get_authorization_url.assert_called_once()


@pytest.mark.asyncio
async def test_login_service_failure(client: AsyncClient, mock_oauth2_service):
    """TC-A02: Login Service Failure"""
    mock_oauth2_service.get_authorization_url.side_effect = Exception("OAuth2 service unavailable")

    response = await client.post("/api/v1/auth/login")

    assert response.status_code == 500
    # Custom error handler returns {"error": {"message": ...}} format
    assert "Failed to initiate OAuth2 login flow" in response.json()["error"]["message"]


# ============================================================================
# TEST GROUP B: GET /api/v1/auth/callback
# ============================================================================

@pytest.mark.asyncio
async def test_callback_new_user_registration(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_oauth2_service,
    mock_redis
):
    """TC-B01: New User Registration via OAuth2"""
    # Ensure no user exists
    response = await client.get(
        "/api/v1/auth/callback",
        params={"code": "valid_auth_code_12345", "state": "valid_state"}
    )

    assert response.status_code == 200
    data = response.json()

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 900  # 15 minutes

    # Verify user was created
    from sqlalchemy import select
    result = await db_session.execute(select(User).where(User.email == "newuser@oauth.com"))
    user = result.scalar_one_or_none()

    assert user is not None
    assert user.email == "newuser@oauth.com"
    assert user.role == UserRole.ADMIN
    assert user.is_active is True


@pytest.mark.asyncio
async def test_callback_existing_user_login(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    mock_oauth2_service,
    mock_redis
):
    """TC-B02: Existing User Login"""
    # Mock to return existing user's email
    mock_oauth2_service.get_user_info.return_value = {
        "email": "admin@example.com",
        "verified_email": True
    }

    # Record original last_login
    original_last_login = admin_user.last_login

    response = await client.get(
        "/api/v1/auth/callback",
        params={"code": "valid_code"}
    )

    assert response.status_code == 200
    data = response.json()

    assert "access_token" in data
    assert "refresh_token" in data

    # Verify last_login was updated
    await db_session.refresh(admin_user)
    assert admin_user.last_login is not None
    if original_last_login:
        assert admin_user.last_login > original_last_login


@pytest.mark.asyncio
async def test_callback_missing_code(client: AsyncClient, mock_oauth2_service):
    """TC-B03: Missing Authorization Code"""
    response = await client.get("/api/v1/auth/callback")

    assert response.status_code == 422  # FastAPI validation error


@pytest.mark.asyncio
async def test_callback_oauth_token_exchange_failure(
    client: AsyncClient,
    mock_oauth2_service
):
    """TC-B04: OAuth2 Token Exchange Failure"""
    mock_oauth2_service.exchange_code_for_token.side_effect = Exception("Invalid authorization code")

    response = await client.get(
        "/api/v1/auth/callback",
        params={"code": "invalid_code"}
    )

    assert response.status_code == 401
    # Custom error handler returns {"error": {"message": ...}} format
    assert "OAuth2 authentication failed" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_callback_userinfo_retrieval_failure(
    client: AsyncClient,
    mock_oauth2_service
):
    """TC-B05: Userinfo Retrieval Failure"""
    mock_oauth2_service.get_user_info.return_value = {
        "verified_email": True
        # Missing 'email' field
    }

    response = await client.get(
        "/api/v1/auth/callback",
        params={"code": "valid_code"}
    )

    assert response.status_code == 401
    # Custom error handler returns {"error": {"message": ...}} format
    assert "Failed to retrieve email" in response.json()["error"]["message"]


# ============================================================================
# TEST GROUP C: POST /api/v1/auth/refresh
# ============================================================================

@pytest.mark.asyncio
async def test_refresh_valid_token(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    valid_refresh_token_obj: RefreshToken,
    mock_redis
):
    """TC-C01: Valid Token Refresh with Rotation"""
    old_token = valid_refresh_token_obj.token

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_token}
    )

    assert response.status_code == 200
    data = response.json()

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["refresh_token"] != old_token  # Token rotation

    # Verify old token was revoked
    await db_session.refresh(valid_refresh_token_obj)
    assert valid_refresh_token_obj.is_revoked is True


@pytest.mark.asyncio
async def test_refresh_expired_token(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    mock_redis
):
    """TC-C02: Expired Refresh Token"""
    # Create expired refresh token
    expired_token_str = create_refresh_token(
        data={
            "user_id": str(admin_user.id),
            "email": admin_user.email,
            "role": admin_user.role.value
        },
        expires_delta=timedelta(days=-1)  # Expired
    )

    # Hash the token for storage
    token_hash = hashlib.sha256(expired_token_str.encode()).hexdigest()

    refresh_token = RefreshToken(
        user_id=admin_user.id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(days=7),  # Use future expiry since token itself is expired
        is_revoked=False
    )
    db_session.add(refresh_token)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": expired_token_str}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_revoked_token(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    valid_refresh_token_obj: RefreshToken,
    mock_redis
):
    """TC-C03: Revoked Refresh Token"""
    # Revoke the token
    valid_refresh_token_obj.is_revoked = True
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": valid_refresh_token_obj.token}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_invalid_token_signature(client: AsyncClient, mock_redis):
    """TC-C04: Invalid Token Signature"""
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid.jwt.token"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_not_in_database(
    client: AsyncClient,
    admin_user: User,
    mock_redis
):
    """TC-C05: Token Not Found in Database"""
    # Create valid JWT but don't store in database
    valid_jwt = create_refresh_token(
        data={
            "user_id": str(admin_user.id),
            "email": admin_user.email,
            "role": admin_user.role.value
        }
    )

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": valid_jwt}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_inactive_user(
    client: AsyncClient,
    db_session: AsyncSession,
    inactive_user: User,
    mock_redis
):
    """TC-C06: Inactive User Account"""
    # Create refresh token for inactive user
    token_str = create_refresh_token(
        data={
            "user_id": str(inactive_user.id),
            "email": inactive_user.email,
            "role": inactive_user.role.value
        }
    )

    # Hash the token for storage
    token_hash = hashlib.sha256(token_str.encode()).hexdigest()

    refresh_token = RefreshToken(
        user_id=inactive_user.id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(days=7),
        is_revoked=False
    )
    db_session.add(refresh_token)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token_str}
    )

    assert response.status_code == 401


# ============================================================================
# TEST GROUP D: POST /api/v1/auth/logout
# ============================================================================

@pytest.mark.asyncio
async def test_logout_successful(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    valid_access_token: str,
    valid_refresh_token_obj: RefreshToken,
    mock_redis
):
    """TC-D01: Successful Logout with Token Blacklisting"""
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {valid_access_token}"},
        json={"refresh_token": valid_refresh_token_obj.token}
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Logged out successfully"

    # Verify refresh token was revoked
    await db_session.refresh(valid_refresh_token_obj)
    assert valid_refresh_token_obj.is_revoked is True

    # Verify Redis blacklist was called (through client.setex)
    mock_redis.client.setex.assert_called()


@pytest.mark.asyncio
async def test_logout_already_revoked_token(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    valid_access_token: str,
    valid_refresh_token_obj: RefreshToken,
    mock_redis
):
    """TC-D02: Logout with Already Revoked Token (Idempotent)"""
    # Revoke token first
    valid_refresh_token_obj.is_revoked = True
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {valid_access_token}"},
        json={"refresh_token": valid_refresh_token_obj.token}
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Logged out successfully"


@pytest.mark.asyncio
async def test_logout_without_authentication(client: AsyncClient):
    """TC-D03: Logout Without Authentication"""
    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "some_token"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_invalid_access_token(client: AsyncClient):
    """TC-D04: Logout with Invalid Access Token"""
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": "Bearer invalid.token.here"},
        json={"refresh_token": "some_token"}
    )

    assert response.status_code == 401


# ============================================================================
# TEST GROUP E: GET /api/v1/auth/me
# ============================================================================

@pytest.mark.asyncio
async def test_get_current_user_profile(
    client: AsyncClient,
    admin_user: User,
    valid_access_token: str,
    mock_redis
):
    """TC-E01: Get Current User Profile"""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {valid_access_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["email"] == admin_user.email
    assert data["role"] == "admin"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_get_user_blacklisted_token(
    client: AsyncClient,
    admin_user: User,
    valid_access_token: str,
    mock_redis
):
    """TC-E02: Blacklisted Access Token"""
    # Mock Redis to indicate token is blacklisted (exists returns > 0)
    mock_redis.client.exists.return_value = 1

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {valid_access_token}"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_user_missing_token(client: AsyncClient):
    """TC-E03: Missing Access Token"""
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_user_expired_token(client: AsyncClient, admin_user: User):
    """TC-E04: Expired Access Token"""
    # Create expired token
    expired_token = create_access_token(
        data={
            "user_id": str(admin_user.id),
            "email": admin_user.email,
            "role": admin_user.role.value
        },
        expires_delta=timedelta(minutes=-10)  # Expired 10 minutes ago
    )

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_user_inactive_account(
    client: AsyncClient,
    inactive_user: User
):
    """TC-E05: Inactive User Account"""
    # Create token for inactive user
    token = create_access_token(
        data={
            "user_id": str(inactive_user.id),
            "email": inactive_user.email,
            "role": inactive_user.role.value
        }
    )

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401


# ============================================================================
# TEST GROUP F: End-to-End Authentication Flow
# ============================================================================

@pytest.mark.asyncio
async def test_complete_authentication_journey(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_oauth2_service,
    mock_redis
):
    """TC-F01: Complete Authentication Journey"""
    import asyncio

    # Step 1: Login - Get authorization URL
    login_response = await client.post("/api/v1/auth/login")
    assert login_response.status_code == 200

    # Step 2: Callback - Complete OAuth2
    callback_response = await client.get(
        "/api/v1/auth/callback",
        params={"code": "auth_code_123"}
    )
    assert callback_response.status_code == 200
    tokens = callback_response.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # Step 3: Get user profile
    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert me_response.status_code == 200
    user_data = me_response.json()
    assert user_data["email"] == "newuser@oauth.com"

    # Small delay to ensure different JWT timestamps (prevent token hash collision)
    await asyncio.sleep(1.1)

    # Step 4: Refresh tokens
    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert refresh_response.status_code == 200
    new_tokens = refresh_response.json()
    new_access_token = new_tokens["access_token"]

    # Step 5: Verify still authenticated with new token
    me_response_2 = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {new_access_token}"}
    )
    assert me_response_2.status_code == 200

    # Step 6: Logout
    logout_response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {new_access_token}"},
        json={"refresh_token": new_tokens["refresh_token"]}
    )
    assert logout_response.status_code == 200


@pytest.mark.asyncio
async def test_token_rotation_security(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    valid_refresh_token_obj: RefreshToken,
    mock_redis
):
    """TC-F02: Token Rotation Security"""
    old_refresh_token = valid_refresh_token_obj.token

    # First refresh - should succeed
    refresh_response_1 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token}
    )
    assert refresh_response_1.status_code == 200

    # Second refresh with old token - should fail
    refresh_response_2 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token}
    )
    assert refresh_response_2.status_code == 401

    # Verify old token is revoked
    await db_session.refresh(valid_refresh_token_obj)
    assert valid_refresh_token_obj.is_revoked is True
