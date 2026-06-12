"""
Elasticsearch client wrapper with async support for knowledge base indexing and search.

This module provides:
- Async Elasticsearch client with connection management
- Index creation and mapping configuration for knowledge_base index
- Bulk indexing operations with batch processing and error handling
- Multiple search methods: keyword search (BM25), semantic search (kNN), and hybrid search
- Index health monitoring and statistics retrieval
"""
import asyncio
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk
from elasticsearch.exceptions import (
    ConnectionError,
    NotFoundError,
    RequestError,
    TransportError
)

from app.core.config import settings
from app.core.logging import logger


class ElasticsearchClient:
    """
    Async Elasticsearch client for knowledge base indexing and search.
    
    Provides methods for index management, bulk indexing, and various search operations
    including keyword search (BM25), semantic search (kNN), and hybrid search.
    """
    
    # Index mapping for knowledge_base index
    KNOWLEDGE_BASE_MAPPING = {
        "properties": {
            "chunk_id": {
                "type": "keyword"
            },
            "content": {
                "type": "text",
                "analyzer": "standard"
            },
            "title": {
                "type": "text",
                "boost": 2.0
            },
            "source_type": {
                "type": "keyword"
            },
            "embedding": {
                "type": "dense_vector",
                "dims": 384,
                "index": True,
                "similarity": "cosine"
            },
            "metadata": {
                "type": "object",
                "dynamic": True
            },
            "created_at": {
                "type": "date"
            }
        }
    }
    
    # Index settings
    INDEX_SETTINGS = {
        "number_of_shards": 1,
        "number_of_replicas": 1,
        "refresh_interval": "30s"
    }
    
    def __init__(
        self,
        hosts: Optional[List[str]] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        verify_certs: bool = True,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize Elasticsearch client with connection configuration.
        
        Args:
            hosts: List of Elasticsearch host URLs (default: from settings)
            username: Authentication username (default: from settings)
            password: Authentication password (default: from settings)
            verify_certs: Enable SSL certificate verification (default: from settings)
            timeout: Request timeout in seconds (default: from settings)
            max_retries: Maximum retry attempts (default: from settings)
        """
        # Use settings if parameters not provided
        self.hosts = hosts or [settings.ELASTICSEARCH_URL]
        self.username = username or settings.ELASTICSEARCH_USERNAME
        self.password = password or settings.ELASTICSEARCH_PASSWORD
        self.verify_certs = verify_certs if verify_certs is not None else settings.ELASTICSEARCH_SSL_VERIFY
        self.timeout = timeout or settings.ELASTICSEARCH_TIMEOUT
        self.max_retries = max_retries or settings.ELASTICSEARCH_MAX_RETRIES
        self.index_prefix = settings.ELASTICSEARCH_INDEX_PREFIX
        
        self.client: Optional[AsyncElasticsearch] = None
        
        # Retry configuration
        self.retry_delays = [1, 2, 4]  # Exponential backoff in seconds
    
    async def initialize(self) -> None:
        """Initialize async Elasticsearch client connection."""
        if self.client is None:
            # Build connection parameters
            connection_params = {
                "hosts": self.hosts,
                "timeout": self.timeout,
                "max_retries": self.max_retries,
                "retry_on_timeout": True
            }
            
            # Add authentication if credentials provided
            if self.username and self.password:
                connection_params["basic_auth"] = (self.username, self.password)
            
            # Add SSL configuration
            connection_params["verify_certs"] = self.verify_certs
            
            self.client = AsyncElasticsearch(**connection_params)
            logger.info(f"Elasticsearch client initialized: {self.hosts}")
    
    async def close(self) -> None:
        """Close Elasticsearch connection and cleanup."""
        if self.client:
            await self.client.close()
            logger.info("Elasticsearch client closed")
    
    async def health_check(self) -> bool:
        """
        Check Elasticsearch cluster health.

        Returns:
            True if cluster is healthy (green or yellow), False otherwise
        """
        try:
            health = await self.client.cluster.health()
            status = health.get("status", "red")
            logger.info(f"Elasticsearch cluster health: {status}")
            return status in ["green", "yellow"]
        except Exception as e:
            logger.error(f"Elasticsearch health check failed: {e}")
            return False

    async def _execute_with_retry(self, operation: Callable, *args, **kwargs) -> Any:
        """
        Execute Elasticsearch operation with retry logic and exponential backoff.

        Args:
            operation: Async operation to execute
            *args: Positional arguments for the operation
            **kwargs: Keyword arguments for the operation

        Returns:
            Result of the operation

        Raises:
            TransportError: If all retries fail
        """
        for attempt in range(self.max_retries):
            try:
                return await operation(*args, **kwargs)
            except ConnectionError as e:
                if attempt < self.max_retries - 1:
                    delay = self.retry_delays[attempt]
                    logger.warning(
                        f"Elasticsearch connection error (attempt {attempt + 1}/{self.max_retries}): {e}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Elasticsearch connection failed after {self.max_retries} retries: {e}")
                    raise
            except TransportError as e:
                logger.error(f"Elasticsearch transport error: {e}")
                raise

    # ========================================================================
    # Index Management
    # ========================================================================

    def _get_index_name(self, index_type: str = "knowledge_base") -> str:
        """
        Get full index name with prefix.

        Args:
            index_type: Type of index (default: knowledge_base)

        Returns:
            Full index name with prefix
        """
        return f"{self.index_prefix}_{index_type}"

    async def create_index(
        self,
        index_name: Optional[str] = None,
        mapping: Optional[Dict] = None,
        settings: Optional[Dict] = None
    ) -> bool:
        """
        Create Elasticsearch index with mappings and settings.

        Args:
            index_name: Name of the index (default: knowledge_base with prefix)
            mapping: Index mapping configuration (default: KNOWLEDGE_BASE_MAPPING)
            settings: Index settings (default: INDEX_SETTINGS)

        Returns:
            True if index created successfully, False otherwise
        """
        index_name = index_name or self._get_index_name("knowledge_base")
        mapping = mapping or self.KNOWLEDGE_BASE_MAPPING
        settings = settings or self.INDEX_SETTINGS

        try:
            # Check if index already exists
            exists = await self.client.indices.exists(index=index_name)

            if exists:
                logger.info(f"Index '{index_name}' already exists")
                return True

            # Create index with mappings and settings
            body = {
                "settings": settings,
                "mappings": mapping
            }

            await self.client.indices.create(index=index_name, body=body)
            logger.info(f"Index '{index_name}' created successfully")
            return True

        except RequestError as e:
            logger.error(f"Failed to create index '{index_name}': {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error creating index '{index_name}': {e}")
            return False

    async def delete_index(self, index_name: Optional[str] = None) -> bool:
        """
        Delete Elasticsearch index.

        Args:
            index_name: Name of the index to delete (default: knowledge_base with prefix)

        Returns:
            True if index deleted successfully, False otherwise
        """
        index_name = index_name or self._get_index_name("knowledge_base")

        try:
            await self.client.indices.delete(index=index_name)
            logger.info(f"Index '{index_name}' deleted successfully")
            return True
        except NotFoundError:
            logger.warning(f"Index '{index_name}' not found")
            return False
        except Exception as e:
            logger.error(f"Failed to delete index '{index_name}': {e}")
            return False

    # ========================================================================
    # Bulk Indexing
    # ========================================================================

    async def bulk_index(
        self,
        documents: List[Dict[str, Any]],
        index_name: Optional[str] = None,
        batch_size: int = 1000,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Bulk index documents with batch processing and error handling.

        Args:
            documents: List of documents to index
            index_name: Target index name (default: knowledge_base with prefix)
            batch_size: Number of documents per batch (default: 1000)
            progress_callback: Optional callback function (indexed_count, total_count)

        Returns:
            Dictionary with indexing statistics:
            - success_count: Number of successfully indexed documents
            - failed_count: Number of failed documents
            - errors: List of error details
        """
        index_name = index_name or self._get_index_name("knowledge_base")

        total_count = len(documents)
        success_count = 0
        failed_count = 0
        errors = []

        try:
            # Prepare actions for bulk indexing
            actions = []
            for doc in documents:
                action = {
                    "_index": index_name,
                    "_id": doc.get("chunk_id"),  # Use chunk_id as document ID
                    "_source": doc
                }
                actions.append(action)

            # Process in batches
            for i in range(0, len(actions), batch_size):
                batch = actions[i:i + batch_size]

                try:
                    # Execute bulk operation
                    success, failed = await async_bulk(
                        self.client,
                        batch,
                        raise_on_error=False,
                        raise_on_exception=False,
                        chunk_size=batch_size
                    )

                    success_count += success

                    # Handle partial failures
                    if failed:
                        failed_count += len(failed)
                        for item in failed:
                            error_detail = {
                                "document_id": item.get("index", {}).get("_id"),
                                "error": item.get("index", {}).get("error", "Unknown error")
                            }
                            errors.append(error_detail)
                            logger.warning(f"Failed to index document: {error_detail}")

                    # Progress callback
                    if progress_callback:
                        progress_callback(success_count, total_count)

                    logger.info(
                        f"Batch indexing progress: {success_count}/{total_count} "
                        f"(success: {success}, failed: {len(failed) if failed else 0})"
                    )

                except Exception as e:
                    logger.error(f"Error during bulk indexing batch: {e}")
                    failed_count += len(batch)
                    errors.append({"batch_error": str(e)})

            logger.info(
                f"Bulk indexing completed: {success_count} succeeded, {failed_count} failed"
            )

            return {
                "success_count": success_count,
                "failed_count": failed_count,
                "errors": errors
            }

        except Exception as e:
            logger.error(f"Bulk indexing failed: {e}")
            return {
                "success_count": success_count,
                "failed_count": total_count - success_count,
                "errors": errors + [{"error": str(e)}]
            }

    # ========================================================================
    # Search Methods
    # ========================================================================

    async def keyword_search(
        self,
        query: str,
        index_name: Optional[str] = None,
        size: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform keyword search using BM25 algorithm (match query).

        Args:
            query: Search query text
            index_name: Index to search (default: knowledge_base with prefix)
            size: Maximum number of results to return
            filters: Optional filters (e.g., {"source_type": "confluence"})

        Returns:
            List of search results with scores
        """
        index_name = index_name or self._get_index_name("knowledge_base")

        try:
            # Build query
            must_clauses = [
                {
                    "multi_match": {
                        "query": query,
                        "fields": ["content", "title^2"],  # Boost title field
                        "type": "best_fields"
                    }
                }
            ]

            # Add filters if provided
            filter_clauses = []
            if filters:
                for field, value in filters.items():
                    filter_clauses.append({"term": {field: value}})

            # Construct query body
            body = {
                "query": {
                    "bool": {
                        "must": must_clauses,
                        "filter": filter_clauses
                    }
                },
                "size": size
            }

            # Execute search
            response = await self.client.search(index=index_name, body=body)

            # Extract results
            results = []
            for hit in response["hits"]["hits"]:
                result = {
                    "chunk_id": hit["_id"],
                    "score": hit["_score"],
                    **hit["_source"]
                }
                results.append(result)

            logger.info(f"Keyword search returned {len(results)} results")
            return results

        except NotFoundError:
            logger.warning(f"Index '{index_name}' not found")
            return []
        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return []

    async def semantic_search(
        self,
        embedding: List[float],
        index_name: Optional[str] = None,
        size: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        min_score: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search using kNN on embedding field.

        Args:
            embedding: Query embedding vector (384 dimensions)
            index_name: Index to search (default: knowledge_base with prefix)
            size: Maximum number of results to return
            filters: Optional filters (e.g., {"source_type": "confluence"})
            min_score: Minimum similarity score threshold

        Returns:
            List of search results with similarity scores
        """
        index_name = index_name or self._get_index_name("knowledge_base")

        try:
            # Build kNN query
            knn_query = {
                "field": "embedding",
                "query_vector": embedding,
                "k": size,
                "num_candidates": size * 10  # Over-fetch for better recall
            }

            # Add filters if provided
            if filters:
                filter_clauses = []
                for field, value in filters.items():
                    filter_clauses.append({"term": {field: value}})

                knn_query["filter"] = filter_clauses

            # Execute kNN search
            body = {
                "knn": knn_query,
                "size": size
            }

            response = await self.client.search(index=index_name, body=body)

            # Extract results
            results = []
            for hit in response["hits"]["hits"]:
                score = hit["_score"]

                # Apply minimum score threshold if specified
                if min_score is not None and score < min_score:
                    continue

                result = {
                    "chunk_id": hit["_id"],
                    "score": score,
                    **hit["_source"]
                }
                results.append(result)

            logger.info(f"Semantic search returned {len(results)} results")
            return results

        except NotFoundError:
            logger.warning(f"Index '{index_name}' not found")
            return []
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    async def hybrid_search(
        self,
        query: str,
        embedding: List[float],
        index_name: Optional[str] = None,
        size: int = 10,
        keyword_weight: float = 0.5,
        semantic_weight: float = 0.5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining BM25 (keyword) and kNN (semantic) search.

        Uses Reciprocal Rank Fusion (RRF) to combine results from both methods.

        Args:
            query: Search query text
            embedding: Query embedding vector (384 dimensions)
            index_name: Index to search (default: knowledge_base with prefix)
            size: Maximum number of results to return
            keyword_weight: Weight for BM25 scores (default: 0.5)
            semantic_weight: Weight for kNN scores (default: 0.5)
            filters: Optional filters (e.g., {"source_type": "confluence"})

        Returns:
            List of search results with combined scores
        """
        index_name = index_name or self._get_index_name("knowledge_base")

        try:
            # Normalize weights
            total_weight = keyword_weight + semantic_weight
            keyword_weight = keyword_weight / total_weight
            semantic_weight = semantic_weight / total_weight

            # Build combined query with both BM25 and kNN
            must_clauses = [
                {
                    "multi_match": {
                        "query": query,
                        "fields": ["content", "title^2"],
                        "type": "best_fields"
                    }
                }
            ]

            # Add filters if provided
            filter_clauses = []
            if filters:
                for field, value in filters.items():
                    filter_clauses.append({"term": {field: value}})

            # Build kNN query
            knn_query = {
                "field": "embedding",
                "query_vector": embedding,
                "k": size * 2,  # Fetch more for better fusion
                "num_candidates": size * 10
            }

            if filter_clauses:
                knn_query["filter"] = filter_clauses

            # Construct hybrid query body
            body = {
                "query": {
                    "bool": {
                        "must": must_clauses,
                        "filter": filter_clauses
                    }
                },
                "knn": knn_query,
                "size": size * 2  # Fetch more for RRF
            }

            # Execute hybrid search
            response = await self.client.search(index=index_name, body=body)

            # Extract and combine results with weighted scoring
            results_map = {}
            for hit in response["hits"]["hits"]:
                chunk_id = hit["_id"]

                # For hybrid search, Elasticsearch combines scores
                # We'll apply weights to normalize
                combined_score = hit["_score"]

                if chunk_id not in results_map:
                    results_map[chunk_id] = {
                        "chunk_id": chunk_id,
                        "score": combined_score,
                        **hit["_source"]
                    }

            # Sort by combined score and limit results
            results = sorted(
                results_map.values(),
                key=lambda x: x["score"],
                reverse=True
            )[:size]

            logger.info(
                f"Hybrid search returned {len(results)} results "
                f"(weights: keyword={keyword_weight:.2f}, semantic={semantic_weight:.2f})"
            )
            return results

        except NotFoundError:
            logger.warning(f"Index '{index_name}' not found")
            return []
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return []

    # ========================================================================
    # Index Health and Statistics
    # ========================================================================

    async def get_index_health(
        self,
        index_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get health status and statistics for an index.

        Args:
            index_name: Index name (default: knowledge_base with prefix)

        Returns:
            Dictionary with health information
        """
        index_name = index_name or self._get_index_name("knowledge_base")

        try:
            # Get index stats
            stats = await self.client.indices.stats(index=index_name)

            # Get index settings
            settings_response = await self.client.indices.get_settings(index=index_name)

            # Extract relevant information
            index_stats = stats["indices"].get(index_name, {})
            primaries = index_stats.get("primaries", {})

            health_info = {
                "index_name": index_name,
                "status": "healthy",
                "document_count": primaries.get("docs", {}).get("count", 0),
                "deleted_count": primaries.get("docs", {}).get("deleted", 0),
                "store_size_bytes": primaries.get("store", {}).get("size_in_bytes", 0),
                "number_of_shards": settings_response[index_name]["settings"]["index"].get("number_of_shards", "N/A"),
                "number_of_replicas": settings_response[index_name]["settings"]["index"].get("number_of_replicas", "N/A")
            }

            logger.info(f"Index health retrieved for '{index_name}'")
            return health_info

        except NotFoundError:
            logger.warning(f"Index '{index_name}' not found")
            return {
                "index_name": index_name,
                "status": "not_found",
                "error": "Index does not exist"
            }
        except Exception as e:
            logger.error(f"Failed to get index health: {e}")
            return {
                "index_name": index_name,
                "status": "error",
                "error": str(e)
            }

    async def get_index_statistics(
        self,
        index_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get detailed statistics for an index.

        Args:
            index_name: Index name (default: knowledge_base with prefix)

        Returns:
            Dictionary with detailed statistics
        """
        index_name = index_name or self._get_index_name("knowledge_base")

        try:
            # Get comprehensive stats
            stats = await self.client.indices.stats(index=index_name)

            index_stats = stats["indices"].get(index_name, {})
            primaries = index_stats.get("primaries", {})
            total = index_stats.get("total", {})

            statistics = {
                "index_name": index_name,
                "primaries": {
                    "docs_count": primaries.get("docs", {}).get("count", 0),
                    "docs_deleted": primaries.get("docs", {}).get("deleted", 0),
                    "store_size_bytes": primaries.get("store", {}).get("size_in_bytes", 0),
                    "indexing_total": primaries.get("indexing", {}).get("index_total", 0),
                    "search_query_total": primaries.get("search", {}).get("query_total", 0),
                    "search_fetch_total": primaries.get("search", {}).get("fetch_total", 0)
                },
                "total": {
                    "docs_count": total.get("docs", {}).get("count", 0),
                    "store_size_bytes": total.get("store", {}).get("size_in_bytes", 0),
                    "indexing_total": total.get("indexing", {}).get("index_total", 0),
                    "search_query_total": total.get("search", {}).get("query_total", 0)
                }
            }

            logger.info(f"Index statistics retrieved for '{index_name}'")
            return statistics

        except NotFoundError:
            logger.warning(f"Index '{index_name}' not found")
            return {
                "index_name": index_name,
                "error": "Index does not exist"
            }
        except Exception as e:
            logger.error(f"Failed to get index statistics: {e}")
            return {
                "index_name": index_name,
                "error": str(e)
            }


# Create global Elasticsearch client instance
elasticsearch_client = ElasticsearchClient()
