"""
Unit tests for Document and DocumentChunk models - TC-013 through TC-016
"""
import pytest
import numpy as np
from sqlalchemy import select

from app.models.user import User, UserRole
from app.models.source import DataSource, SourceType
from app.models.document import Document, DocumentChunk


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
async def test_document_soft_delete(clean_db, sample_user_data):
    """TC-013: Document Model with Soft Delete"""
    session = clean_db
    
    # Create user and data source
    user = User(**sample_user_data)
    session.add(user)
    await session.commit()
    
    source = DataSource(
        name="Test Source",
        type=SourceType.CONFLUENCE,
        config={},
        created_by=user.id
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    
    # Create document
    document = Document(
        source_id=source.id,
        external_id="DOC-123",
        title="Test Document",
        content="Test content"
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    
    # Verify is_deleted defaults to False
    assert document.is_deleted is False
    
    # Soft delete
    document.is_deleted = True
    await session.commit()
    
    # Document still exists
    result = await session.execute(select(Document))
    docs = result.scalars().all()
    assert len(docs) == 1
    assert docs[0].is_deleted is True
    
    # Filter out soft deleted
    result = await session.execute(
        select(Document).where(Document.is_deleted == False)
    )
    active_docs = result.scalars().all()
    assert len(active_docs) == 0


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
async def test_document_cascade_delete_chunks(clean_db, sample_user_data):
    """TC-014: Document Cascade Delete with Chunks"""
    session = clean_db
    
    # Create user, source, and document
    user = User(**sample_user_data)
    session.add(user)
    await session.commit()
    
    source = DataSource(
        name="Test Source",
        type=SourceType.CONFLUENCE,
        config={},
        created_by=user.id
    )
    session.add(source)
    await session.commit()
    
    document = Document(
        source_id=source.id,
        external_id="DOC-123",
        title="Test Document",
        content="Test content"
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    
    # Create 5 chunks
    for i in range(5):
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=i,
            content=f"Chunk {i} content"
        )
        session.add(chunk)
    await session.commit()
    
    # Verify chunks exist
    result = await session.execute(select(DocumentChunk))
    chunks = result.scalars().all()
    assert len(chunks) == 5
    
    # Delete document
    await session.delete(document)
    await session.commit()
    
    # Verify all chunks are deleted (cascade)
    result = await session.execute(select(DocumentChunk))
    chunks = result.scalars().all()
    assert len(chunks) == 0


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
@pytest.mark.requires_postgres
async def test_document_chunk_vector_embedding(clean_db, sample_user_data, sample_embedding):
    """TC-015: DocumentChunk Vector Embedding Storage (requires PostgreSQL with pgvector)"""
    session = clean_db
    
    # Create user, source, and document
    user = User(**sample_user_data)
    session.add(user)
    await session.commit()
    
    source = DataSource(
        name="Test Source",
        type=SourceType.CONFLUENCE,
        config={},
        created_by=user.id
    )
    session.add(source)
    await session.commit()
    
    document = Document(
        source_id=source.id,
        external_id="DOC-123",
        title="Test Document",
        content="Test content"
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    
    # Create chunk with 384-dimensional embedding
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="Test chunk content",
        embedding=sample_embedding
    )
    session.add(chunk)
    await session.commit()
    
    # Query back and verify
    result = await session.execute(select(DocumentChunk))
    retrieved_chunk = result.scalar_one()
    
    assert retrieved_chunk.embedding is not None
    assert len(retrieved_chunk.embedding) == 384
    
    # Test with NULL embedding
    chunk2 = DocumentChunk(
        document_id=document.id,
        chunk_index=1,
        content="Chunk without embedding",
        embedding=None
    )
    session.add(chunk2)
    await session.commit()
    
    result = await session.execute(
        select(DocumentChunk).where(DocumentChunk.chunk_index == 1)
    )
    chunk_no_embed = result.scalar_one()
    assert chunk_no_embed.embedding is None


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
async def test_document_chunk_ordering(clean_db, sample_user_data):
    """TC-016: DocumentChunk Chunk Index Ordering"""
    session = clean_db
    
    # Create user, source, and document
    user = User(**sample_user_data)
    session.add(user)
    await session.commit()
    
    source = DataSource(
        name="Test Source",
        type=SourceType.CONFLUENCE,
        config={},
        created_by=user.id
    )
    session.add(source)
    await session.commit()
    
    document = Document(
        source_id=source.id,
        external_id="DOC-123",
        title="Test Document",
        content="Test content"
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    
    # Create 10 chunks with sequential indexes
    for i in range(10):
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=i,
            content=f"Chunk {i}"
        )
        session.add(chunk)
    await session.commit()
    
    # Query ordered by chunk_index
    result = await session.execute(
        select(DocumentChunk).order_by(DocumentChunk.chunk_index)
    )
    chunks = result.scalars().all()
    
    # Verify order
    assert len(chunks) == 10
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i
        assert chunk.content == f"Chunk {i}"
