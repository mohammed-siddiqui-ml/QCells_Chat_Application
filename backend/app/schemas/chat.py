"""
Pydantic schemas for chat API
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    """Request schema for creating a new chat session"""
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata for the session (e.g., IP address, user agent)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "metadata": {
                    "ip": "192.168.1.1",
                    "user_agent": "Mozilla/5.0"
                }
            }
        }


class SessionResponse(BaseModel):
    """Response schema for chat session"""
    id: str = Field(..., description="Session UUID")
    session_token: str = Field(..., description="Session token for tracking")
    user_id: Optional[str] = Field(None, description="User UUID if authenticated")
    created_at: datetime = Field(..., description="Session creation timestamp")
    updated_at: datetime = Field(..., description="Session last update timestamp")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Session metadata")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "session_token": "sess_abc123xyz",
                "user_id": None,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "metadata": {"ip": "192.168.1.1"}
            }
        }


class MessageResponse(BaseModel):
    """Response schema for chat message"""
    id: str = Field(..., description="Message UUID")
    session_id: str = Field(..., description="Session UUID")
    role: str = Field(..., description="Message role (user, assistant, system)")
    content: str = Field(..., description="Message content")
    created_at: datetime = Field(..., description="Message timestamp")
    sources: Optional[Dict[str, Any]] = Field(None, description="Source references for assistant messages")
    feedback: Optional[Dict[str, Any]] = Field(None, description="User feedback on message")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "456e7890-e89b-12d3-a456-426614174001",
                "session_id": "123e4567-e89b-12d3-a456-426614174000",
                "role": "assistant",
                "content": "RAG stands for Retrieval-Augmented Generation...",
                "created_at": "2024-01-01T00:01:00Z",
                "sources": {
                    "documents": [
                        {
                            "doc_id": "doc_001",
                            "title": "RAG Introduction",
                            "source": "confluence",
                            "score": 0.95
                        }
                    ]
                },
                "feedback": None
            }
        }


class SessionHistoryResponse(BaseModel):
    """Response schema for session history with pagination"""
    session: SessionResponse = Field(..., description="Session information")
    messages: List[MessageResponse] = Field(..., description="List of messages in session")
    total_messages: int = Field(..., description="Total number of messages in session")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Number of messages per page")
    total_pages: int = Field(..., description="Total number of pages")
    
    class Config:
        json_schema_extra = {
            "example": {
                "session": {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "session_token": "sess_abc123xyz",
                    "user_id": None,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:01:00Z",
                    "metadata": {}
                },
                "messages": [],
                "total_messages": 10,
                "page": 1,
                "page_size": 50,
                "total_pages": 1
            }
        }


class QueryRequest(BaseModel):
    """Request schema for submitting a query"""
    session_id: str = Field(..., description="Session UUID")
    query: str = Field(..., min_length=1, max_length=2000, description="User query text")
    source_type: Optional[str] = Field(None, description="Optional source type filter (confluence, jira, github, onboarding)")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Optional LLM temperature (0.0-2.0)")
    max_tokens: Optional[int] = Field(None, ge=50, le=4000, description="Optional max tokens for response")
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "123e4567-e89b-12d3-a456-426614174000",
                "query": "What is RAG?",
                "source_type": "confluence",
                "temperature": 0.7,
                "max_tokens": 500
            }
        }


class QueryResponse(BaseModel):
    """Response schema for query submission"""
    session_id: str = Field(..., description="Session UUID")
    user_message: MessageResponse = Field(..., description="User message that was saved")
    assistant_message: MessageResponse = Field(..., description="Assistant response message")
    query_analysis: Optional[Dict[str, Any]] = Field(None, description="Query analysis metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "123e4567-e89b-12d3-a456-426614174000",
                "user_message": {
                    "id": "user_msg_id",
                    "session_id": "123e4567-e89b-12d3-a456-426614174000",
                    "role": "user",
                    "content": "What is RAG?",
                    "created_at": "2024-01-01T00:01:00Z",
                    "sources": None,
                    "feedback": None
                },
                "assistant_message": {
                    "id": "assistant_msg_id",
                    "session_id": "123e4567-e89b-12d3-a456-426614174000",
                    "role": "assistant",
                    "content": "RAG stands for...",
                    "created_at": "2024-01-01T00:01:05Z",
                    "sources": {},
                    "feedback": None
                },
                "query_analysis": {
                    "query_type": "definition",
                    "entities": ["RAG"]
                }
            }
        }
