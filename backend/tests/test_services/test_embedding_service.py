"""
Comprehensive tests for the Embedding Service.

Tests cover:
- Service initialization (local and OpenAI models)
- Single embedding generation
- Batch embedding generation
- Caching functionality
- Normalization
- Error handling
"""
# ⚠️ CRITICAL: Set EMBEDDING_MODEL=openai BEFORE any app imports
# This prevents SSL certificate errors when downloading HuggingFace models in WSL
import os
os.environ['EMBEDDING_MODEL'] = 'openai'

import pytest
import numpy as np
from unittest.mock import MagicMock, AsyncMock, patch, Mock
from typing import List

from app.services.genai.embedding_service import (
    EmbeddingService,
    EmbeddingError,
    embedding_service
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_settings_local():
    """Mock settings for local model."""
    with patch('app.services.genai.embedding_service.settings') as mock_settings:
        mock_settings.EMBEDDING_MODEL = "local"
        mock_settings.LOCAL_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.EMBEDDING_CACHE_TTL = 86400
        mock_settings.OPENAI_API_KEY = None
        mock_settings.OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
        yield mock_settings


@pytest.fixture
def mock_settings_openai():
    """Mock settings for OpenAI model."""
    with patch('app.services.genai.embedding_service.settings') as mock_settings:
        mock_settings.EMBEDDING_MODEL = "openai"
        mock_settings.LOCAL_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.EMBEDDING_CACHE_TTL = 86400
        mock_settings.OPENAI_API_KEY = "test-api-key-123"
        mock_settings.OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
        yield mock_settings


@pytest.fixture
def mock_sentence_transformer():
    """Mock SentenceTransformer model."""
    mock_model = MagicMock()
    mock_model.encode = MagicMock()
    return mock_model


@pytest.fixture
def mock_openai_client():
    """Mock AsyncOpenAI client."""
    mock_client = AsyncMock()
    return mock_client


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    with patch('app.services.genai.embedding_service.redis_client') as mock_redis:
        mock_redis.get_cached_query = AsyncMock(return_value=None)
        mock_redis.set_cached_query = AsyncMock()
        mock_redis.clear_cache_pattern = AsyncMock(return_value=5)
        yield mock_redis


@pytest.fixture
def sample_texts():
    """Sample texts for testing."""
    return [
        "What is machine learning?",
        "Explain artificial intelligence",
        "How does deep learning work?",
        "What are neural networks?",
        "Define natural language processing"
    ]


@pytest.fixture
def fake_embedding_384():
    """Generate a fake 384-dimensional normalized embedding."""
    embedding = np.random.randn(384)
    embedding = embedding / np.linalg.norm(embedding)  # Normalize
    return embedding.tolist()


@pytest.fixture
def fake_embedding_1536():
    """Generate a fake 1536-dimensional normalized embedding."""
    embedding = np.random.randn(1536)
    embedding = embedding / np.linalg.norm(embedding)  # Normalize
    return embedding.tolist()


# ============================================================================
# INITIALIZATION TESTS (TC-001 to TC-004)
# ============================================================================

@pytest.mark.unit
def test_initialize_local_model(mock_settings_local, mock_sentence_transformer):
    """TC-001: Initialize EmbeddingService with local model."""
    with patch('app.services.genai.embedding_service.SentenceTransformer', return_value=mock_sentence_transformer):
        service = EmbeddingService()
        
        assert service.model_type == "local"
        assert service.local_model is not None
        assert service.openai_client is None
        assert service.embedding_dimension == 384
        assert service.batch_size == 32
        assert service.cache_ttl == 86400


@pytest.mark.unit
def test_initialize_openai_model(mock_settings_openai, mock_openai_client):
    """TC-002: Initialize EmbeddingService with OpenAI model."""
    with patch('app.services.genai.embedding_service.AsyncOpenAI', return_value=mock_openai_client):
        service = EmbeddingService()
        
        assert service.model_type == "openai"
        assert service.openai_client is not None
        assert service.local_model is None
        assert service.embedding_dimension == 1536
        assert service.batch_size == 32


@pytest.mark.unit
def test_invalid_model_type():
    """TC-003: Service initialization fails with invalid model type."""
    with patch('app.services.genai.embedding_service.settings') as mock_settings:
        mock_settings.EMBEDDING_MODEL = "invalid_model"
        
        with pytest.raises(ValueError) as exc_info:
            EmbeddingService()
        
        assert "Unsupported EMBEDDING_MODEL" in str(exc_info.value)
        assert "invalid_model" in str(exc_info.value)


@pytest.mark.unit
def test_openai_without_api_key(mock_settings_openai):
    """TC-004: OpenAI initialization fails without API key."""
    mock_settings_openai.OPENAI_API_KEY = None

    with pytest.raises(EmbeddingError) as exc_info:
        EmbeddingService()

    assert "OPENAI_API_KEY" in str(exc_info.value)


# ============================================================================
# SINGLE EMBEDDING GENERATION TESTS (TC-005 to TC-008)
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_generate_local_embedding():
    """TC-005: Generate embedding using real local model."""
    # This test uses a real local model
    with patch('app.services.genai.embedding_service.settings') as mock_settings:
        mock_settings.EMBEDDING_MODEL = "local"
        mock_settings.LOCAL_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.EMBEDDING_CACHE_TTL = 86400

        with patch('app.services.genai.embedding_service.redis_client') as mock_redis:
            mock_redis.get_cached_query = AsyncMock(return_value=None)
            mock_redis.set_cached_query = AsyncMock()

            service = EmbeddingService()
            embedding = await service.generate_embedding("What is machine learning?", use_cache=False)

            assert isinstance(embedding, list)
            assert len(embedding) == 384
            assert all(isinstance(x, float) for x in embedding)

            # Verify normalization (L2 norm should be ~1.0)
            norm = np.linalg.norm(embedding)
            assert abs(norm - 1.0) < 0.001


@pytest.mark.asyncio
@pytest.mark.unit
async def test_generate_openai_embedding(mock_settings_openai, mock_openai_client, fake_embedding_1536):
    """TC-006: Generate embedding using mocked OpenAI API."""
    # Mock the OpenAI response
    mock_response = Mock()
    mock_response.data = [Mock(embedding=fake_embedding_1536)]
    mock_openai_client.embeddings.create = AsyncMock(return_value=mock_response)

    with patch('app.services.genai.embedding_service.AsyncOpenAI', return_value=mock_openai_client):
        with patch('app.services.genai.embedding_service.redis_client') as mock_redis:
            mock_redis.get_cached_query = AsyncMock(return_value=None)
            mock_redis.set_cached_query = AsyncMock()

            service = EmbeddingService()
            embedding = await service.generate_embedding("What is AI?", use_cache=False)

            assert isinstance(embedding, list)
            assert len(embedding) == 1536

            # Verify normalization
            norm = np.linalg.norm(embedding)
            assert abs(norm - 1.0) < 0.001


@pytest.mark.asyncio
@pytest.mark.unit
async def test_empty_text_error(mock_settings_local, mock_sentence_transformer):
    """TC-007: Empty text raises EmbeddingError."""
    with patch('app.services.genai.embedding_service.SentenceTransformer', return_value=mock_sentence_transformer):
        service = EmbeddingService()

        with pytest.raises(EmbeddingError) as exc_info:
            await service.generate_embedding("")

        assert "empty text" in str(exc_info.value).lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_whitespace_only_text_error(mock_settings_local, mock_sentence_transformer):
    """TC-008: Whitespace-only text raises EmbeddingError."""
    with patch('app.services.genai.embedding_service.SentenceTransformer', return_value=mock_sentence_transformer):
        service = EmbeddingService()

        with pytest.raises(EmbeddingError) as exc_info:
            await service.generate_embedding("   \n\t  ")

        assert "empty text" in str(exc_info.value).lower()


# ============================================================================
# CACHING TESTS (TC-009 to TC-012)
# ============================================================================

@pytest.mark.unit
def test_cache_key_generation(mock_settings_local, mock_sentence_transformer):
    """TC-009: Cache key generation uses SHA-256 hash."""
    with patch('app.services.genai.embedding_service.SentenceTransformer', return_value=mock_sentence_transformer):
        service = EmbeddingService()

        key1 = service._get_cache_key("test query")
        key2 = service._get_cache_key("test query")
        key3 = service._get_cache_key("different query")

        # Keys should start with "embedding:{model_type}:"
        assert key1.startswith("embedding:local:")
        assert key2.startswith("embedding:local:")

        # Same text should produce same key
        assert key1 == key2

        # Different text should produce different key
        assert key1 != key3

        # Hash part should be 64 hex characters (SHA-256)
        hash_part = key1.split(":")[-1]
        assert len(hash_part) == 64
        assert all(c in "0123456789abcdef" for c in hash_part)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_embedding_cached_successfully(mock_settings_local, mock_sentence_transformer, fake_embedding_384):
    """TC-010: Embedding is cached and retrieved correctly."""
    mock_sentence_transformer.encode.return_value = np.array(fake_embedding_384)

    with patch('app.services.genai.embedding_service.SentenceTransformer', return_value=mock_sentence_transformer):
        with patch('app.services.genai.embedding_service.redis_client') as mock_redis:
            # First call: cache miss
            mock_redis.get_cached_query = AsyncMock(return_value=None)
            mock_redis.set_cached_query = AsyncMock()

            service = EmbeddingService()
            embedding1 = await service.generate_embedding("test", use_cache=True)

            # Verify set_cached_query was called
            assert mock_redis.set_cached_query.call_count == 1
            call_args = mock_redis.set_cached_query.call_args
            assert call_args[0][0].startswith("embedding:local:")
            assert call_args[1]['ttl'] == 86400

            # Second call: cache hit
            mock_redis.get_cached_query = AsyncMock(return_value=embedding1)
            embedding2 = await service.generate_embedding("test", use_cache=True)

            # Verify get_cached_query was called
            assert mock_redis.get_cached_query.call_count >= 1

            # Embeddings should match
            assert embedding1 == embedding2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cache_disabled(mock_settings_local, mock_sentence_transformer, fake_embedding_384):
    """TC-011: Cache is bypassed when use_cache=False."""
    mock_sentence_transformer.encode.return_value = np.array(fake_embedding_384)

    with patch('app.services.genai.embedding_service.SentenceTransformer', return_value=mock_sentence_transformer):
        with patch('app.services.genai.embedding_service.redis_client') as mock_redis:
            mock_redis.get_cached_query = AsyncMock(return_value=None)
            mock_redis.set_cached_query = AsyncMock()

            service = EmbeddingService()
            await service.generate_embedding("test", use_cache=False)

            # Verify cache methods were NOT called
            assert mock_redis.get_cached_query.call_count == 0
            assert mock_redis.set_cached_query.call_count == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cache_failure_graceful(mock_settings_local, mock_sentence_transformer, fake_embedding_384):
    """TC-012: Embedding is generated even if cache fails."""
    mock_sentence_transformer.encode.return_value = np.array(fake_embedding_384)

    with patch('app.services.genai.embedding_service.SentenceTransformer', return_value=mock_sentence_transformer):
        with patch('app.services.genai.embedding_service.redis_client') as mock_redis:
            # Mock cache to raise exception
            mock_redis.get_cached_query = AsyncMock(side_effect=Exception("Redis connection failed"))
            mock_redis.set_cached_query = AsyncMock(side_effect=Exception("Redis connection failed"))

            service = EmbeddingService()
            # Should not raise exception, fallback to generating embedding
            embedding = await service.generate_embedding("test", use_cache=True)

            assert isinstance(embedding, list)
            assert len(embedding) == 384


# ============================================================================
# BATCH PROCESSING TESTS (TC-013 to TC-017)
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_batch_processing_10_texts():
    """TC-013: Batch process 10 texts using real local model."""
    with patch('app.services.genai.embedding_service.settings') as mock_settings:
        mock_settings.EMBEDDING_MODEL = "local"
        mock_settings.LOCAL_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.EMBEDDING_CACHE_TTL = 86400

        with patch('app.services.genai.embedding_service.redis_client') as mock_redis:
            mock_redis.get_cached_query = AsyncMock(return_value=None)
            mock_redis.set_cached_query = AsyncMock()

            service = EmbeddingService()
            texts = [f"Test text number {i}" for i in range(10)]
            embeddings = await service.generate_batch_embeddings(texts, use_cache=False)

            assert len(embeddings) == 10
            for emb in embeddings:
                assert len(emb) == 384
                # Verify normalization
                norm = np.linalg.norm(emb)
                assert abs(norm - 1.0) < 0.001


@pytest.mark.asyncio
@pytest.mark.integration
async def test_batch_processing_50_texts_multiple_batches():
    """TC-014: Batch process 50 texts in multiple batches (32+18)."""
    with patch('app.services.genai.embedding_service.settings') as mock_settings:
        mock_settings.EMBEDDING_MODEL = "local"
        mock_settings.LOCAL_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.EMBEDDING_CACHE_TTL = 86400

        with patch('app.services.genai.embedding_service.redis_client') as mock_redis:
            mock_redis.get_cached_query = AsyncMock(return_value=None)
            mock_redis.set_cached_query = AsyncMock()

            service = EmbeddingService()
            texts = [f"Test text number {i}" for i in range(50)]
            embeddings = await service.generate_batch_embeddings(texts, use_cache=False)

            assert len(embeddings) == 50
            for emb in embeddings:
                assert len(emb) == 384
                norm = np.linalg.norm(emb)
                assert abs(norm - 1.0) < 0.001


@pytest.mark.asyncio
@pytest.mark.unit
async def test_batch_with_empty_texts_filtered(mock_settings_local, mock_sentence_transformer):
    """TC-015: Batch processing filters out empty texts."""
    # Create mock embeddings for valid texts
    valid_embeddings = [np.random.randn(384) for _ in range(3)]
    mock_sentence_transformer.encode.return_value = np.array(valid_embeddings)

    with patch('app.services.genai.embedding_service.SentenceTransformer', return_value=mock_sentence_transformer):
        service = EmbeddingService()

        texts = ["text1", "", "text2", "   ", "text3"]
        embeddings = await service.generate_batch_embeddings(texts, use_cache=False)

        # Only 3 valid texts should be processed
        assert len(embeddings) == 3


@pytest.mark.asyncio
@pytest.mark.unit
async def test_batch_all_empty_error(mock_settings_local, mock_sentence_transformer):
    """TC-016: Batch with all empty texts raises EmbeddingError."""
    with patch('app.services.genai.embedding_service.SentenceTransformer', return_value=mock_sentence_transformer):
        service = EmbeddingService()

        texts = ["", "   ", "\n"]
        with pytest.raises(EmbeddingError) as exc_info:
            await service.generate_batch_embeddings(texts, use_cache=False)

        assert "No valid texts" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_batch_empty_list(mock_settings_local, mock_sentence_transformer):
    """TC-017: Batch with empty list returns empty list."""
    with patch('app.services.genai.embedding_service.SentenceTransformer', return_value=mock_sentence_transformer):
        service = EmbeddingService()

        embeddings = await service.generate_batch_embeddings([], use_cache=False)
        assert embeddings == []


# ============================================================================
# NORMALIZATION TESTS (TC-018 to TC-019)
# ============================================================================

@pytest.mark.unit
def test_normalization_correctness(mock_settings_local, mock_sentence_transformer):
    """TC-018: Normalization produces unit vectors."""
    with patch('app.services.genai.embedding_service.SentenceTransformer', return_value=mock_sentence_transformer):
        service = EmbeddingService()

        # Test vector: [3.0, 4.0] has L2 norm = 5.0
        test_vector = [3.0, 4.0]
        normalized = service._normalize_embedding(test_vector)

        # Should be [0.6, 0.8]
        assert abs(normalized[0] - 0.6) < 0.001
        assert abs(normalized[1] - 0.8) < 0.001

        # L2 norm should be 1.0
        norm = np.linalg.norm(normalized)
        assert abs(norm - 1.0) < 0.001


@pytest.mark.unit
def test_zero_norm_handling(mock_settings_local, mock_sentence_transformer):
    """TC-019: Zero-norm embeddings are handled gracefully."""
    with patch('app.services.genai.embedding_service.SentenceTransformer', return_value=mock_sentence_transformer):
        service = EmbeddingService()

        # Zero vector
        zero_vector = [0.0, 0.0, 0.0]
        normalized = service._normalize_embedding(zero_vector)

        # Should return zero vector unchanged
        assert normalized == [0.0, 0.0, 0.0]


# ============================================================================
# CACHE MANAGEMENT TESTS (TC-020)
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_clear_cache(mock_settings_local, mock_sentence_transformer):
    """TC-020: Clear cache removes all embeddings for model type."""
    with patch('app.services.genai.embedding_service.SentenceTransformer', return_value=mock_sentence_transformer):
        with patch('app.services.genai.embedding_service.redis_client') as mock_redis:
            mock_redis.clear_cache_pattern = AsyncMock(return_value=10)

            service = EmbeddingService()
            count = await service.clear_cache()

            # Verify clear_cache_pattern called with correct pattern
            mock_redis.clear_cache_pattern.assert_called_once()
            call_args = mock_redis.clear_cache_pattern.call_args[0][0]
            assert call_args == "embedding:local:*"
            assert count == 10


# ============================================================================
# ERROR HANDLING TESTS (TC-021 to TC-022)
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_local_model_failure(mock_settings_local, mock_sentence_transformer):
    """TC-021: Local model failure raises EmbeddingError."""
    mock_sentence_transformer.encode.side_effect = Exception("Model encoding failed")

    with patch('app.services.genai.embedding_service.SentenceTransformer', return_value=mock_sentence_transformer):
        with patch('app.services.genai.embedding_service.redis_client') as mock_redis:
            mock_redis.get_cached_query = AsyncMock(return_value=None)

            service = EmbeddingService()

            with pytest.raises(EmbeddingError) as exc_info:
                await service.generate_embedding("test", use_cache=False)

            assert "Embedding generation failed" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_api_failure(mock_settings_openai, mock_openai_client):
    """TC-022: OpenAI API failure raises EmbeddingError."""
    mock_openai_client.embeddings.create = AsyncMock(side_effect=Exception("API call failed"))

    with patch('app.services.genai.embedding_service.AsyncOpenAI', return_value=mock_openai_client):
        with patch('app.services.genai.embedding_service.redis_client') as mock_redis:
            mock_redis.get_cached_query = AsyncMock(return_value=None)

            service = EmbeddingService()

            with pytest.raises(EmbeddingError) as exc_info:
                await service.generate_embedding("test", use_cache=False)

            assert "Embedding generation failed" in str(exc_info.value)


# ============================================================================
# GLOBAL INSTANCE TEST (TC-023)
# ============================================================================

@pytest.mark.integration
def test_global_service_instance():
    """TC-023: Global embedding_service instance is available."""
    from app.services.genai.embedding_service import embedding_service

    assert embedding_service is not None
    assert isinstance(embedding_service, EmbeddingService)


# ============================================================================
# EDGE CASE TESTS (TC-024)
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_long_text_handling():
    """TC-024: Long text is processed successfully."""
    with patch('app.services.genai.embedding_service.settings') as mock_settings:
        mock_settings.EMBEDDING_MODEL = "local"
        mock_settings.LOCAL_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.EMBEDDING_CACHE_TTL = 86400

        with patch('app.services.genai.embedding_service.redis_client') as mock_redis:
            mock_redis.get_cached_query = AsyncMock(return_value=None)
            mock_redis.set_cached_query = AsyncMock()

            service = EmbeddingService()

            # Create a long text (1000+ words)
            long_text = " ".join([f"word{i}" for i in range(1000)])

            embedding = await service.generate_embedding(long_text, use_cache=False)

            assert isinstance(embedding, list)
            assert len(embedding) == 384

            # Verify normalization
            norm = np.linalg.norm(embedding)
            assert abs(norm - 1.0) < 0.001
