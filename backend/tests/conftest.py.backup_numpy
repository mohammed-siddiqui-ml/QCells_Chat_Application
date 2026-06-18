"""
Pytest configuration and fixtures for database tests
"""
# ⚠️ CRITICAL: Set required environment variables BEFORE any app imports
# This prevents SSL certificate errors when downloading HuggingFace models in WSL
import os
import sys

# Set required environment variables for testing
os.environ['EMBEDDING_MODEL'] = 'openai'
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key-for-testing-only-not-for-production'
os.environ['OPENAI_API_KEY'] = 'test-openai-api-key-for-testing'

# ⚠️ WSL FIX: Disable numpy multithreading to avoid module loading errors
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['NUMEXPR_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'

# ⚠️ WSL FIX: Allow numpy to be imported multiple times per process (pytest issue in WSL)
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

# ⚠️ AGGRESSIVE WSL FIX: Pre-import numpy to prevent double-import errors
# This must happen before any app imports that might trigger numpy loading via pgvector
try:
    import numpy as np
    # Force numpy initialization
    _ = np.array([1, 2, 3])
except Exception:
    pass  # Ignore any errors during pre-import

import asyncio
import pytest
import pytest_asyncio
import tempfile
from pathlib import Path
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool, StaticPool
from sqlalchemy import text, event

from app.db.session import Base
from app.models.user import User, UserRole
from app.models.chat import ChatSession, Message, MessageRole
from app.models.source import DataSource, SyncLog, SourceType, SyncStatus
from app.models.document import Document, DocumentChunk


# Test database URL - use in-memory SQLite for testing (PostgreSQL with pgvector preferred for vector tests)
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "sqlite+aiosqlite:///:memory:"
)

# Check if using PostgreSQL (for pgvector support)
IS_POSTGRES = TEST_DATABASE_URL.startswith("postgresql")

# Temporary directory for test databases
TEST_DB_DIR = Path(tempfile.gettempdir()) / "chatapp_tests"
TEST_DB_DIR.mkdir(exist_ok=True)


@pytest_asyncio.fixture(scope="function")
async def engine():
    """Create async engine for tests - fresh for each test"""
    if IS_POSTGRES:
        test_engine = create_async_engine(
            TEST_DATABASE_URL,
            poolclass=NullPool,
            echo=False,
        )
        db_file = None
    else:
        # For SQLite, use a unique file-based database for each test to avoid schema conflicts
        # This ensures complete isolation between tests
        import uuid
        db_file = TEST_DB_DIR / f"test_{uuid.uuid4().hex}.db"
        test_url = f"sqlite+aiosqlite:///{db_file}"

        test_engine = create_async_engine(
            test_url,
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
            echo=False,
        )

    # Enable foreign keys for SQLite BEFORE creating tables (critical for CASCADE)
    if not IS_POSTGRES:
        @event.listens_for(test_engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    # Create all tables
    async with test_engine.begin() as conn:
        # CRITICAL: Use checkfirst=True to prevent "already exists" errors
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, checkfirst=True))

    yield test_engine

    # CRITICAL: Cleanup after each test to prevent schema persistence
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()

    # Remove SQLite database file if it exists
    if db_file and db_file.exists():
        db_file.unlink()


@pytest_asyncio.fixture(scope="function")
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a new database session for each test with transaction rollback"""
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def clean_db(db_session: AsyncSession):
    """Clean all tables before test"""
    # Since we use transaction rollback, this fixture is not strictly necessary
    # but we keep it for explicit cleanup if needed
    # Check if tables exist before trying to delete
    try:
        # Delete in reverse dependency order
        await db_session.execute(text("DELETE FROM document_chunks"))
        await db_session.execute(text("DELETE FROM documents"))
        await db_session.execute(text("DELETE FROM sync_logs"))
        await db_session.execute(text("DELETE FROM messages"))
        await db_session.execute(text("DELETE FROM chat_sessions"))
        await db_session.execute(text("DELETE FROM data_sources"))
        await db_session.execute(text("DELETE FROM users"))
        await db_session.commit()
    except Exception:
        # If tables don't exist or error occurs, rollback and continue
        await db_session.rollback()
    return db_session


@pytest.fixture
def sample_user_data():
    """Sample user data for tests"""
    return {
        "email": "test@example.com",
        "password_hash": "hashed_password_123",
        "role": UserRole.ADMIN,
    }


@pytest.fixture
def sample_session_data():
    """Sample chat session data for tests"""
    return {
        "session_token": "session_abc123xyz",
        "meta": {"ip": "192.168.1.1", "user_agent": "Mozilla/5.0"},
    }


@pytest.fixture
def sample_message_data():
    """Sample message data for tests"""
    return {
        "role": MessageRole.USER,
        "content": "What is X?",
    }


@pytest.fixture
def sample_data_source_data():
    """Sample data source data for tests"""
    return {
        "name": "Test Confluence",
        "type": SourceType.CONFLUENCE,
        "config": {"url": "https://company.atlassian.net", "space_key": "ENG"},
    }


@pytest.fixture
def sample_document_data():
    """Sample document data for tests"""
    return {
        "external_id": "DOC-123",
        "title": "Test Document",
        "content": "This is test content",
        "url": "https://example.com/doc",
    }


@pytest.fixture
def sample_embedding():
    """Sample 384-dimensional embedding for tests"""
    import numpy as np
    return np.random.rand(384).tolist()


def pytest_configure(config):
    """Configure custom markers"""
    config.addinivalue_line(
        "markers", "requires_postgres: mark test as requiring PostgreSQL (pgvector)"
    )


def pytest_collection_modifyitems(config, items):
    """Skip tests requiring PostgreSQL if not available"""
    skip_postgres = pytest.mark.skip(reason="requires PostgreSQL with pgvector")
    for item in items:
        if "requires_postgres" in item.keywords and not IS_POSTGRES:
            item.add_marker(skip_postgres)


@pytest.fixture
async def test_user(db_session):
    """Create a test user for tests that need created_by field"""
    from app.models.user import User, UserRole

    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password="dummy_hash",
        role=UserRole.USER
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def mock_semantic_search(mocker):
    """Mock semantic search to avoid pgvector <=> operator in SQLite"""
    from unittest.mock import AsyncMock

    mock = mocker.patch(
        'app.services.search_service.SearchService._execute_semantic_search',
        new_callable=AsyncMock
    )
    mock.return_value = [
        {"id": "doc-1", "content": "test result 1", "distance": 0.1},
        {"id": "doc-2", "content": "test result 2", "distance": 0.2},
        {"id": "doc-3", "content": "test result 3", "distance": 0.3}
    ]
    return mock
