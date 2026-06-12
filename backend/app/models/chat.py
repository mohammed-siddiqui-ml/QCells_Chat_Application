"""
Chat session and message models
"""
from datetime import datetime
from typing import Optional
import uuid
import enum

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum as SQLEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.db.types import GUID, JSON


class MessageRole(str, enum.Enum):
    """Message role enumeration"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatSession(Base):
    """Chat session model for managing conversations"""
    __tablename__ = "chat_sessions"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4
    )

    # Foreign Key to User (nullable for anonymous users)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Session token for tracking
    session_token: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    
    # Metadata for flexible storage (use 'meta' as column name to avoid SQLAlchemy reserved 'metadata')
    meta: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
        name="metadata"  # Column name in database
    )
    
    # Relationships
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="chat_sessions",
        lazy="selectin"
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="session",
        lazy="selectin",
        cascade="all, delete-orphan"
    )
    
    # Indexes (session_token already has unique index from unique=True constraint)
    __table_args__ = (
        Index("ix_chat_sessions_user_id", "user_id"),
        Index("ix_chat_sessions_created_at", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id}, session_token={self.session_token})>"


class Message(Base):
    """Message model for storing conversation messages"""
    __tablename__ = "messages"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4
    )

    # Foreign Key to ChatSession
    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Message content
    role: Mapped[MessageRole] = mapped_column(
        SQLEnum(MessageRole, name="message_role"),
        nullable=False
    )
    content: Mapped[str] = mapped_column(
        Text, 
        nullable=False
    )
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=datetime.utcnow,
        nullable=False
    )
    
    # Sources and feedback as JSONB
    sources: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict
    )
    feedback: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict
    )
    
    # Relationships
    session: Mapped["ChatSession"] = relationship(
        "ChatSession",
        back_populates="messages",
        lazy="selectin"
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_messages_session_id", "session_id"),
        Index("ix_messages_created_at", "created_at"),
        Index("ix_messages_role", "role"),
    )
    
    def __repr__(self) -> str:
        return f"<Message(id={self.id}, session_id={self.session_id}, role={self.role})>"
