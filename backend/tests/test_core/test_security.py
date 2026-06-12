"""
Tests for JWT token management (Test Scenarios A1-A7)
"""
import pytest
from datetime import datetime, timedelta
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_token,
    get_password_hash,
    verify_password,
    decode_token_unsafe,
)
from app.core.config import settings


class TestJWTTokenManagement:
    """Test scenarios A1-A7: JWT Token Management"""

    def test_a1_create_access_token_with_claims(self):
        """A1: Create access token with all required claims"""
        user_data = {
            "user_id": "550e8400-e29b-41d4-a716-446655440000",
            "email": "test@example.com",
            "role": "admin"
        }
        
        token = create_access_token(user_data)
        claims = decode_token_unsafe(token)
        
        assert claims["user_id"] == user_data["user_id"]
        assert claims["email"] == user_data["email"]
        assert claims["role"] == user_data["role"]
        assert claims["type"] == "access"
        assert "exp" in claims
        assert "iat" in claims
        
        # Verify expiration is approximately 15 minutes (900 seconds)
        exp_delta = claims["exp"] - claims["iat"]
        assert 890 <= exp_delta <= 910  # Allow small tolerance

    def test_a2_create_refresh_token_minimal_claims(self):
        """A2: Create refresh token with minimal claims"""
        user_id = "550e8400-e29b-41d4-a716-446655440000"

        token = create_refresh_token({"user_id": user_id})
        claims = decode_token_unsafe(token)
        
        assert claims["user_id"] == user_id
        assert claims["type"] == "refresh"
        assert "exp" in claims
        assert "iat" in claims
        assert "email" not in claims
        assert "role" not in claims
        
        # Verify expiration is approximately 7 days (604800 seconds)
        exp_delta = claims["exp"] - claims["iat"]
        assert 604000 <= exp_delta <= 605000  # Allow small tolerance

    def test_a3_validate_valid_access_token(self):
        """A3: Validate valid access token successfully"""
        user_data = {
            "user_id": "550e8400-e29b-41d4-a716-446655440000",
            "email": "test@example.com",
            "role": "admin"
        }
        
        token = create_access_token(user_data)
        claims = verify_token(token, expected_type="access")
        
        assert claims is not None
        assert claims["user_id"] == user_data["user_id"]

    def test_a4_reject_expired_access_token(self):
        """A4: Reject expired access token"""
        user_data = {"user_id": "test-user", "email": "test@example.com", "role": "user"}
        expired_time = timedelta(seconds=-100)
        
        token = create_access_token(user_data, expires_delta=expired_time)
        claims = verify_token(token, expected_type="access")
        
        assert claims is None

    def test_a5_reject_invalid_signature(self):
        """A5: Reject access token with invalid signature"""
        user_data = {"user_id": "test-user", "email": "test@example.com", "role": "user"}
        
        token = create_access_token(user_data)
        # Tamper with the signature
        parts = token.split('.')
        tampered_token = f"{parts[0]}.{parts[1]}.invalid_signature"
        
        claims = verify_token(tampered_token)
        assert claims is None

    def test_a6_reject_refresh_token_as_access(self):
        """A6: Reject refresh token when access token expected"""
        user_id = "test-user"

        refresh_token = create_refresh_token({"user_id": user_id})
        claims = verify_token(refresh_token, expected_type="access")
        
        assert claims is None

    def test_a7_decode_token_claims(self):
        """A7: Decode token claims correctly"""
        user_data = {
            "user_id": "550e8400-e29b-41d4-a716-446655440000",
            "email": "admin@example.com",
            "role": "admin"
        }
        
        token = create_access_token(user_data)
        claims = decode_token_unsafe(token)
        
        assert claims["user_id"] == user_data["user_id"]
        assert claims["email"] == user_data["email"]
        assert claims["role"] == user_data["role"]


class TestPasswordHashing:
    """Test scenarios B4-B5: Password hashing"""

    def test_b4_password_hashed_with_bcrypt_12_rounds(self):
        """B4: Password hashed with bcrypt 12 rounds"""
        password = "TestPassword123"
        
        hashed = get_password_hash(password)
        
        # Bcrypt hash format: $2b$rounds$salt+hash
        assert hashed.startswith("$2b$12$")
        assert len(hashed) == 60  # Standard bcrypt hash length

    def test_b5_verify_password_against_hash(self):
        """B5: Verify password against bcrypt hash"""
        password = "SecurePass123!"
        hashed = get_password_hash(password)
        
        # Correct password
        assert verify_password(password, hashed) is True
        
        # Wrong password
        assert verify_password("WrongPassword", hashed) is False
