"""
Integration tests for Elasticsearch client.

These tests require a running Elasticsearch instance.
Run with: pytest tests/test_elasticsearch_client_integration.py -m integration

Prerequisites:
- Elasticsearch running on localhost:9200 (or set ELASTICSEARCH_URL env var)
- No authentication required (or set credentials in env vars)
"""
import os
import pytest
import asyncio
from typing import List, Dict, Any

from app.utils.elasticsearch_client import ElasticsearchClient


# Check if Elasticsearch is available for integration tests
ELASTICSEARCH_AVAILABLE = os.getenv("ELASTICSEARCH_URL") is not None or True


@pytest.fixture
async def es_client():
    """Create Elasticsearch client for integration tests"""
    # Use environment variable or default to localhost
    es_url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
    
    client = ElasticsearchClient(
        hosts=[es_url],
        username=os.getenv("ELASTICSEARCH_USERNAME", ""),
        password=os.getenv("ELASTICSEARCH_PASSWORD", ""),
        verify_certs=False,
        timeout=30,
        max_retries=3
    )
    
    await client.initialize()
    
    # Check if Elasticsearch is actually available
    try:
        is_healthy = await client.health_check()
        if not is_healthy:
            pytest.skip("Elasticsearch is not healthy")
    except Exception as e:
        pytest.skip(f"Elasticsearch is not available: {e}")
    
    yield client
    
    # Cleanup: delete test indices
    try:
        await client.delete_index()
    except Exception:
        pass
    
    await client.close()


@pytest.fixture
def sample_documents() -> List[Dict[str, Any]]:
    """Generate sample documents for testing"""
    documents = []
    for i in range(50):
        documents.append({
            "chunk_id": f"chunk_{i}",
            "content": f"This is test content for document {i}. It contains information about machine learning and AI.",
            "title": f"Test Document {i}",
            "source_type": "test",
            "embedding": [0.1 + (i * 0.01)] * 384,  # Simple varying embedding
            "metadata": {
                "doc_number": i,
                "category": "test",
                "tags": ["test", "integration"]
            },
            "created_at": "2026-06-12T10:00:00Z"
        })
    return documents


@pytest.mark.integration
@pytest.mark.asyncio
class TestElasticsearchIntegrationConnection:
    """Integration tests for connection management"""

    async def test_connection_and_health_check(self, es_client):
        """Test connection initialization and health check"""
        assert es_client.client is not None
        
        # Check health
        is_healthy = await es_client.health_check()
        assert is_healthy is True


@pytest.mark.integration
@pytest.mark.asyncio
class TestElasticsearchIntegrationIndexManagement:
    """Integration tests for index management"""

    async def test_create_index_with_mapping(self, es_client):
        """Test creating index with correct mapping"""
        # Create index
        result = await es_client.create_index()
        assert result is True
        
        # Verify index exists
        index_name = es_client._get_index_name("knowledge_base")
        exists = await es_client.client.indices.exists(index=index_name)
        assert exists is True
        
        # Verify mapping
        mapping = await es_client.client.indices.get_mapping(index=index_name)
        index_mapping = mapping[index_name]["mappings"]["properties"]
        
        # Check all required fields
        assert "chunk_id" in index_mapping
        assert index_mapping["chunk_id"]["type"] == "keyword"
        
        assert "content" in index_mapping
        assert index_mapping["content"]["type"] == "text"
        
        assert "title" in index_mapping
        assert index_mapping["title"]["type"] == "text"
        
        assert "source_type" in index_mapping
        assert index_mapping["source_type"]["type"] == "keyword"
        
        assert "embedding" in index_mapping
        assert index_mapping["embedding"]["type"] == "dense_vector"
        assert index_mapping["embedding"]["dims"] == 384
        assert index_mapping["embedding"]["similarity"] == "cosine"
        
        assert "metadata" in index_mapping
        assert index_mapping["metadata"]["type"] == "object"
        
        assert "created_at" in index_mapping
        assert index_mapping["created_at"]["type"] == "date"

    async def test_delete_index(self, es_client):
        """Test index deletion"""
        # Create index first
        await es_client.create_index()
        
        # Delete index
        result = await es_client.delete_index()
        assert result is True
        
        # Verify index is deleted
        index_name = es_client._get_index_name("knowledge_base")
        exists = await es_client.client.indices.exists(index=index_name)
        assert exists is False

    async def test_create_index_idempotent(self, es_client):
        """Test that creating index twice is idempotent"""
        # Create index first time
        result1 = await es_client.create_index()
        assert result1 is True
        
        # Create index second time (should succeed without error)
        result2 = await es_client.create_index()
        assert result2 is True


@pytest.mark.integration
@pytest.mark.asyncio
class TestElasticsearchIntegrationBulkIndexing:
    """Integration tests for bulk indexing"""

    async def test_bulk_index_small_batch(self, es_client, sample_documents):
        """Test bulk indexing with small batch"""
        # Create index first
        await es_client.create_index()

        # Index documents
        small_batch = sample_documents[:10]
        result = await es_client.bulk_index(small_batch)

        assert result["success_count"] == 10
        assert result["failed_count"] == 0
        assert len(result["errors"]) == 0

        # Verify documents are indexed
        await asyncio.sleep(1)  # Wait for refresh
        index_name = es_client._get_index_name("knowledge_base")
        count_result = await es_client.client.count(index=index_name)
        assert count_result["count"] == 10

    async def test_bulk_index_with_batching(self, es_client):
        """Test bulk indexing with multiple batches"""
        # Create index first
        await es_client.create_index()

        # Create 2500 documents to test batching
        large_batch = [
            {
                "chunk_id": f"chunk_{i}",
                "content": f"Content {i}",
                "title": f"Title {i}",
                "source_type": "test",
                "embedding": [0.1] * 384,
                "metadata": {},
                "created_at": "2026-06-12T10:00:00Z"
            }
            for i in range(2500)
        ]

        # Index with batch_size=1000
        result = await es_client.bulk_index(large_batch, batch_size=1000)

        assert result["success_count"] == 2500
        assert result["failed_count"] == 0

        # Verify all documents are indexed
        await asyncio.sleep(2)  # Wait for refresh
        index_name = es_client._get_index_name("knowledge_base")
        count_result = await es_client.client.count(index=index_name)
        assert count_result["count"] == 2500


@pytest.mark.integration
@pytest.mark.asyncio
class TestElasticsearchIntegrationSearch:
    """Integration tests for search operations"""

    async def test_keyword_search(self, es_client, sample_documents):
        """Test keyword search"""
        # Setup: create index and index documents
        await es_client.create_index()
        await es_client.bulk_index(sample_documents)
        await asyncio.sleep(1)  # Wait for indexing

        # Search for "machine learning"
        results = await es_client.keyword_search("machine learning", size=10)

        assert len(results) > 0
        assert len(results) <= 10

        # Verify result structure
        first_result = results[0]
        assert "chunk_id" in first_result
        assert "score" in first_result
        assert "content" in first_result
        assert "title" in first_result

    async def test_semantic_search(self, es_client, sample_documents):
        """Test semantic search with kNN"""
        # Setup: create index and index documents
        await es_client.create_index()
        await es_client.bulk_index(sample_documents)
        await asyncio.sleep(1)  # Wait for indexing

        # Search with query embedding
        query_embedding = [0.15] * 384
        results = await es_client.semantic_search(query_embedding, size=5)

        assert len(results) > 0
        assert len(results) <= 5

        # Verify results are ordered by score
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    async def test_hybrid_search(self, es_client, sample_documents):
        """Test hybrid search combining keyword and semantic"""
        # Setup: create index and index documents
        await es_client.create_index()
        await es_client.bulk_index(sample_documents)
        await asyncio.sleep(1)  # Wait for indexing

        # Hybrid search
        query_embedding = [0.15] * 384
        results = await es_client.hybrid_search(
            query="machine learning",
            embedding=query_embedding,
            size=10,
            keyword_weight=0.5,
            semantic_weight=0.5
        )

        assert len(results) > 0
        assert len(results) <= 10

        # Verify result structure
        first_result = results[0]
        assert "chunk_id" in first_result
        assert "score" in first_result

    async def test_search_with_filters(self, es_client):
        """Test search with filters"""
        # Create index
        await es_client.create_index()

        # Index documents with different source types
        documents = [
            {
                "chunk_id": f"pdf_{i}",
                "content": f"PDF content {i}",
                "title": f"PDF {i}",
                "source_type": "pdf",
                "embedding": [0.1] * 384,
                "metadata": {},
                "created_at": "2026-06-12T10:00:00Z"
            }
            for i in range(5)
        ] + [
            {
                "chunk_id": f"web_{i}",
                "content": f"Web content {i}",
                "title": f"Web {i}",
                "source_type": "web",
                "embedding": [0.2] * 384,
                "metadata": {},
                "created_at": "2026-06-12T10:00:00Z"
            }
            for i in range(5)
        ]

        await es_client.bulk_index(documents)
        await asyncio.sleep(1)  # Wait for indexing

        # Search with filter for pdf only
        results = await es_client.keyword_search(
            query="content",
            filters={"source_type": "pdf"}
        )

        assert len(results) == 5
        for result in results:
            assert result["source_type"] == "pdf"


@pytest.mark.integration
@pytest.mark.asyncio
class TestElasticsearchIntegrationMonitoring:
    """Integration tests for monitoring and statistics"""

    async def test_get_index_health(self, es_client, sample_documents):
        """Test getting index health information"""
        # Create index and add documents
        await es_client.create_index()
        await es_client.bulk_index(sample_documents)
        await asyncio.sleep(1)

        # Get health info
        health = await es_client.get_index_health()

        assert health["status"] == "healthy"
        assert "document_count" in health
        assert health["document_count"] == 50
        assert "store_size_bytes" in health
        assert health["store_size_bytes"] > 0

    async def test_get_index_statistics(self, es_client, sample_documents):
        """Test getting detailed index statistics"""
        # Create index and add documents
        await es_client.create_index()
        await es_client.bulk_index(sample_documents)
        await asyncio.sleep(1)

        # Get statistics
        stats = await es_client.get_index_statistics()

        assert "index_name" in stats
        assert "primaries" in stats
        assert stats["primaries"]["docs_count"] == 50
        assert stats["primaries"]["indexing_total"] > 0

