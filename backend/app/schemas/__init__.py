"""
Pydantic schemas package
"""
from app.schemas.auth import (
    TokenResponse,
    RefreshTokenRequest,
    UserInfo,
    OAuth2LoginRequest,
    OAuth2LoginResponse,
    LoginRequest,
    TokenClaims,
    LogoutRequest,
)
from app.schemas.chat import (
    CreateSessionRequest,
    SessionResponse,
    MessageResponse,
    SessionHistoryResponse,
    QueryRequest,
    QueryResponse,
)

__all__ = [
    # Auth schemas
    "TokenResponse",
    "RefreshTokenRequest",
    "UserInfo",
    "OAuth2LoginRequest",
    "OAuth2LoginResponse",
    "LoginRequest",
    "TokenClaims",
    "LogoutRequest",

    # Chat schemas
    "CreateSessionRequest",
    "SessionResponse",
    "MessageResponse",
    "SessionHistoryResponse",
    "QueryRequest",
    "QueryResponse",
]
