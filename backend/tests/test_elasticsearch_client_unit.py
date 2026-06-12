"""
Unit tests for Elasticsearch client with mocked connections.

Tests cover:
- Connection initialization and configuration
- Index management (create, delete)
- Bulk indexing logic and batch processing
- Search query construction
- Error handling and retry logic
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from elasticsearch.exceptions import ConnectionError, NotFoundError, RequestError

from app.utils.elasticsearch_client import ElasticsearchClient


@pytest.mark.unit
class TestElasticsearchClientInit:
    """Test client initialization and configuration"""

    def test_init_default_config(self):
        """Test initialization with default settings"""
        with patch('app.utils.elasticsearch_client.settings') as mock_settings:
            mock_settings.ELASTICSEARCH_URL = "http://localhost:9200"
            mock_settings.ELASTICSEARCH_USERNAME = ""
            mock_settings.ELASTICSEARCH_PASSWORD = ""
            mock_settings.ELASTICSEARCH_SSL_VERIFY = True
            mock_settings.ELASTICSEARCH_TIMEOUT = 30
            mock_settings.ELASTICSEARCH_MAX_RETRIES = 3
            mock_settings.ELASTICSEARCH_INDEX_PREFIX = "test"

            client = ElasticsearchClient()

            assert client.hosts == ["http://localhost:9200"]
            assert client.timeout == 30
            assert client.max_retries == 3
            assert client.index_prefix == "test"

    def test_init_custom_config(self):
        """Test initialization with custom parameters"""
        client = ElasticsearchClient(
            hosts=["http://custom:9200"],
            username="user",
            password="pass",
            timeout=60,
            max_retries=5
        )

        assert client.hosts == ["http://custom:9200"]
        assert client.username == "user"
        assert client.password == "pass"
        assert client.timeout == 60
        assert client.max_retries == 5


@pytest.mark.unit
class TestElasticsearchClientConnection:
    """Test connection management"""

    @pytest.mark.asyncio
    async def test_initialize_connection(self):
        """Test client initialization"""
        with patch('app.utils.elasticsearch_client.settings') as mock_settings:
            mock_settings.ELASTICSEARCH_URL = "http://localhost:9200"
            mock_settings.ELASTICSEARCH_USERNAME = ""
            mock_settings.ELASTICSEARCH_PASSWORD = ""
            mock_settings.ELASTICSEARCH_SSL_VERIFY = False
            mock_settings.ELASTICSEARCH_TIMEOUT = 30
            mock_settings.ELASTICSEARCH_MAX_RETRIES = 3
            mock_settings.ELASTICSEARCH_INDEX_PREFIX = "test"

            with patch('app.utils.elasticsearch_client.AsyncElasticsearch') as mock_es:
                client = ElasticsearchClient()
                await client.initialize()

                assert client.client is not None
                mock_es.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_connection(self):
        """Test client cleanup"""
        with patch('app.utils.elasticsearch_client.settings') as mock_settings:
            mock_settings.ELASTICSEARCH_URL = "http://localhost:9200"
            mock_settings.ELASTICSEARCH_USERNAME = ""
            mock_settings.ELASTICSEARCH_PASSWORD = ""
            mock_settings.ELASTICSEARCH_SSL_VERIFY = False
            mock_settings.ELASTICSEARCH_TIMEOUT = 30
            mock_settings.ELASTICSEARCH_MAX_RETRIES = 3
            mock_settings.ELASTICSEARCH_INDEX_PREFIX = "test"

            with patch('app.utils.elasticsearch_client.AsyncElasticsearch') as mock_es:
                mock_client = AsyncMock()
                mock_es.return_value = mock_client

                client = ElasticsearchClient()
                await client.initialize()
                await client.close()

                mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        """Test health check with healthy cluster"""
        with patch('app.utils.elasticsearch_client.settings') as mock_settings:
            mock_settings.ELASTICSEARCH_URL = "http://localhost:9200"
            mock_settings.ELASTICSEARCH_USERNAME = ""
            mock_settings.ELASTICSEARCH_PASSWORD = ""
            mock_settings.ELASTICSEARCH_SSL_VERIFY = False
            mock_settings.ELASTICSEARCH_TIMEOUT = 30
            mock_settings.ELASTICSEARCH_MAX_RETRIES = 3
            mock_settings.ELASTICSEARCH_INDEX_PREFIX = "test"

            with patch('app.utils.elasticsearch_client.AsyncElasticsearch') as mock_es:
                mock_client = AsyncMock()
                mock_client.cluster.health.return_value = {"status": "green"}
                mock_es.return_value = mock_client

                client = ElasticsearchClient()
                await client.initialize()
                
                result = await client.health_check()
                assert result is True

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self):
        """Test health check with unhealthy cluster"""
        with patch('app.utils.elasticsearch_client.settings') as mock_settings:
            mock_settings.ELASTICSEARCH_URL = "http://localhost:9200"
            mock_settings.ELASTICSEARCH_USERNAME = ""
            mock_settings.ELASTICSEARCH_PASSWORD = ""
            mock_settings.ELASTICSEARCH_SSL_VERIFY = False
            mock_settings.ELASTICSEARCH_TIMEOUT = 30
            mock_settings.ELASTICSEARCH_MAX_RETRIES = 3
            mock_settings.ELASTICSEARCH_INDEX_PREFIX = "test"

            with patch('app.utils.elasticsearch_client.AsyncElasticsearch') as mock_es:
                mock_client = AsyncMock()
                mock_client.cluster.health.side_effect = Exception("Connection failed")
                mock_es.return_value = mock_client

                client = ElasticsearchClient()
                await client.initialize()
                
                result = await client.health_check()
                assert result is False


@pytest.mark.unit
class TestElasticsearchIndexManagement:
    """Test index management operations"""

    @pytest.mark.asyncio
    async def test_create_index_success(self):
        """Test successful index creation"""
        with patch('app.utils.elasticsearch_client.settings') as mock_settings:
            mock_settings.ELASTICSEARCH_URL = "http://localhost:9200"
            mock_settings.ELASTICSEARCH_USERNAME = ""
            mock_settings.ELASTICSEARCH_PASSWORD = ""
            mock_settings.ELASTICSEARCH_SSL_VERIFY = False
            mock_settings.ELASTICSEARCH_TIMEOUT = 30
            mock_settings.ELASTICSEARCH_MAX_RETRIES = 3
            mock_settings.ELASTICSEARCH_INDEX_PREFIX = "test"

            with patch('app.utils.elasticsearch_client.AsyncElasticsearch') as mock_es:
                mock_client = AsyncMock()
                mock_client.indices.exists.return_value = False
                mock_client.indices.create.return_value = {"acknowledged": True}
                mock_es.return_value = mock_client

                client = ElasticsearchClient()
                await client.initialize()

                result = await client.create_index()
                assert result is True
                mock_client.indices.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_index_already_exists(self):
        """Test creating index that already exists"""
        with patch('app.utils.elasticsearch_client.settings') as mock_settings:
            mock_settings.ELASTICSEARCH_URL = "http://localhost:9200"
            mock_settings.ELASTICSEARCH_USERNAME = ""
            mock_settings.ELASTICSEARCH_PASSWORD = ""
            mock_settings.ELASTICSEARCH_SSL_VERIFY = False
            mock_settings.ELASTICSEARCH_TIMEOUT = 30
            mock_settings.ELASTICSEARCH_MAX_RETRIES = 3
            mock_settings.ELASTICSEARCH_INDEX_PREFIX = "test"

            with patch('app.utils.elasticsearch_client.AsyncElasticsearch') as mock_es:
                mock_client = AsyncMock()
                mock_client.indices.exists.return_value = True
                mock_es.return_value = mock_client

                client = ElasticsearchClient()
                await client.initialize()

                result = await client.create_index()
                assert result is True
                mock_client.indices.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_index_success(self):
        """Test successful index deletion"""
        with patch('app.utils.elasticsearch_client.settings') as mock_settings:
            mock_settings.ELASTICSEARCH_URL = "http://localhost:9200"
            mock_settings.ELASTICSEARCH_USERNAME = ""
            mock_settings.ELASTICSEARCH_PASSWORD = ""
            mock_settings.ELASTICSEARCH_SSL_VERIFY = False
            mock_settings.ELASTICSEARCH_TIMEOUT = 30
            mock_settings.ELASTICSEARCH_MAX_RETRIES = 3
            mock_settings.ELASTICSEARCH_INDEX_PREFIX = "test"

            with patch('app.utils.elasticsearch_client.AsyncElasticsearch') as mock_es:
                mock_client = AsyncMock()
                mock_client.indices.delete.return_value = {"acknowledged": True}
                mock_es.return_value = mock_client

                client = ElasticsearchClient()
                await client.initialize()

                result = await client.delete_index()
                assert result is True
                mock_client.indices.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_index_not_found(self):
        """Test deleting non-existent index"""
        with patch('app.utils.elasticsearch_client.settings') as mock_settings:
            mock_settings.ELASTICSEARCH_URL = "http://localhost:9200"
            mock_settings.ELASTICSEARCH_USERNAME = ""
            mock_settings.ELASTICSEARCH_PASSWORD = ""
            mock_settings.ELASTICSEARCH_SSL_VERIFY = False
            mock_settings.ELASTICSEARCH_TIMEOUT = 30
            mock_settings.ELASTICSEARCH_MAX_RETRIES = 3
            mock_settings.ELASTICSEARCH_INDEX_PREFIX = "test"

            with patch('app.utils.elasticsearch_client.AsyncElasticsearch') as mock_es:
                mock_client = AsyncMock()
                mock_client.indices.delete.side_effect = NotFoundError("Index not found", None, None)
                mock_es.return_value = mock_client

                client = ElasticsearchClient()
                await client.initialize()

                result = await client.delete_index()
                assert result is False


@pytest.mark.unit
class TestElasticsearchBulkIndexing:
    """Test bulk indexing operations"""

    @pytest.mark.asyncio
    async def test_bulk_index_small_batch(self):
        """Test bulk indexing with small batch"""
        with patch('app.utils.elasticsearch_client.settings') as mock_settings:
            mock_settings.ELASTICSEARCH_URL = "http://localhost:9200"
            mock_settings.ELASTICSEARCH_USERNAME = ""
            mock_settings.ELASTICSEARCH_PASSWORD = ""
            mock_settings.ELASTICSEARCH_SSL_VERIFY = False
            mock_settings.ELASTICSEARCH_TIMEOUT = 30
            mock_settings.ELASTICSEARCH_MAX_RETRIES = 3
            mock_settings.ELASTICSEARCH_INDEX_PREFIX = "test"

            with patch('app.utils.elasticsearch_client.AsyncElasticsearch') as mock_es:
                with patch('app.utils.elasticsearch_client.async_bulk') as mock_bulk:
                    mock_client = AsyncMock()
                    mock_es.return_value = mock_client
                    mock_bulk.return_value = (10, [])  # 10 success, 0 failed

                    client = ElasticsearchClient()
                    await client.initialize()

                    documents = [
                        {
                            "chunk_id": f"chunk_{i}",
                            "content": f"Content {i}",
                            "title": f"Title {i}",
                            "source_type": "test",
                            "embedding": [0.1] * 384,
                            "metadata": {},
                            "created_at": "2026-06-12T10:00:00Z"
                        }
                        for i in range(10)
                    ]

                    result = await client.bulk_index(documents)

                    assert result["success_count"] == 10
                    assert result["failed_count"] == 0
                    assert len(result["errors"]) == 0
