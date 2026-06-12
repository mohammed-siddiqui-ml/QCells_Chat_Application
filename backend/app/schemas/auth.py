"""
Pydantic schemas for authentication
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from app.models.user import UserRole


class TokenResponse(BaseModel):
    """Response schema for token endpoints"""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiry in seconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 900
            }
        }


class RefreshTokenRequest(BaseModel):
    """Request schema for token refresh"""
    refresh_token: str = Field(..., description="Refresh token to exchange")
    
    class Config:
        json_schema_extra = {
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }


class UserInfo(BaseModel):
    """User information schema"""
    id: str = Field(..., description="User UUID")
    email: Optional[str] = Field(None, description="User email")
    role: UserRole = Field(..., description="User role")
    is_active: bool = Field(..., description="Account active status")
    created_at: datetime = Field(..., description="Account creation timestamp")
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "admin@example.com",
                "role": "admin",
                "is_active": True,
                "created_at": "2024-01-01T00:00:00Z",
                "last_login": "2024-01-15T10:30:00Z"
            }
        }


class OAuth2LoginRequest(BaseModel):
    """Request schema for OAuth2 login initiation"""
    provider: str = Field(default="google", description="OAuth2 provider")
    redirect_uri: Optional[str] = Field(None, description="Custom redirect URI")
    
    class Config:
        json_schema_extra = {
            "example": {
                "provider": "google",
                "redirect_uri": "http://localhost:3000/auth/callback"
            }
        }


class OAuth2LoginResponse(BaseModel):
    """Response schema for OAuth2 login initiation"""
    authorization_url: str = Field(..., description="URL to redirect user for authorization")
    state: str = Field(..., description="CSRF state token")
    
    class Config:
        json_schema_extra = {
            "example": {
                "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
                "state": "random-state-token-12345"
            }
        }


class LoginRequest(BaseModel):
    """Request schema for password-based login"""
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=8, description="User password")
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "admin@example.com",
                "password": "SecurePassword123!"
            }
        }


class TokenClaims(BaseModel):
    """JWT token claims schema"""
    user_id: str = Field(..., description="User UUID")
    email: Optional[str] = Field(None, description="User email")
    role: UserRole = Field(..., description="User role")
    exp: int = Field(..., description="Expiration timestamp")
    iat: int = Field(..., description="Issued at timestamp")
    type: str = Field(..., description="Token type (access/refresh)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "admin@example.com",
                "role": "admin",
                "exp": 1704110400,
                "iat": 1704109500,
                "type": "access"
            }
        }


class LogoutRequest(BaseModel):
    """Request schema for logout"""
    refresh_token: Optional[str] = Field(None, description="Refresh token to revoke")
    revoke_all: bool = Field(default=False, description="Revoke all user tokens")
    
    class Config:
        json_schema_extra = {
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "revoke_all": False
            }
        }
