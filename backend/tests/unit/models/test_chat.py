"""
Unit tests for ChatSession and Message models - TC-004 through TC-008
"""
import pytest
from datetime import datetime
import time
from sqlalchemy import select

from app.models.user import User, UserRole
from app.models.chat import ChatSession, Message, MessageRole


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
async def test_chat_session_creation_with_user(clean_db, sample_user_data, sample_session_data):
    """TC-004: ChatSession Creation with User Relationship"""
    session = clean_db
    
    # Create user first
    user = User(**sample_user_data)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    
    # Create chat session
    chat_session = ChatSession(
        user_id=user.id,
        **sample_session_data
    )
    session.add(chat_session)
    await session.commit()
    await session.refresh(chat_session)
    
    # Verify relationship
    assert chat_session.user_id == user.id
    assert chat_session.user is not None
    assert chat_session.user.id == user.id
    
    # Verify reverse relationship
    await session.refresh(user)
    assert len(user.chat_sessions) == 1
    assert user.chat_sessions[0].id == chat_session.id


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
async def test_chat_session_anonymous_user(clean_db, sample_session_data):
    """TC-005: ChatSession with Anonymous User (NULL user_id)"""
    session = clean_db
    
    # Create chat session without user
    chat_session = ChatSession(
        user_id=None,
        **sample_session_data
    )
    session.add(chat_session)
    await session.commit()
    await session.refresh(chat_session)
    
    # Verify
    assert chat_session.user_id is None
    assert chat_session.user is None
    assert chat_session.session_token == sample_session_data["session_token"]


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
async def test_chat_session_metadata_jsonb(clean_db, sample_session_data):
    """TC-006: ChatSession Metadata JSONB Storage"""
    session = clean_db
    
    # Create session with complex metadata
    metadata = {
        "ip": "192.168.1.1",
        "user_agent": "Mozilla/5.0",
        "nested": {"data": 123, "array": [1, 2, 3]}
    }
    
    chat_session = ChatSession(
        session_token="test_token",
        metadata=metadata
    )
    session.add(chat_session)
    await session.commit()
    
    # Query back
    result = await session.execute(
        select(ChatSession).where(ChatSession.session_token == "test_token")
    )
    retrieved_session = result.scalar_one()
    
    # Verify metadata
    assert retrieved_session.metadata == metadata
    assert retrieved_session.metadata["nested"]["data"] == 123
    assert retrieved_session.metadata["nested"]["array"] == [1, 2, 3]


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
async def test_message_cascade_delete(clean_db, sample_session_data):
    """TC-007: Message Creation with Cascade Delete"""
    session = clean_db
    
    # Create chat session
    chat_session = ChatSession(**sample_session_data)
    session.add(chat_session)
    await session.commit()
    await session.refresh(chat_session)
    
    # Create 3 messages
    for i in range(3):
        message = Message(
            session_id=chat_session.id,
            role=MessageRole.USER,
            content=f"Message {i}"
        )
        session.add(message)
    await session.commit()
    
    # Verify messages exist
    result = await session.execute(select(Message))
    messages = result.scalars().all()
    assert len(messages) == 3
    
    # Delete chat session
    await session.delete(chat_session)
    await session.commit()
    
    # Verify all messages are deleted (cascade)
    result = await session.execute(select(Message))
    messages = result.scalars().all()
    assert len(messages) == 0


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
async def test_message_role_enum_and_jsonb(clean_db, sample_session_data):
    """TC-008: Message Role Enum and JSONB Fields"""
    session = clean_db
    
    # Create chat session
    chat_session = ChatSession(**sample_session_data)
    session.add(chat_session)
    await session.commit()
    
    # Create user message
    user_msg = Message(
        session_id=chat_session.id,
        role=MessageRole.USER,
        content="What is X?"
    )
    session.add(user_msg)
    
    # Create assistant message with sources
    assistant_msg = Message(
        session_id=chat_session.id,
        role=MessageRole.ASSISTANT,
        content="X is...",
        sources={"doc_ids": [1, 2]}
    )
    session.add(assistant_msg)
    
    # Create system message with feedback
    system_msg = Message(
        session_id=chat_session.id,
        role=MessageRole.SYSTEM,
        content="Session started",
        feedback={"rating": 5}
    )
    session.add(system_msg)
    
    await session.commit()
    
    # Query back and verify
    result = await session.execute(select(Message))
    messages = result.scalars().all()
    assert len(messages) == 3
    
    roles = {msg.role for msg in messages}
    assert roles == {MessageRole.USER, MessageRole.ASSISTANT, MessageRole.SYSTEM}
    
    # Verify JSONB fields
    for msg in messages:
        if msg.role == MessageRole.ASSISTANT:
            assert msg.sources == {"doc_ids": [1, 2]}
        elif msg.role == MessageRole.SYSTEM:
            assert msg.feedback == {"rating": 5}
