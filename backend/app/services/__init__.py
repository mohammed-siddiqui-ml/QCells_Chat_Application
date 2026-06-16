"""
Services package for business logic.

This package contains service modules for:
- Authentication and authorization (OAuth2, JWT)
- GenAI and LLM integration
- Data ingestion and synchronization
- External integrations (Confluence, Jira, etc.)
- Hybrid search (semantic + keyword)
"""
from app.services.auth_service import AuthService, OAuth2Service, AuthenticationError
from app.services.genai import (
    EmbeddingService,
    embedding_service,
    EmbeddingError,
    LLMService,
    llm_service,
    LLMError,
    get_llm_service,
    RAGService,
    rag_service,
    RAGError,
    get_rag_service
)
from app.services.search_service import SearchService, search_service

__all__ = [
    "AuthService",
    "OAuth2Service",
    "AuthenticationError",
    "EmbeddingService",
    "embedding_service",
    "EmbeddingError",
    "LLMService",
    "llm_service",
    "LLMError",
    "get_llm_service",
    "RAGService",
    "rag_service",
    "RAGError",
    "get_rag_service",
    "SearchService",
    "search_service",
]
