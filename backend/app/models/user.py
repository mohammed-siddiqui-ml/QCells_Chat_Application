"""
User model for authentication and authorization
"""
from datetime import datetime
from typing import Optional
import uuid
import enum

from sqlalchemy import String, Boolean, Enum as SQLEnum, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.db.types import GUID


class UserRole(str, enum.Enum):
    """User role enumeration"""
    ADMIN = "admin"
    USER = "user"
    ANONYMOUS = "anonymous"


class User(Base):
    """User model for authentication and role management"""
    __tablename__ = "users"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Authentication fields
    email: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True,
        nullable=True
    )
    password_hash: Mapped[Optional[str]] = mapped_column(
        String(255), 
        nullable=True
    )
    
    # Role and status
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, name="user_role"),
        default=UserRole.ANONYMOUS,
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, 
        default=True, 
        nullable=False
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=datetime.utcnow,
        nullable=False
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True
    )
    
    # Relationships
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        "ChatSession",
        back_populates="user",
        lazy="selectin"
    )
    data_sources: Mapped[list["DataSource"]] = relationship(
        "DataSource",
        back_populates="created_by_user",
        lazy="selectin"
    )
    
    # Indexes (email already has unique index from unique=True constraint)
    __table_args__ = (
        Index("ix_users_role", "role"),
        Index("ix_users_is_active", "is_active"),
    )
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
