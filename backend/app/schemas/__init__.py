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
from app.schemas.admin import (
    DataSourceCreate,
    DataSourceUpdate,
    DataSourceResponse,
    DataSourceListResponse,
    SyncTriggerResponse,
    DeleteResponse,
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

    # Admin schemas
    "DataSourceCreate",
    "DataSourceUpdate",
    "DataSourceResponse",
    "DataSourceListResponse",
    "SyncTriggerResponse",
    "DeleteResponse",
]
