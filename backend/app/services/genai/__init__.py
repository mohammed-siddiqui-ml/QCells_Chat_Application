"""
GenAI services package.

This package contains GenAI-related services for:
- Embedding generation (local and cloud models)
- LLM integration
- RAG pipeline orchestration
"""
from app.services.genai.embedding_service import EmbeddingService, embedding_service, EmbeddingError
from app.services.genai.llm_service import LLMService, llm_service, LLMError, get_llm_service

__all__ = [
    "EmbeddingService",
    "embedding_service",
    "EmbeddingError",
    "LLMService",
    "llm_service",
    "LLMError",
    "get_llm_service",
]