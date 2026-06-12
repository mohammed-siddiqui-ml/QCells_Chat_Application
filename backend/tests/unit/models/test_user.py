"""
Unit tests for User model - TC-001, TC-002, TC-003
"""
import pytest
from datetime import datetime
import uuid
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.user import User, UserRole


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
async def test_user_creation_with_all_fields(clean_db, sample_user_data):
    """TC-001: User Model Creation and Fields"""
    session = clean_db
    
    # Create user
    user = User(**sample_user_data)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    
    # Verify all fields
    assert user.id is not None
    assert isinstance(user.id, uuid.UUID)
    assert user.email == sample_user_data["email"]
    assert user.password_hash == sample_user_data["password_hash"]
    assert user.role == UserRole.ADMIN
    assert user.is_active is True  # default
    assert user.last_login is None  # default
    assert isinstance(user.created_at, datetime)
    
    # Verify relationships are initialized
    assert user.chat_sessions == []
    assert user.data_sources == []


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
async def test_user_email_unique_constraint(clean_db, sample_user_data):
    """TC-002: User Email Unique Constraint"""
    session = clean_db
    
    # Create first user
    user1 = User(**sample_user_data)
    session.add(user1)
    await session.commit()
    
    # Attempt to create second user with same email
    user2 = User(**sample_user_data)
    session.add(user2)
    
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
async def test_user_role_enum_validation(clean_db):
    """TC-003: UserRole Enum Validation"""
    session = clean_db
    
    # Test ADMIN role
    admin_user = User(
        email="admin@example.com",
        password_hash="hash123",
        role=UserRole.ADMIN
    )
    session.add(admin_user)
    await session.commit()
    await session.refresh(admin_user)
    assert admin_user.role == UserRole.ADMIN
    
    # Test USER role
    regular_user = User(
        email="user@example.com",
        password_hash="hash123",
        role=UserRole.USER
    )
    session.add(regular_user)
    await session.commit()
    await session.refresh(regular_user)
    assert regular_user.role == UserRole.USER
    
    # Test ANONYMOUS role
    anon_user = User(
        email=None,
        password_hash=None,
        role=UserRole.ANONYMOUS
    )
    session.add(anon_user)
    await session.commit()
    await session.refresh(anon_user)
    assert anon_user.role == UserRole.ANONYMOUS
    
    # Verify all three users exist
    result = await session.execute(select(User))
    users = result.scalars().all()
    assert len(users) == 3
    
    roles = {user.role for user in users}
    assert roles == {UserRole.ADMIN, UserRole.USER, UserRole.ANONYMOUS}


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
async def test_user_default_values(clean_db):
    """Test User model default values"""
    session = clean_db
    
    # Create user with minimal data
    user = User(email="minimal@example.com")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    
    # Verify defaults
    assert user.role == UserRole.ANONYMOUS  # default role
    assert user.is_active is True
    assert user.password_hash is None
    assert user.last_login is None
    assert user.created_at is not None
