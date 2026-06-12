"""
Integration tests for models - TC-017 and full CRUD operations
"""
import pytest
from sqlalchemy import text, inspect

from app.models.user import User, UserRole
from app.models.chat import ChatSession, Message
from app.models.source import DataSource, SyncLog
from app.models.document import Document, DocumentChunk


@pytest.mark.integration
@pytest.mark.database
@pytest.mark.asyncio
async def test_index_existence_verification(engine):
    """TC-017: Index Existence Verification"""
    async with engine.connect() as conn:
        # Use run_sync to call synchronous Inspector methods in async context
        def verify_tables_and_indexes(sync_conn):
            inspector = inspect(sync_conn)
            tables = inspector.get_table_names()

            # Verify all expected tables exist
            expected_tables = {
                "users", "chat_sessions", "messages",
                "data_sources", "sync_logs", "documents", "document_chunks"
            }
            assert expected_tables.issubset(set(tables))

            # Verify indexes on users table
            users_indexes = inspector.get_indexes("users")
            users_index_names = {idx['name'] for idx in users_indexes}

            # Check for email unique constraint (SQLite may use unique constraints instead of unique indexes)
            users_unique_constraints = inspector.get_unique_constraints("users")
            has_email_unique_constraint = any('email' in uc.get('column_names', [])
                                             for uc in users_unique_constraints)
            has_email_index = any('email' in name.lower() for name in users_index_names)
            has_email_unique_index = any(idx.get('unique') and 'email' in idx.get('column_names', [])
                                        for idx in users_indexes)

            # At least one of these should be true (unique constraint, unique index, or regular index)
            assert has_email_unique_constraint or has_email_unique_index or has_email_index, \
                f"No email index/constraint found. Indexes: {users_indexes}, Constraints: {users_unique_constraints}"

            # Verify other explicit indexes exist
            assert 'ix_users_role' in users_index_names
            assert 'ix_users_is_active' in users_index_names

            # Verify indexes on chat_sessions table
            sessions_indexes = inspector.get_indexes("chat_sessions")
            sessions_index_names = {idx['name'] for idx in sessions_indexes}
            sessions_unique_constraints = inspector.get_unique_constraints("chat_sessions")
            # session_token should have unique constraint or index
            has_token_constraint = any('session_token' in uc.get('column_names', [])
                                      for uc in sessions_unique_constraints)
            has_token_index = any('session_token' in name for name in sessions_index_names)
            assert has_token_constraint or has_token_index, \
                f"No session_token constraint/index. Indexes: {sessions_indexes}, Constraints: {sessions_unique_constraints}"

            # Verify indexes on messages table
            messages_indexes = inspector.get_indexes("messages")
            messages_index_names = {idx['name'] for idx in messages_indexes}
            assert any('session_id' in name for name in messages_index_names)

            # Verify indexes on data_sources table
            sources_indexes = inspector.get_indexes("data_sources")
            sources_index_names = {idx['name'] for idx in sources_indexes}
            assert any('type' in name for name in sources_index_names)

            # Verify indexes on documents table
            docs_indexes = inspector.get_indexes("documents")
            docs_index_names = {idx['name'] for idx in docs_indexes}
            assert any('source_id' in name for name in docs_index_names)
            assert any('external_id' in name for name in docs_index_names)

            return True

        # Run all inspections in sync context
        result = await conn.run_sync(verify_tables_and_indexes)
        assert result is True


@pytest.mark.integration
@pytest.mark.database
@pytest.mark.asyncio
async def test_full_crud_operations(clean_db, sample_user_data):
    """Test complete CRUD operations across all models"""
    session = clean_db
    
    # CREATE operations
    # Create user
    user = User(**sample_user_data)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    user_id = user.id
    
    # Create chat session
    chat_session = ChatSession(
        user_id=user.id,
        session_token="crud_test_token"
    )
    session.add(chat_session)
    await session.commit()
    session_id = chat_session.id
    
    # Create message
    message = Message(
        session_id=chat_session.id,
        role="user",
        content="Test message"
    )
    session.add(message)
    await session.commit()
    message_id = message.id
    
    # Create data source
    data_source = DataSource(
        name="CRUD Test Source",
        type="confluence",
        config={},
        created_by=user.id
    )
    session.add(data_source)
    await session.commit()
    source_id = data_source.id
    
    # READ operations
    await session.refresh(user)
    assert user.email == sample_user_data["email"]
    assert len(user.chat_sessions) > 0
    
    # UPDATE operations
    user.email = "updated@example.com"
    await session.commit()
    await session.refresh(user)
    assert user.email == "updated@example.com"
    
    # DELETE operations
    await session.delete(message)
    await session.commit()
    
    # Verify deletion
    result = await session.get(Message, message_id)
    assert result is None


@pytest.mark.integration
@pytest.mark.database
@pytest.mark.asyncio
async def test_constraint_enforcement(clean_db, sample_user_data):
    """Test database constraints are properly enforced"""
    session = clean_db
    
    # Create user
    user = User(**sample_user_data)
    session.add(user)
    await session.commit()
    
    # Test NOT NULL constraint on required fields
    from sqlalchemy.exc import IntegrityError
    
    # Document requires source_id
    invalid_doc = Document(
        external_id="test",
        title="test",
        content="test"
        # Missing source_id - should fail
    )
    session.add(invalid_doc)
    
    with pytest.raises(IntegrityError):
        await session.commit()
    
    await session.rollback()


@pytest.mark.integration
@pytest.mark.database
@pytest.mark.asyncio
async def test_default_values_applied(clean_db):
    """Test that default values are applied correctly"""
    session = clean_db
    
    # Create user with minimal data
    user = User(email="defaults@test.com")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    
    # Verify defaults
    assert user.role == UserRole.ANONYMOUS
    assert user.is_active is True
    assert user.created_at is not None
    
    # Create chat session
    chat_session = ChatSession(session_token="default_test")
    session.add(chat_session)
    await session.commit()
    await session.refresh(chat_session)
    
    # Verify defaults
    assert chat_session.created_at is not None
    assert chat_session.updated_at is not None
    # Use .meta (the Python attribute name) instead of .metadata (SQLAlchemy reserved)
    assert chat_session.meta == {} or chat_session.meta is None
