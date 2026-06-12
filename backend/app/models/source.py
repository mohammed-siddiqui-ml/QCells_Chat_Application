"""
Data source and sync log models
"""
from datetime import datetime
from typing import Optional
import uuid
import enum

from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, Enum as SQLEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.db.types import GUID, JSON


class SourceType(str, enum.Enum):
    """Data source type enumeration"""
    CONFLUENCE = "confluence"
    JIRA = "jira"
    GITHUB = "github"
    ONBOARDING = "onboarding"


class SyncStatus(str, enum.Enum):
    """Sync status enumeration"""
    PENDING = "pending"
    SYNCING = "syncing"
    SUCCESS = "success"
    FAILED = "failed"


class DataSource(Base):
    """Data source model for external integrations"""
    __tablename__ = "data_sources"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        GUID, 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Source information
    name: Mapped[str] = mapped_column(
        String(255), 
        nullable=False
    )
    type: Mapped[SourceType] = mapped_column(
        SQLEnum(SourceType, name="source_type"),
        nullable=False
    )
    
    # Configuration (encrypted in application layer)
    config: Mapped[dict] = mapped_column(
        JSON, 
        nullable=False,
        default=dict
    )
    
    # Sync status and tracking
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True
    )
    sync_status: Mapped[SyncStatus] = mapped_column(
        SQLEnum(SyncStatus, name="sync_status"),
        default=SyncStatus.PENDING,
        nullable=False
    )
    sync_error: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True
    )
    
    # Foreign Key to User (creator)
    created_by: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean, 
        default=True, 
        nullable=False
    )
    
    # Relationships
    created_by_user: Mapped["User"] = relationship(
        "User",
        back_populates="data_sources",
        lazy="selectin"
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="source",
        lazy="selectin",
        cascade="all, delete-orphan"
    )
    sync_logs: Mapped[list["SyncLog"]] = relationship(
        "SyncLog",
        back_populates="source",
        lazy="selectin",
        cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_data_sources_type", "type"),
        Index("ix_data_sources_created_by", "created_by"),
        Index("ix_data_sources_sync_status", "sync_status"),
        Index("ix_data_sources_is_active", "is_active"),
    )
    
    def __repr__(self) -> str:
        return f"<DataSource(id={self.id}, name={self.name}, type={self.type})>"


class SyncLog(Base):
    """Sync log model for tracking data synchronization"""
    __tablename__ = "sync_logs"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        GUID, 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Foreign Key to DataSource
    source_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Sync timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=datetime.utcnow,
        nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True
    )
    
    # Sync status and metrics
    status: Mapped[SyncStatus] = mapped_column(
        SQLEnum(SyncStatus, name="sync_status"),
        default=SyncStatus.PENDING,
        nullable=False
    )
    documents_processed: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    documents_added: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    documents_updated: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    documents_deleted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )

    # Error logging
    error_log: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    # Relationships
    source: Mapped["DataSource"] = relationship(
        "DataSource",
        back_populates="sync_logs",
        lazy="selectin"
    )

    # Indexes
    __table_args__ = (
        Index("ix_sync_logs_source_id", "source_id"),
        Index("ix_sync_logs_status", "status"),
        Index("ix_sync_logs_started_at", "started_at"),
    )

    def __repr__(self) -> str:
        return f"<SyncLog(id={self.id}, source_id={self.source_id}, status={self.status})>"
