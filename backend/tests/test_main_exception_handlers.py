"""
Tests for FastAPI application exception handlers (task-015)
Tests TC-C1, TC-C2, TC-C3, TC-C4
"""
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    return TestClient(app, raise_server_exceptions=False)


# Test endpoints for triggering exceptions
class TestModel(BaseModel):
    """Test Pydantic model for validation testing."""
    required_field: str = Field(..., min_length=1)
    email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')


# Add test endpoints dynamically
@app.get("/test/http-exception")
async def endpoint_http_exception():
    """Test endpoint that raises HTTPException."""
    raise HTTPException(status_code=404, detail="Test resource not found")


@app.post("/test/validation-error")
async def endpoint_validation_error(data: TestModel):
    """Test endpoint that triggers validation error."""
    return {"message": "success"}


@app.get("/test/database-error")
async def endpoint_database_error():
    """Test endpoint that raises database error."""
    raise IntegrityError("INSERT INTO test", {}, Exception("constraint violation"))


@app.get("/test/general-exception")
async def endpoint_general_exception():
    """Test endpoint that raises general exception."""
    raise ValueError("Unexpected error occurred")


class TestExceptionHandlers:
    """Test suite for exception handlers."""

    def test_http_exception_handler(self, client):
        """
        TC-C1: HTTPException handler returns proper JSON response
        """
        response = client.get("/test/http-exception")
        
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["type"] == "HTTPException"
        assert data["error"]["status_code"] == 404
        assert data["error"]["message"] == "Test resource not found"
        assert data["error"]["path"] == "/test/http-exception"

    def test_validation_error_handler(self, client):
        """
        TC-C2: ValidationError handler returns proper JSON with error details
        """
        # Send invalid data (missing required fields and invalid email)
        response = client.post(
            "/test/validation-error",
            json={"email": "invalid-email"}
        )
        
        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"]["type"] == "ValidationError"
        assert data["error"]["status_code"] == 422
        assert data["error"]["message"] == "Request validation failed"
        assert "details" in data["error"]
        assert len(data["error"]["details"]) > 0

    def test_validation_error_handler_invalid_email(self, client):
        """
        TC-C2 (variant): ValidationError handler with invalid email format
        """
        response = client.post(
            "/test/validation-error",
            json={"required_field": "test", "email": "not-an-email"}
        )
        
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["type"] == "ValidationError"
        assert "details" in data["error"]

    def test_database_error_handler(self, client):
        """
        TC-C3: DatabaseError handler returns generic error message (no info leakage)
        """
        response = client.get("/test/database-error")
        
        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert data["error"]["type"] == "DatabaseError"
        assert data["error"]["status_code"] == 500
        assert data["error"]["message"] == "A database error occurred. Please try again later."
        assert data["error"]["path"] == "/test/database-error"
        # Ensure no database details leaked
        assert "constraint" not in data["error"]["message"].lower()
        assert "integrity" not in data["error"]["message"].lower()

    def test_general_exception_handler(self, client):
        """
        TC-C4: General exception handler catches unexpected errors
        """
        response = client.get("/test/general-exception")
        
        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert data["error"]["type"] == "InternalServerError"
        assert data["error"]["status_code"] == 500
        assert data["error"]["message"] == "An unexpected error occurred. Please try again later."
        assert data["error"]["path"] == "/test/general-exception"
        # Ensure no exception details leaked
        assert "ValueError" not in data["error"]["message"]
        assert "Unexpected error occurred" not in data["error"]["message"]
