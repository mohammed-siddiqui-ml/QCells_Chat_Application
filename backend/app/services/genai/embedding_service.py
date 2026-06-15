"""
Embedding service for generating text embeddings using local or cloud models.

This module provides:
- Support for both local (sentence-transformers) and OpenAI embeddings
- Batch embedding generation for documents (32 texts at once)
- Query embedding generation with Redis caching
- Model switching based on EMBEDDING_MODEL environment variable
- Normalized embeddings for cosine similarity
"""
import hashlib
import numpy as np
from typing import List, Optional, Union
from openai import AsyncOpenAI

from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.core.logging import logger
from app.utils.redis_client import redis_client


class EmbeddingError(Exception):
    """Base exception for embedding generation errors"""
    pass


class EmbeddingService:
    """
    Service for generating text embeddings using local or cloud models.
    
    Supports:
    - Local: sentence-transformers (all-MiniLM-L6-v2, 384 dimensions)
    - Cloud: OpenAI (text-embedding-3-small or ada-002)
    """
    
    def __init__(self):
        """Initialize embedding service with model based on configuration."""
        self.model_type = settings.EMBEDDING_MODEL.lower()
        self.batch_size = settings.EMBEDDING_BATCH_SIZE
        self.cache_ttl = settings.EMBEDDING_CACHE_TTL
        
        # Initialize appropriate model
        self.local_model: Optional[SentenceTransformer] = None
        self.openai_client: Optional[AsyncOpenAI] = None
        
        if self.model_type == "local":
            self._initialize_local_model()
            self.embedding_dimension = 384
        elif self.model_type == "openai":
            self._initialize_openai_client()
            # OpenAI ada-002 produces 1536 dimensions, text-embedding-3-small can be 1536
            self.embedding_dimension = 1536
        else:
            raise ValueError(f"Unsupported EMBEDDING_MODEL: {self.model_type}. Use 'local' or 'openai'")
        
        logger.info(f"EmbeddingService initialized with model_type={self.model_type}, dimension={self.embedding_dimension}")
    
    def _initialize_local_model(self) -> None:
        """Initialize local sentence-transformers model."""
        try:
            model_name = settings.LOCAL_EMBEDDING_MODEL
            logger.info(f"Loading local embedding model: {model_name}")
            self.local_model = SentenceTransformer(model_name)
            logger.info(f"Local embedding model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load local embedding model: {e}")
            raise EmbeddingError(f"Failed to initialize local embedding model: {e}")
    
    def _initialize_openai_client(self) -> None:
        """Initialize OpenAI client for embeddings."""
        try:
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY not configured")
            self.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            logger.info("OpenAI client initialized for embeddings")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise EmbeddingError(f"Failed to initialize OpenAI client: {e}")
    
    def _normalize_embedding(self, embedding: Union[List[float], np.ndarray]) -> List[float]:
        """
        Normalize embedding to unit length for cosine similarity.
        
        Args:
            embedding: Input embedding vector
            
        Returns:
            Normalized embedding as list
        """
        embedding_array = np.array(embedding)
        norm = np.linalg.norm(embedding_array)
        if norm == 0:
            logger.warning("Zero-norm embedding detected, returning as-is")
            return embedding_array.tolist()
        normalized = embedding_array / norm
        return normalized.tolist()
    
    def _get_cache_key(self, text: str) -> str:
        """
        Generate cache key from text hash.
        
        Args:
            text: Input text
            
        Returns:
            Cache key string
        """
        text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
        return f"embedding:{self.model_type}:{text_hash}"

    async def generate_embedding(
        self,
        text: str,
        use_cache: bool = True
    ) -> List[float]:
        """
        Generate embedding for a single text (optimized for queries).

        Args:
            text: Input text to embed
            use_cache: Whether to use Redis cache (default: True)

        Returns:
            Normalized embedding vector

        Raises:
            EmbeddingError: If embedding generation fails
        """
        if not text or not text.strip():
            raise EmbeddingError("Cannot generate embedding for empty text")

        # Check cache first if enabled
        if use_cache:
            cache_key = self._get_cache_key(text)
            try:
                cached_embedding = await redis_client.get_cached_query(cache_key)
                if cached_embedding:
                    logger.debug(f"Cache hit for embedding: {cache_key[:50]}...")
                    return cached_embedding
            except Exception as e:
                logger.warning(f"Failed to retrieve cached embedding: {e}")

        # Generate new embedding
        try:
            if self.model_type == "local":
                embedding = await self._generate_local_embedding(text)
            else:  # openai
                embedding = await self._generate_openai_embedding(text)

            # Normalize
            normalized_embedding = self._normalize_embedding(embedding)

            # Cache if enabled
            if use_cache:
                try:
                    cache_key = self._get_cache_key(text)
                    await redis_client.set_cached_query(
                        cache_key,
                        normalized_embedding,
                        ttl=self.cache_ttl
                    )
                    logger.debug(f"Cached embedding: {cache_key[:50]}...")
                except Exception as e:
                    logger.warning(f"Failed to cache embedding: {e}")

            return normalized_embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise EmbeddingError(f"Embedding generation failed: {e}")

    async def _generate_local_embedding(self, text: str) -> List[float]:
        """
        Generate embedding using local sentence-transformers model.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        if not self.local_model:
            raise EmbeddingError("Local model not initialized")

        try:
            # encode returns numpy array
            embedding = self.local_model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Local embedding generation failed: {e}")
            raise EmbeddingError(f"Local embedding failed: {e}")

    async def _generate_openai_embedding(self, text: str) -> List[float]:
        """
        Generate embedding using OpenAI API.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        if not self.openai_client:
            raise EmbeddingError("OpenAI client not initialized")

        try:
            response = await self.openai_client.embeddings.create(
                model=settings.OPENAI_EMBEDDING_MODEL,
                input=text
            )
            embedding = response.data[0].embedding
            return embedding
        except Exception as e:
            logger.error(f"OpenAI embedding generation failed: {e}")
            raise EmbeddingError(f"OpenAI embedding failed: {e}")

    async def generate_batch_embeddings(
        self,
        texts: List[str],
        use_cache: bool = False
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches (for document processing).

        Processes texts in batches of 32 for efficiency.

        Args:
            texts: List of texts to embed
            use_cache: Whether to use Redis cache (default: False for batch operations)

        Returns:
            List of normalized embedding vectors

        Raises:
            EmbeddingError: If embedding generation fails
        """
        if not texts:
            return []

        # Filter out empty texts
        valid_texts = [text for text in texts if text and text.strip()]
        if not valid_texts:
            raise EmbeddingError("No valid texts to embed")

        embeddings = []

        # Process in batches
        for i in range(0, len(valid_texts), self.batch_size):
            batch = valid_texts[i:i + self.batch_size]
            batch_embeddings = await self._generate_batch(batch, use_cache)
            embeddings.extend(batch_embeddings)
            logger.debug(f"Processed batch {i//self.batch_size + 1}/{(len(valid_texts)-1)//self.batch_size + 1}")

        return embeddings

    async def _generate_batch(
        self,
        texts: List[str],
        use_cache: bool
    ) -> List[List[float]]:
        """
        Generate embeddings for a single batch.

        Args:
            texts: Batch of texts (up to batch_size)
            use_cache: Whether to use cache

        Returns:
            List of normalized embeddings
        """
        try:
            if self.model_type == "local":
                embeddings = await self._generate_local_batch_embeddings(texts)
            else:  # openai
                embeddings = await self._generate_openai_batch_embeddings(texts)

            # Normalize all embeddings
            normalized_embeddings = [self._normalize_embedding(emb) for emb in embeddings]

            return normalized_embeddings

        except Exception as e:
            logger.error(f"Batch embedding generation failed: {e}")
            raise EmbeddingError(f"Batch embedding failed: {e}")

    async def _generate_local_batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings using local model for a batch.

        Args:
            texts: List of texts

        Returns:
            List of embedding vectors
        """
        if not self.local_model:
            raise EmbeddingError("Local model not initialized")

        try:
            # encode handles batch processing efficiently
            embeddings = self.local_model.encode(texts, convert_to_numpy=True)
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            logger.error(f"Local batch embedding generation failed: {e}")
            raise EmbeddingError(f"Local batch embedding failed: {e}")

    async def _generate_openai_batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings using OpenAI API for a batch.

        Args:
            texts: List of texts

        Returns:
            List of embedding vectors
        """
        if not self.openai_client:
            raise EmbeddingError("OpenAI client not initialized")

        try:
            response = await self.openai_client.embeddings.create(
                model=settings.OPENAI_EMBEDDING_MODEL,
                input=texts
            )
            embeddings = [item.embedding for item in response.data]
            return embeddings
        except Exception as e:
            logger.error(f"OpenAI batch embedding generation failed: {e}")
            raise EmbeddingError(f"OpenAI batch embedding failed: {e}")

    async def clear_cache(self) -> int:
        """
        Clear all cached embeddings for this model type.

        Returns:
            Number of cache entries cleared
        """
        try:
            pattern = f"embedding:{self.model_type}:*"
            count = await redis_client.clear_cache_pattern(pattern)
            logger.info(f"Cleared {count} cached embeddings for model type: {self.model_type}")
            return count
        except Exception as e:
            logger.error(f"Failed to clear embedding cache: {e}")
            return 0


# Global embedding service instance - lazy initialization to avoid issues during testing
import sys
_embedding_service_instance: Optional[EmbeddingService] = None

def get_embedding_service() -> EmbeddingService:
    """Get or create the global embedding service instance."""
    global _embedding_service_instance
    if _embedding_service_instance is None:
        _embedding_service_instance = EmbeddingService()
    return _embedding_service_instance

# For backward compatibility, create instance only if not running under pytest
# This prevents hanging during test collection when importing the module
# Check if pytest is in sys.modules (indicates we're running tests)
if 'pytest' not in sys.modules:
    embedding_service = EmbeddingService()
else:
    # In testing mode, create a placeholder that will be replaced by fixtures
    embedding_service = None  # type: ignore
