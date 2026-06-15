"""
GenAI services package.

This package contains GenAI-related services for:
- Embedding generation (local and cloud models)
- LLM integration
- RAG pipeline orchestration
"""
from app.services.genai.embedding_service import EmbeddingService, embedding_service, EmbeddingError

__all__ = [
    "EmbeddingService",
    "embedding_service",
    "EmbeddingError",
]