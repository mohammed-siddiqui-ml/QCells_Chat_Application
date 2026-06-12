"""
Database session management
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import settings

# Determine engine configuration based on database type
is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# Create async engine with conditional pool settings
if is_sqlite:
    # SQLite doesn't support pool_size and max_overflow
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    )
else:
    # PostgreSQL and other databases support pooling
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        echo=settings.DEBUG,
    )

# Create async session factory
async_session_maker = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Create declarative base with async support
class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models with async support"""
    pass


async def get_db() -> AsyncSession:
    """
    Dependency for getting async database sessions
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
