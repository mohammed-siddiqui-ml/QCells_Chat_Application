"""
Integration tests for Admin API endpoints (app/api/routes/admin.py)

Test coverage:
- List data sources (GET /api/v1/admin/sources)
- Create data source (POST /api/v1/admin/sources)
- Get data source (GET /api/v1/admin/sources/{id})
- Update data source (PUT /api/v1/admin/sources/{id})
- Delete data source (DELETE /api/v1/admin/sources/{id})
- Trigger sync (POST /api/v1/admin/sources/{id}/sync)
- Authorization and RBAC
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from fastapi import FastAPI

# Mock Celery BEFORE importing the admin router
import sys
sys.modules['app.tasks.celery_app'] = MagicMock()

from app.db.session import get_db
from app.api.routes.admin import router
from app.models.user import User, UserRole
from app.models.source import DataSource, SourceType, SyncStatus
from app.core.security import create_access_token
from app.core.encryption import encryption_service


@pytest.fixture
def test_app():
    """Create a minimal FastAPI app with only admin router for testing"""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/admin", tags=["admin"])
    return app


@pytest_asyncio.fixture
async def admin_user(db_session):
    """Create admin user for testing"""
    user = User(
        email="admin@test.com",
        password_hash="dummy_hash",
        role=UserRole.ADMIN,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def regular_user(db_session):
    """Create regular user for testing"""
    user = User(
        email="user@test.com",
        password_hash="dummy_hash",
        role=UserRole.USER,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def client(db_session, test_app, admin_user):
    """Create async HTTP client for API testing with admin user"""
    # Import the dependency we need to override
    from app.middleware.auth_middleware import get_current_active_user

    # Override get_db dependency to use test database
    async def override_get_db():
        yield db_session

    # Override get_current_active_user to return admin_user by default
    def override_get_current_user():
        return admin_user

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_active_user] = override_get_current_user

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    test_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_regular_user(db_session, test_app, regular_user):
    """Create async HTTP client for API testing with regular (non-admin) user"""
    # Import the dependency we need to override
    from app.middleware.auth_middleware import get_current_active_user

    # Override get_db dependency to use test database
    async def override_get_db():
        yield db_session

    # Override get_current_active_user to return regular_user
    def override_get_current_user():
        return regular_user

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_active_user] = override_get_current_user

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    test_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_unauthenticated(db_session, test_app):
    """Create async HTTP client for testing unauthenticated requests"""
    # Import the dependency we need to override
    from app.middleware.auth_middleware import get_current_active_user

    # Override get_db dependency to use test database
    async def override_get_db():
        yield db_session

    # Override get_current_active_user to raise 401 (simulating unauthenticated)
    def override_get_current_user():
        from fastapi import HTTPException, status as http_status
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_active_user] = override_get_current_user

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    test_app.dependency_overrides.clear()


def get_auth_headers(user: User) -> dict:
    """
    Generate authorization headers for a user.
    NOTE: This is now deprecated since we override the dependency directly.
    Kept for backward compatibility but not used in new tests.
    """
    token = create_access_token(data={"user_id": str(user.id), "email": user.email, "role": user.role.value})
    return {"Authorization": f"Bearer {token}"}


# TC-010: List Sources - Empty List (Admin)
@pytest.mark.asyncio
async def test_list_sources_empty(client):
    """Test listing data sources when none exist"""
    response = await client.get("/api/v1/admin/sources")

    assert response.status_code == 200
    data = response.json()
    assert data["sources"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total_pages"] == 0


# TC-012: List Sources - Unauthenticated
@pytest.mark.asyncio
async def test_list_sources_unauthenticated(client_unauthenticated):
    """Test listing sources without authentication"""
    response = await client_unauthenticated.get("/api/v1/admin/sources")
    assert response.status_code == 401


# TC-013: List Sources - Non-Admin User
@pytest.mark.asyncio
async def test_list_sources_non_admin(client_regular_user):
    """Test that non-admin users cannot list sources"""
    response = await client_regular_user.get("/api/v1/admin/sources")
    assert response.status_code == 403


# TC-020: Create Source - Valid Confluence (Admin)
@pytest.mark.asyncio
async def test_create_source_confluence_admin(client, db_session):
    """Test creating a Confluence data source as admin"""
    payload = {
        "name": "Company Confluence",
        "type": "confluence",
        "config": {
            "url": "https://company.atlassian.net/wiki",
            "username": "admin@company.com",
            "api_token": "secret_token_123",
            "space_keys": ["ENG", "PROD"]
        }
    }

    response = await client.post("/api/v1/admin/sources", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Company Confluence"
    assert data["type"] == "confluence"
    assert data["sync_status"] == "pending"
    assert "id" in data

    # Verify config is decrypted in response
    assert data["config"]["url"] == "https://company.atlassian.net/wiki"

    # Verify config is encrypted in database
    result = await db_session.execute(
        select(DataSource).where(DataSource.id == data["id"])
    )
    source = result.scalar_one()
    assert "encrypted" in source.config
    assert "secret_token_123" not in str(source.config)


# TC-022: Create Source - Invalid Type
@pytest.mark.asyncio
async def test_create_source_invalid_type(client):
    """Test creating source with invalid type"""
    payload = {
        "name": "Test",
        "type": "invalid_type",
        "config": {}
    }

    response = await client.post("/api/v1/admin/sources", json=payload)
    assert response.status_code == 422


# TC-023: Create Source - Missing Config
@pytest.mark.asyncio
async def test_create_source_missing_config(client):
    """Test creating source without config field"""
    payload = {
        "name": "Test",
        "type": "jira"
    }

    response = await client.post("/api/v1/admin/sources", json=payload)
    assert response.status_code == 422


# TC-025: Create Source - Non-Admin User
@pytest.mark.asyncio
async def test_create_source_non_admin(client_regular_user):
    """Test that non-admin cannot create sources"""
    payload = {
        "name": "Test",
        "type": "jira",
        "config": {}
    }

    response = await client_regular_user.post("/api/v1/admin/sources", json=payload)
    assert response.status_code == 403


# TC-030: Get Source - Valid ID (Admin)
@pytest.mark.asyncio
async def test_get_source_valid_id(client, admin_user, db_session):
    """Test getting a specific source by ID"""
    # Create source first
    config_dict = {"url": "https://test.com", "token": "secret"}
    encrypted_config = encryption_service.encrypt_config(config_dict)

    source = DataSource(
        name="Test Source",
        type=SourceType.CONFLUENCE,
        config={"encrypted": encrypted_config},
        created_by=admin_user.id
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    response = await client.get(f"/api/v1/admin/sources/{source.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(source.id)
    assert data["name"] == "Test Source"
    assert data["config"]["url"] == "https://test.com"


# TC-031: Get Source - Invalid UUID Format
@pytest.mark.asyncio
async def test_get_source_invalid_uuid(client):
    """Test getting source with invalid UUID"""
    response = await client.get("/api/v1/admin/sources/not-a-uuid")
    assert response.status_code == 400


# TC-032: Get Source - Non-Existent ID
@pytest.mark.asyncio
async def test_get_source_not_found(client):
    """Test getting source that doesn't exist"""
    response = await client.get("/api/v1/admin/sources/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


# TC-033: Get Source - Non-Admin User
@pytest.mark.asyncio
async def test_get_source_non_admin(client_regular_user, db_session, admin_user):
    """Test that non-admin cannot get source details"""
    # Create source first
    source = DataSource(
        name="Test Source",
        type=SourceType.JIRA,
        config={"encrypted": encryption_service.encrypt_config({})},
        created_by=admin_user.id
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    response = await client_regular_user.get(f"/api/v1/admin/sources/{source.id}")
    assert response.status_code == 403


# TC-040: Update Source - Update Name Only (Admin)
@pytest.mark.asyncio
async def test_update_source_name_only(client, admin_user, db_session):
    """Test updating only the source name"""
    # Create source
    source = DataSource(
        name="Old Name",
        type=SourceType.GITHUB,
        config={"encrypted": encryption_service.encrypt_config({"key": "value"})},
        created_by=admin_user.id
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    response = await client.put(
        f"/api/v1/admin/sources/{source.id}",
        json={"name": "New Name"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["config"]["key"] == "value"  # Config unchanged


# TC-041: Update Source - Update Config Only
@pytest.mark.asyncio
async def test_update_source_config_only(client, admin_user, db_session):
    """Test updating only the source config"""
    source = DataSource(
        name="Test Source",
        type=SourceType.CONFLUENCE,
        config={"encrypted": encryption_service.encrypt_config({"old": "config"})},
        created_by=admin_user.id
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    response = await client.put(
        f"/api/v1/admin/sources/{source.id}",
        json={"config": {"new_key": "new_value"}}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Source"  # Name unchanged
    assert data["config"]["new_key"] == "new_value"


# TC-044: Update Source - Non-Existent ID
@pytest.mark.asyncio
async def test_update_source_not_found(client):
    """Test updating non-existent source"""
    response = await client.put(
        "/api/v1/admin/sources/00000000-0000-0000-0000-000000000000",
        json={"name": "New Name"}
    )
    assert response.status_code == 404


# TC-045: Update Source - Non-Admin User
@pytest.mark.asyncio
async def test_update_source_non_admin(client_regular_user, db_session, admin_user):
    """Test that non-admin cannot update sources"""
    source = DataSource(
        name="Test Source",
        type=SourceType.JIRA,
        config={"encrypted": encryption_service.encrypt_config({})},
        created_by=admin_user.id
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    response = await client_regular_user.put(
        f"/api/v1/admin/sources/{source.id}",
        json={"name": "New Name"}
    )
    assert response.status_code == 403


# TC-050: Delete Source - Soft Delete (Admin)
@pytest.mark.asyncio
async def test_delete_source_soft_delete(client, admin_user, db_session):
    """Test soft deleting a source (sets is_active=false)"""
    source = DataSource(
        name="To Delete",
        type=SourceType.GITHUB,
        config={"encrypted": encryption_service.encrypt_config({})},
        created_by=admin_user.id,
        is_active=True
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    source_id = source.id

    response = await client.delete(f"/api/v1/admin/sources/{source_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["source_id"] == str(source_id)

    # Verify source still exists but is_active=false
    result = await db_session.execute(
        select(DataSource).where(DataSource.id == source_id)
    )
    deleted_source = result.scalar_one()
    assert deleted_source.is_active is False


# TC-052: Delete Source - Non-Existent ID
@pytest.mark.asyncio
async def test_delete_source_not_found(client):
    """Test deleting non-existent source"""
    response = await client.delete(
        "/api/v1/admin/sources/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404


# TC-053: Delete Source - Non-Admin User
@pytest.mark.asyncio
async def test_delete_source_non_admin(client_regular_user, db_session, admin_user):
    """Test that non-admin cannot delete sources"""
    source = DataSource(
        name="Test Source",
        type=SourceType.JIRA,
        config={"encrypted": encryption_service.encrypt_config({})},
        created_by=admin_user.id
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    response = await client_regular_user.delete(f"/api/v1/admin/sources/{source.id}")
    assert response.status_code == 403


# TC-060: Trigger Sync - Confluence Source (Admin)
@pytest.mark.asyncio
@patch("app.tasks.celery_app.celery_app")
async def test_trigger_sync_confluence(mock_celery_app, client, admin_user, db_session):
    """Test triggering sync for Confluence source"""
    # Mock celery task
    mock_task = MagicMock()
    mock_task.id = "test-task-id-123"
    mock_celery_app.send_task.return_value = mock_task

    # Create source
    source = DataSource(
        name="Test Confluence",
        type=SourceType.CONFLUENCE,
        config={"encrypted": encryption_service.encrypt_config({})},
        created_by=admin_user.id,
        is_active=True
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    response = await client.post(
        f"/api/v1/admin/sources/{source.id}/sync"
    )

    assert response.status_code == 202
    data = response.json()
    assert data["task_id"] == "test-task-id-123"
    assert data["source_id"] == str(source.id)
    assert data["status"] == "queued"

    # Verify Celery task was called
    mock_celery_app.send_task.assert_called_once_with(
        "app.tasks.ingestion.ingest_confluence",
        args=[str(source.id)],
        queue="normal"
    )


# TC-062: Trigger Sync - GitHub Source
@pytest.mark.asyncio
@patch("app.tasks.celery_app.celery_app")
async def test_trigger_sync_github(mock_celery_app, client, admin_user, db_session):
    """Test triggering sync for GitHub source"""
    mock_task = MagicMock()
    mock_task.id = "github-task-id"
    mock_celery_app.send_task.return_value = mock_task

    source = DataSource(
        name="Test GitHub",
        type=SourceType.GITHUB,
        config={"encrypted": encryption_service.encrypt_config({})},
        created_by=admin_user.id,
        is_active=True
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    response = await client.post(f"/api/v1/admin/sources/{source.id}/sync")

    assert response.status_code == 202
    mock_celery_app.send_task.assert_called_once_with(
        "app.tasks.ingestion.ingest_github",
        args=[str(source.id)],
        queue="normal"
    )


# TC-064: Trigger Sync - Inactive Source
@pytest.mark.asyncio
async def test_trigger_sync_inactive_source(client, admin_user, db_session):
    """Test that syncing inactive source fails"""
    source = DataSource(
        name="Inactive Source",
        type=SourceType.JIRA,
        config={"encrypted": encryption_service.encrypt_config({})},
        created_by=admin_user.id,
        is_active=False  # Inactive
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    response = await client.post(f"/api/v1/admin/sources/{source.id}/sync")
    assert response.status_code == 400


# TC-065: Trigger Sync - Non-Existent Source
@pytest.mark.asyncio
async def test_trigger_sync_not_found(client):
    """Test triggering sync for non-existent source"""
    response = await client.post(
        "/api/v1/admin/sources/00000000-0000-0000-0000-000000000000/sync"
    )
    assert response.status_code == 404


# TC-067: Trigger Sync - Non-Admin User
@pytest.mark.asyncio
async def test_trigger_sync_non_admin(client_regular_user, db_session, admin_user):
    """Test that non-admin cannot trigger sync"""
    source = DataSource(
        name="Test Source",
        type=SourceType.CONFLUENCE,
        config={"encrypted": encryption_service.encrypt_config({})},
        created_by=admin_user.id,
        is_active=True
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    response = await client_regular_user.post(f"/api/v1/admin/sources/{source.id}/sync")
    assert response.status_code == 403


# TC-011: List Sources - Paginated Results (Admin)
@pytest.mark.asyncio
async def test_list_sources_paginated(client, admin_user, db_session):
    """Test listing sources with pagination"""
    # Create 3 sources
    for i in range(3):
        source = DataSource(
            name=f"Source {i}",
            type=SourceType.CONFLUENCE,
            config={"encrypted": encryption_service.encrypt_config({"index": i})},
            created_by=admin_user.id
        )
        db_session.add(source)
    await db_session.commit()

    response = await client.get("/api/v1/admin/sources?page=1&page_size=2")

    assert response.status_code == 200
    data = response.json()
    assert len(data["sources"]) == 2
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total_pages"] == 2