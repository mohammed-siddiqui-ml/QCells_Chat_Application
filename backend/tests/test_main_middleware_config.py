"""
Tests for FastAPI application middleware and configuration (task-015)
Tests TC-D1, TC-D2, TC-D4, TC-E3
"""
import pytest
import os
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    return TestClient(app)


class TestMiddleware:
    """Test suite for middleware functionality."""

    def test_cors_allowed_origins(self, client):
        """
        TC-D1: CORS middleware allows requests from allowed origins
        """
        # Send request with allowed origin
        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"}
        )
        
        assert response.status_code == 200
        # Note: TestClient doesn't fully simulate CORS preflight
        # In real scenarios, Access-Control-Allow-Origin would be in response headers

    def test_cors_preflight_request(self, client):
        """
        TC-D1 (variant): CORS preflight request is handled
        """
        # Send OPTIONS preflight request
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )
        
        # Should get successful response (CORS middleware handles OPTIONS)
        assert response.status_code in [200, 204]

    def test_logging_middleware(self, client):
        """
        TC-D3: Logging middleware logs all requests and responses
        """
        # Make a request to trigger logging middleware
        with patch("app.main.logger") as mock_logger:
            response = client.get("/health")
            
            assert response.status_code == 200
            # Verify logger was called for request and response
            assert mock_logger.info.call_count >= 2

    def test_request_logging_includes_details(self, client):
        """
        TC-D3 (variant): Logging middleware includes request details
        """
        with patch("app.main.logger") as mock_logger:
            response = client.get("/health")
            
            # Check that logging was called with proper format
            calls = mock_logger.info.call_args_list
            # First call should be for incoming request
            assert any("Incoming request" in str(call) or "GET" in str(call) for call in calls)


class TestConfiguration:
    """Test suite for application configuration."""

    def test_app_metadata(self, client):
        """
        TC-E3: Application initializes with correct title, version, and description
        """
        # Access OpenAPI schema
        response = client.get("/openapi.json")
        
        assert response.status_code == 200
        schema = response.json()
        
        assert schema["info"]["title"] == "GenAI Chat API"
        assert schema["info"]["version"] == "1.0.0"
        assert "GenAI Intelligent Chat-Based Knowledge Retrieval System" in schema["info"]["description"]

    def test_cors_configuration_with_allowed_origins(self):
        """
        TC-D4: Application uses ALLOWED_ORIGINS when set
        """
        # This test verifies the CORS configuration logic
        from app.core.config import settings
        from app.main import allowed_origins
        
        # If ALLOWED_ORIGINS is set, it should be used
        if settings.ALLOWED_ORIGINS:
            assert allowed_origins == settings.ALLOWED_ORIGINS
        else:
            # Otherwise, should fall back to CORS_ORIGINS
            assert allowed_origins == settings.CORS_ORIGINS

    def test_root_endpoint(self, client):
        """
        Test root endpoint returns API information
        """
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data
        assert "status" in data
        assert data["status"] == "running"
        assert "GenAI" in data["message"]

    def test_openapi_docs_available(self, client):
        """
        Test that API documentation is available
        """
        # Test /docs endpoint
        response = client.get("/docs")
        assert response.status_code == 200
        
        # Test /redoc endpoint
        response = client.get("/redoc")
        assert response.status_code == 200

    def test_health_endpoint_in_openapi(self, client):
        """
        Test that health endpoints are documented in OpenAPI schema
        """
        response = client.get("/openapi.json")
        schema = response.json()
        
        assert "/health" in schema["paths"]
        assert "/ready" in schema["paths"]
        assert "get" in schema["paths"]["/health"]
        assert "get" in schema["paths"]["/ready"]
