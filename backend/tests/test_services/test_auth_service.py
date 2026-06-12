"""
Tests for AuthService and OAuth2Service (Test Scenarios B, C, D, E)
"""
import pytest
import hashlib
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select
from app.services.auth_service import AuthService, OAuth2Service
from app.models.user import User, UserRole
from app.models.token import RefreshToken
from app.core.security import get_password_hash, create_refresh_token, decode_token_unsafe


@pytest.fixture
async def test_user(db_session):
    """Create a test user with password"""
    user = User(
        email="user@example.com",
        password_hash=get_password_hash("SecurePass123!"),
        role=UserRole.USER,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_admin_user(db_session):
    """Create a test admin user"""
    user = User(
        email="admin@example.com",
        password_hash=get_password_hash("AdminPass123!"),
        role=UserRole.ADMIN,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


class TestPasswordAuthentication:
    """Test scenarios B1-B6: Password Authentication"""

    @pytest.mark.asyncio
    async def test_b1_authenticate_valid_credentials(self, db_session, test_user):
        """B1: Authenticate user with valid credentials"""
        auth_service = AuthService()
        
        user = await auth_service.authenticate_user(
            db_session,
            "user@example.com",
            "SecurePass123!"
        )
        
        assert user is not None
        assert user.email == "user@example.com"

    @pytest.mark.asyncio
    async def test_b2_reject_invalid_password(self, db_session, test_user):
        """B2: Reject authentication with invalid password"""
        auth_service = AuthService()
        
        user = await auth_service.authenticate_user(
            db_session,
            "user@example.com",
            "WrongPassword"
        )
        
        assert user is None

    @pytest.mark.asyncio
    async def test_b3_reject_nonexistent_user(self, db_session):
        """B3: Reject authentication for non-existent user"""
        auth_service = AuthService()
        
        user = await auth_service.authenticate_user(
            db_session,
            "nonexistent@example.com",
            "password"
        )
        
        assert user is None

    @pytest.mark.asyncio
    async def test_b6_set_update_user_password(self, db_session, test_user):
        """B6: Set/update user password"""
        auth_service = AuthService()
        new_password = "NewSecurePass456!"
        
        # Update password
        await auth_service.set_user_password(db_session, test_user.id, new_password)
        await db_session.commit()
        
        # Verify new password works
        user = await auth_service.authenticate_user(
            db_session,
            test_user.email,
            new_password
        )
        assert user is not None


class TestOAuth2Integration:
    """Test scenarios C1-C5: OAuth2 Integration"""

    def test_c1_generate_oauth2_authorization_url(self):
        """C1: Generate OAuth2 authorization URL with state"""
        oauth_service = OAuth2Service()
        
        auth_url, state = oauth_service.get_authorization_url()
        
        assert oauth_service.client_id in auth_url
        assert oauth_service.redirect_uri in auth_url
        assert state in auth_url
        assert len(state) == 36  # UUID length

    @pytest.mark.asyncio
    async def test_c2_exchange_code_for_token(self):
        """C2: Exchange authorization code for access token"""
        oauth_service = OAuth2Service()
        
        mock_response = {
            "access_token": "ya29.mock_token",
            "token_type": "Bearer",
            "expires_in": 3599
        }
        
        with patch.object(oauth_service, '_make_token_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await oauth_service.exchange_code_for_token("auth_code_123")
            
            assert result["access_token"] == "ya29.mock_token"
            assert result["token_type"] == "Bearer"

    @pytest.mark.asyncio
    async def test_c3_fetch_user_info(self):
        """C3: Fetch user info from OAuth2 provider"""
        oauth_service = OAuth2Service()
        
        mock_userinfo = {
            "sub": "google_12345",
            "email": "oauth@example.com",
            "name": "OAuth User"
        }
        
        with patch.object(oauth_service, '_make_userinfo_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_userinfo
            
            result = await oauth_service.get_user_info("oauth_access_token")
            
            assert result["email"] == "oauth@example.com"
            assert result["sub"] == "google_12345"

    @pytest.mark.asyncio
    async def test_c4_create_user_from_oauth(self, db_session):
        """C4: Create new user from OAuth2 login"""
        auth_service = AuthService()

        user = await auth_service.create_user_from_oauth(
            db_session,
            "newuser@example.com"
        )
        await db_session.commit()

        assert user is not None
        assert user.email == "newuser@example.com"
        assert user.password_hash is None
        assert user.role == UserRole.USER


class TestTokenRefresh:
    """Test scenarios D1-D6: Token Refresh and Rotation"""

    @pytest.mark.asyncio
    async def test_d1_refresh_access_token_successfully(self, db_session, test_user):
        """D1: Refresh access token with valid refresh token"""
        auth_service = AuthService()

        # Create refresh token
        refresh_token_str = create_refresh_token({"user_id": str(test_user.id)})
        token_hash = hashlib.sha256(refresh_token_str.encode()).hexdigest()

        refresh_token = RefreshToken(
            user_id=test_user.id,
            token_hash=token_hash,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        db_session.add(refresh_token)
        await db_session.commit()

        # Refresh the token
        result = await auth_service.refresh_access_token(db_session, refresh_token_str)

        assert result is not None
        assert "access_token" in result
        assert "refresh_token" in result

        # Verify old token is revoked
        await db_session.refresh(refresh_token)
        assert refresh_token.is_revoked is True

    @pytest.mark.asyncio
    async def test_d4_reject_reused_refresh_token(self, db_session, test_user):
        """D4: Reject reuse of old refresh token"""
        auth_service = AuthService()

        # Create refresh token
        refresh_token_str = create_refresh_token({"user_id": str(test_user.id)})
        token_hash = hashlib.sha256(refresh_token_str.encode()).hexdigest()

        refresh_token = RefreshToken(
            user_id=test_user.id,
            token_hash=token_hash,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        db_session.add(refresh_token)
        await db_session.commit()

        # Use token once
        await auth_service.refresh_access_token(db_session, refresh_token_str)

        # Try to use again
        result = await auth_service.refresh_access_token(db_session, refresh_token_str)
        assert result is None

    @pytest.mark.asyncio
    async def test_d5_reject_expired_refresh_token(self, db_session, test_user):
        """D5: Reject expired refresh token"""
        auth_service = AuthService()

        # Create expired refresh token
        refresh_token_str = create_refresh_token({"user_id": str(test_user.id)}, expires_delta=timedelta(seconds=-100))
        token_hash = hashlib.sha256(refresh_token_str.encode()).hexdigest()

        refresh_token = RefreshToken(
            user_id=test_user.id,
            token_hash=token_hash,
            expires_at=datetime.utcnow() - timedelta(seconds=100)
        )
        db_session.add(refresh_token)
        await db_session.commit()

        # Try to refresh
        result = await auth_service.refresh_access_token(db_session, refresh_token_str)
        assert result is None


class TestTokenRevocation:
    """Test scenarios E1-E4: Token Revocation"""

    @pytest.mark.asyncio
    async def test_e1_revoke_single_refresh_token(self, db_session, test_user):
        """E1: Revoke single refresh token"""
        auth_service = AuthService()

        # Create 2 refresh tokens
        token1_str = create_refresh_token({"user_id": str(test_user.id)})
        token1_hash = hashlib.sha256(token1_str.encode()).hexdigest()
        token1 = RefreshToken(
            user_id=test_user.id,
            token_hash=token1_hash,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )

        token2_str = create_refresh_token({"user_id": str(test_user.id)})
        token2_hash = hashlib.sha256(token2_str.encode()).hexdigest()
        token2 = RefreshToken(
            user_id=test_user.id,
            token_hash=token2_hash,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )

        db_session.add_all([token1, token2])
        await db_session.commit()

        # Revoke token1
        await auth_service.revoke_refresh_token(db_session, token1_hash)
        await db_session.commit()

        # Verify
        await db_session.refresh(token1)
        await db_session.refresh(token2)
        assert token1.is_revoked is True
        assert token1.revoked_at is not None
        assert token2.is_revoked is False

    @pytest.mark.asyncio
    async def test_e2_revoke_all_user_tokens(self, db_session, test_user):
        """E2: Revoke all user tokens"""
        auth_service = AuthService()

        # Create 3 refresh tokens
        tokens = []
        for _ in range(3):
            token_str = create_refresh_token({"user_id": str(test_user.id)})
            token_hash = hashlib.sha256(token_str.encode()).hexdigest()
            token = RefreshToken(
                user_id=test_user.id,
                token_hash=token_hash,
                expires_at=datetime.utcnow() + timedelta(days=7)
            )
            tokens.append(token)
            db_session.add(token)

        await db_session.commit()

        # Revoke all
        await auth_service.revoke_all_user_tokens(db_session, test_user.id)
        await db_session.commit()

        # Verify all revoked
        for token in tokens:
            await db_session.refresh(token)
            assert token.is_revoked is True
            assert token.revoked_at is not None
