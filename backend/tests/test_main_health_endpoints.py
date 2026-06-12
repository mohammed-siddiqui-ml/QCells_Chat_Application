"""
Tests for FastAPI application health check endpoints (task-015)
Tests TC-B1, TC-B2, TC-B3, TC-B4, TC-B5
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    return TestClient(app)


class TestHealthEndpoints:
    """Test suite for health check endpoints."""

    def test_health_endpoint_basic(self, client):
        """
        TC-B1: Health endpoint returns success when app is running
        """
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_ready_endpoint_all_services_healthy(self, client):
        """
        TC-B2: Ready endpoint returns 200 when all services are healthy
        """
        # Mock all service health checks to return healthy
        # Create mock connection that will be returned by engine.connect()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        # Create a mock for engine that returns the connection
        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch("app.main.engine", mock_engine), \
             patch("app.main.redis_client.health_check", new_callable=AsyncMock) as mock_redis, \
             patch("app.main.elasticsearch_client.health_check", new_callable=AsyncMock) as mock_es:

            mock_redis.return_value = True
            mock_es.return_value = True

            response = client.get("/ready")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert "services" in data
            assert data["services"]["postgresql"]["status"] == "healthy"
            assert data["services"]["redis"]["status"] == "healthy"
            assert data["services"]["elasticsearch"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_ready_endpoint_postgresql_unavailable(self, client):
        """
        TC-B3: Ready endpoint returns 503 when PostgreSQL is unavailable
        """
        # Mock connection that raises error
        mock_conn = AsyncMock()
        mock_conn.__aenter__.side_effect = OperationalError("Connection failed", None, None)

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch("app.main.engine", mock_engine), \
             patch("app.main.redis_client.health_check", new_callable=AsyncMock) as mock_redis, \
             patch("app.main.elasticsearch_client.health_check", new_callable=AsyncMock) as mock_es:

            # PostgreSQL fails, others succeed
            mock_redis.return_value = True
            mock_es.return_value = True

            response = client.get("/ready")

            assert response.status_code == 503
            data = response.json()
            # HTTPException handler wraps detail in error.message
            assert "error" in data
            assert data["error"]["message"]["status"] == "not_ready"
            assert data["error"]["message"]["services"]["postgresql"]["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_ready_endpoint_redis_unavailable(self, client):
        """
        TC-B4: Ready endpoint returns 503 when Redis is unavailable
        """
        # Mock healthy database connection
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch("app.main.engine", mock_engine), \
             patch("app.main.redis_client.health_check", new_callable=AsyncMock) as mock_redis, \
             patch("app.main.elasticsearch_client.health_check", new_callable=AsyncMock) as mock_es:

            # Setup mocks - Redis fails
            mock_redis.return_value = False
            mock_es.return_value = True

            response = client.get("/ready")

            assert response.status_code == 503
            data = response.json()
            # HTTPException handler wraps detail in error.message
            assert data["error"]["message"]["status"] == "not_ready"
            assert data["error"]["message"]["services"]["redis"]["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_ready_endpoint_elasticsearch_unavailable(self, client):
        """
        TC-B5: Ready endpoint returns 503 when Elasticsearch is unavailable
        """
        # Mock healthy database connection
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch("app.main.engine", mock_engine), \
             patch("app.main.redis_client.health_check", new_callable=AsyncMock) as mock_redis, \
             patch("app.main.elasticsearch_client.health_check", new_callable=AsyncMock) as mock_es:

            # Setup mocks - Elasticsearch fails
            mock_redis.return_value = True
            mock_es.return_value = False

            response = client.get("/ready")

            assert response.status_code == 503
            data = response.json()
            # HTTPException handler wraps detail in error.message
            assert data["error"]["message"]["status"] == "not_ready"
            assert data["error"]["message"]["services"]["elasticsearch"]["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_ready_endpoint_multiple_services_unavailable(self, client):
        """
        TC-B6: Ready endpoint returns 503 when multiple services are unavailable
        """
        # Mock database connection that raises error
        mock_conn = AsyncMock()
        mock_conn.__aenter__.side_effect = OperationalError("DB failed", None, None)

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch("app.main.engine", mock_engine), \
             patch("app.main.redis_client.health_check", new_callable=AsyncMock) as mock_redis, \
             patch("app.main.elasticsearch_client.health_check", new_callable=AsyncMock) as mock_es:

            # All services fail
            mock_redis.return_value = False
            mock_es.return_value = False

            response = client.get("/ready")

            assert response.status_code == 503
            data = response.json()
            # HTTPException handler wraps detail in error.message
            assert data["error"]["message"]["status"] == "not_ready"
            assert data["error"]["message"]["services"]["postgresql"]["status"] == "unhealthy"
            assert data["error"]["message"]["services"]["redis"]["status"] == "unhealthy"
            assert data["error"]["message"]["services"]["elasticsearch"]["status"] == "unhealthy"
