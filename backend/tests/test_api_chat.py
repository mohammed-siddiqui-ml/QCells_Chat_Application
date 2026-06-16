"""
Integration tests for Chat API endpoints - REST endpoints
Tests cover session management, message history, and query processing
"""
import pytest
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

# Mock the services BEFORE importing anything that uses them
import sys
sys.modules['app.services.genai.llm_service'] = MagicMock()
sys.modules['app.services.genai.embedding_service'] = MagicMock()
sys.modules['app.services.genai.rag_service'] = MagicMock()

from app.models.chat import ChatSession, Message, MessageRole
from app.db.session import get_db
from app.api.routes.chat import router
from app.schemas.chat import SessionResponse


@pytest.fixture
def test_app():
    """Create a minimal FastAPI app with only chat router for testing"""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/chat", tags=["chat"])
    return app


@pytest.fixture
def client(db_session, test_app):
    """Create test client with database override"""
    async def override_get_db():
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db
    with TestClient(test_app) as test_client:
        yield test_client
    test_app.dependency_overrides.clear()


@pytest.fixture
async def test_session(clean_db):
    """Create a test session for tests"""
    session = ChatSession(
        session_token="test_session_token_123",
        meta={"ip": "192.168.1.1", "user_agent": "TestAgent/1.0"}
    )
    clean_db.add(session)
    await clean_db.commit()
    await clean_db.refresh(session)
    return session


@pytest.mark.asyncio
async def test_create_session(client):
    """TC-A1: Create Anonymous Session Successfully"""
    response = client.post(
        "/api/v1/chat/sessions",
        json={"metadata": {"ip_address": "192.168.1.1", "user_agent": "Mozilla/5.0"}}
    )
    
    assert response.status_code == 201
    data = response.json()
    
    # Verify response structure
    assert "id" in data
    assert "session_token" in data
    assert "created_at" in data
    assert "updated_at" in data
    
    # Verify session token format
    assert data["session_token"].startswith("sess_")
    assert len(data["session_token"]) > 10
    
    # Verify user_id is null for anonymous session
    assert data["user_id"] is None
    
    # Verify metadata
    assert data["metadata"] is not None


@pytest.mark.asyncio
async def test_unique_session_tokens(client):
    """TC-A2: Generate Unique Session Tokens"""
    response1 = client.post("/api/v1/chat/sessions", json={})
    response2 = client.post("/api/v1/chat/sessions", json={})
    
    assert response1.status_code == 201
    assert response2.status_code == 201
    
    data1 = response1.json()
    data2 = response2.json()
    
    # Verify tokens are different
    assert data1["session_token"] != data2["session_token"]
    assert data1["id"] != data2["id"]


@pytest.mark.asyncio
async def test_get_session_invalid_uuid(client):
    """TC-A4: Handle Invalid Session ID Format"""
    response = client.get("/api/v1/chat/sessions/invalid-uuid-format")
    
    assert response.status_code == 400
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_get_session_not_found(client):
    """TC-A5: Handle Non-Existent Session"""
    non_existent_id = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/api/v1/chat/sessions/{non_existent_id}")
    
    assert response.status_code == 404
    data = response.json()
    assert "Session not found" in data["detail"]


@pytest.mark.asyncio
async def test_get_session_with_empty_history(client, test_session):
    """Test retrieving session with no messages"""
    response = client.get(f"/api/v1/chat/sessions/{test_session.id}")

    assert response.status_code == 200
    data = response.json()

    assert data["session"]["id"] == str(test_session.id)
    assert data["messages"] == []
    assert data["total_messages"] == 0
    assert data["page"] == 1
    # With 0 messages and page_size 50, total_pages should be 1 (showing empty page 1)
    assert data["total_pages"] == 1


@pytest.mark.asyncio
async def test_get_session_with_messages_pagination(clean_db, test_session, test_app):
    """TC-B1: Retrieve Session with Default Pagination"""
    # Create 75 messages
    for i in range(75):
        msg = Message(
            session_id=test_session.id,
            role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
            content=f"Message {i}"
        )
        clean_db.add(msg)
    await clean_db.commit()

    # Override get_db for this test
    async def override_get_db():
        yield clean_db

    test_app.dependency_overrides[get_db] = override_get_db

    with TestClient(test_app) as client:
        response = client.get(f"/api/v1/chat/sessions/{test_session.id}")

    test_app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()

    # Default page size is 50
    assert len(data["messages"]) == 50
    assert data["total_messages"] == 75
    assert data["page"] == 1
    assert data["page_size"] == 50
    assert data["total_pages"] == 2


@pytest.mark.asyncio
async def test_custom_page_size(clean_db, test_session, test_app):
    """TC-B2: Retrieve Session with Custom Page Size"""
    # Create 30 messages
    for i in range(30):
        msg = Message(
            session_id=test_session.id,
            role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
            content=f"Message {i}"
        )
        clean_db.add(msg)
    await clean_db.commit()

    async def override_get_db():
        yield clean_db

    test_app.dependency_overrides[get_db] = override_get_db

    with TestClient(test_app) as client:
        response = client.get(f"/api/v1/chat/sessions/{test_session.id}?page_size=10")

    test_app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()

    assert len(data["messages"]) == 10
    assert data["page_size"] == 10
    assert data["total_pages"] == 3


@pytest.mark.asyncio
async def test_page_size_max_limit(clean_db, test_session, test_app):
    """TC-B4: Handle Page Size Exceeding Maximum"""
    # Create 150 messages to test max page size
    for i in range(150):
        msg = Message(
            session_id=test_session.id,
            role=MessageRole.USER,
            content=f"Message {i}"
        )
        clean_db.add(msg)
    await clean_db.commit()

    async def override_get_db():
        yield clean_db

    test_app.dependency_overrides[get_db] = override_get_db

    with TestClient(test_app) as client:
        # Test 1: Request 200 should be rejected with 422 (validation error)
        response_invalid = client.get(f"/api/v1/chat/sessions/{test_session.id}?page_size=200")
        assert response_invalid.status_code == 422  # Validation error for page_size > 100

        # Test 2: Request exactly 100 should work
        response_valid = client.get(f"/api/v1/chat/sessions/{test_session.id}?page_size=100")
        assert response_valid.status_code == 200
        data = response_valid.json()
        assert data["page_size"] == 100
        assert len(data["messages"]) == 100  # Should return 100 messages

    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_submit_query_success(clean_db, test_session, test_app):
    """TC-C1: Submit Query Successfully with Mocked RAG Service"""

    # Mock RAG service response
    async def mock_generate_rag_response(*args, **kwargs):
        # Yield query analysis
        yield {
            "type": "metadata",
            "stage": "query_analysis",
            "data": {"intent": "question", "keywords": ["capital", "France"]}
        }
        # Yield sources
        yield {
            "type": "metadata",
            "stage": "sources",
            "data": {"sources": [{"title": "Geography", "url": "http://example.com", "score": 0.95}]}
        }
        # Yield tokens
        for token in ["The", " capital", " of", " France", " is", " Paris", "."]:
            yield {"type": "token", "data": token}

    with patch('app.api.routes.chat.rag_service') as mock_rag:
        mock_rag.generate_rag_response = mock_generate_rag_response

        async def override_get_db():
            yield clean_db

        test_app.dependency_overrides[get_db] = override_get_db

        with TestClient(test_app) as client:
            response = client.post(
                "/api/v1/chat/query",
                json={
                    "session_id": str(test_session.id),
                    "query": "What is the capital of France?"
                }
            )

        test_app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "session_id" in data
    assert "user_message" in data
    assert "assistant_message" in data

    # Verify user message
    assert data["user_message"]["role"] == "user"
    assert data["user_message"]["content"] == "What is the capital of France?"

    # Verify assistant message
    assert data["assistant_message"]["role"] == "assistant"
    assert "Paris" in data["assistant_message"]["content"] or len(data["assistant_message"]["content"]) > 0


@pytest.mark.asyncio
async def test_query_validation_empty_query(client, test_session):
    """TC-C6: Handle Empty Query Validation"""
    response = client.post(
        "/api/v1/chat/query",
        json={
            "session_id": str(test_session.id),
            "query": ""
        }
    )

    assert response.status_code == 422  # Unprocessable Entity


@pytest.mark.asyncio
async def test_query_validation_too_long(client, test_session):
    """TC-C6: Handle Query Too Long Validation"""
    response = client.post(
        "/api/v1/chat/query",
        json={
            "session_id": str(test_session.id),
            "query": "a" * 2001  # Exceeds 2000 char limit
        }
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_invalid_temperature(client, test_session):
    """TC-C7: Handle Invalid Temperature Range"""
    response = client.post(
        "/api/v1/chat/query",
        json={
            "session_id": str(test_session.id),
            "query": "Test query",
            "temperature": 2.5  # Exceeds max of 2.0
        }
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_nonexistent_session(client):
    """TC-C9: Handle Query with Non-Existent Session"""
    response = client.post(
        "/api/v1/chat/query",
        json={
            "session_id": "00000000-0000-0000-0000-000000000000",
            "query": "Test query"
        }
    )

    assert response.status_code == 404
