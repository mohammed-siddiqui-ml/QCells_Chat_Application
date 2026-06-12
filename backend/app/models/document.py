"""
Document and document chunk models for knowledge base
"""
from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.db.session import Base
from app.db.types import GUID, JSON


class Document(Base):
    """Document model for storing knowledge base documents"""
    __tablename__ = "documents"

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
    
    # External identifier from source system
    external_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    
    # Document content
    title: Mapped[str] = mapped_column(
        Text, 
        nullable=False
    )
    content: Mapped[str] = mapped_column(
        Text, 
        nullable=False
    )
    url: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True
    )
    
    # Metadata for flexible storage (use 'meta' as column name to avoid SQLAlchemy reserved 'metadata')
    meta: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
        name="metadata"  # Column name in database
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
    
    # Soft delete flag
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, 
        default=False, 
        nullable=False
    )
    
    # Relationships
    source: Mapped["DataSource"] = relationship(
        "DataSource",
        back_populates="documents",
        lazy="selectin"
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        lazy="selectin",
        cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_documents_source_id", "source_id"),
        Index("ix_documents_external_id", "external_id"),
        Index("ix_documents_is_deleted", "is_deleted"),
        Index("ix_documents_created_at", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<Document(id={self.id}, title={self.title[:50]})>"


class DocumentChunk(Base):
    """Document chunk model for storing embedded document segments"""
    __tablename__ = "document_chunks"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4
    )

    # Foreign Key to Document
    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Chunk information
    chunk_index: Mapped[int] = mapped_column(
        Integer, 
        nullable=False
    )
    content: Mapped[str] = mapped_column(
        Text, 
        nullable=False
    )
    
    # Vector embedding (384 dimensions for sentence-transformers)
    embedding: Mapped[Optional[list]] = mapped_column(
        Vector(384), 
        nullable=True
    )
    
    # Metadata for flexible storage (use 'meta' as column name to avoid SQLAlchemy reserved 'metadata')
    meta: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
        name="metadata"  # Column name in database
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="chunks",
        lazy="selectin"
    )
    
    # Indexes (including vector similarity search index)
    __table_args__ = (
        Index("ix_document_chunks_document_id", "document_id"),
        Index("ix_document_chunks_chunk_index", "chunk_index"),
        # Vector index for similarity search (created via migration)
    )
    
    def __repr__(self) -> str:
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, chunk_index={self.chunk_index})>"
