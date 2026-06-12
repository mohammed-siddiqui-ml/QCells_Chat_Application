"""
Token model for refresh token management and revocation
"""
from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.db.types import GUID


class RefreshToken(Base):
    """Refresh token model for JWT token rotation and revocation"""
    __tablename__ = "refresh_tokens"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Foreign Key to User
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Token data
    token_hash: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )
    
    # Token metadata
    is_revoked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # User agent and IP for security tracking
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),  # IPv6 max length
        nullable=True
    )
    
    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="refresh_tokens",
        lazy="selectin"
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
        Index("ix_refresh_tokens_is_revoked", "is_revoked"),
    )
    
    def __repr__(self) -> str:
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, is_revoked={self.is_revoked})>"
    
    def is_valid(self) -> bool:
        """Check if token is still valid (not revoked and not expired)"""
        return not self.is_revoked and self.expires_at > datetime.utcnow()
