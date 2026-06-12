"""
Services package for business logic.

This package contains service modules for:
- Authentication and authorization (OAuth2, JWT)
- GenAI and LLM integration
- Data ingestion and synchronization
- External integrations (Confluence, Jira, etc.)
"""
from app.services.auth_service import AuthService, OAuth2Service, AuthenticationError

__all__ = [
    "AuthService",
    "OAuth2Service",
    "AuthenticationError",
]
