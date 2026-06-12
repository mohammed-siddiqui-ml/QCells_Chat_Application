"""
Unit tests for DataSource and SyncLog models - TC-009 through TC-012
"""
import pytest
from datetime import datetime
from sqlalchemy import select

from app.models.user import User, UserRole
from app.models.source import DataSource, SyncLog, SourceType, SyncStatus


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
async def test_data_source_with_all_source_types(clean_db, sample_user_data):
    """TC-009: DataSource Model with SourceType Enum"""
    session = clean_db
    
    # Create user first
    user = User(**sample_user_data)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    
    # Create data source for each type
    sources_data = [
        {
            "name": "Confluence Source",
            "type": SourceType.CONFLUENCE,
            "config": {"url": "https://company.atlassian.net", "space_key": "ENG"}
        },
        {
            "name": "Jira Source",
            "type": SourceType.JIRA,
            "config": {"url": "https://company.atlassian.net", "project_key": "PROJ"}
        },
        {
            "name": "GitHub Source",
            "type": SourceType.GITHUB,
            "config": {"url": "https://github.com/org/repo", "token": "secret"}
        },
        {
            "name": "Onboarding Source",
            "type": SourceType.ONBOARDING,
            "config": {"type": "internal"}
        }
    ]
    
    for source_data in sources_data:
        source = DataSource(
            **source_data,
            created_by=user.id
        )
        session.add(source)
    
    await session.commit()
    
    # Verify all sources
    result = await session.execute(select(DataSource))
    sources = result.scalars().all()
    assert len(sources) == 4
    
    types = {s.type for s in sources}
    assert types == {
        SourceType.CONFLUENCE,
        SourceType.JIRA,
        SourceType.GITHUB,
        SourceType.ONBOARDING
    }
    
    # Verify config JSONB
    for source in sources:
        assert isinstance(source.config, dict)
        assert "url" in source.config or "type" in source.config


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
async def test_data_source_config_jsonb(clean_db, sample_user_data):
    """TC-010: DataSource Config JSONB Encryption Ready"""
    session = clean_db
    
    # Create user
    user = User(**sample_user_data)
    session.add(user)
    await session.commit()
    
    # Create data source with sensitive config
    config = {
        "url": "https://api.example.com",
        "api_key": "secret_key_123",
        "credentials": {
            "username": "admin",
            "password": "sensitive_password"
        }
    }
    
    source = DataSource(
        name="Test Source",
        type=SourceType.CONFLUENCE,
        config=config,
        created_by=user.id
    )
    session.add(source)
    await session.commit()
    
    # Query back
    result = await session.execute(select(DataSource))
    retrieved_source = result.scalar_one()
    
    # Verify config is stored and retrievable
    assert retrieved_source.config == config
    assert retrieved_source.config["credentials"]["password"] == "sensitive_password"


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
async def test_sync_log_creation_and_metrics(clean_db, sample_user_data):
    """TC-011: SyncLog Creation and Metrics Tracking"""
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
    
    # Create sync log
    sync_log = SyncLog(
        source_id=source.id,
        status=SyncStatus.SUCCESS,
        documents_processed=100,
        documents_added=20,
        documents_updated=10,
        documents_deleted=5,
        completed_at=datetime.utcnow()
    )
    session.add(sync_log)
    await session.commit()
    await session.refresh(sync_log)
    
    # Verify all fields
    assert sync_log.source_id == source.id
    assert sync_log.status == SyncStatus.SUCCESS
    assert sync_log.documents_processed == 100
    assert sync_log.documents_added == 20
    assert sync_log.documents_updated == 10
    assert sync_log.documents_deleted == 5
    assert sync_log.completed_at is not None
    assert sync_log.started_at is not None
    
    # Verify relationship
    assert sync_log.source.id == source.id


@pytest.mark.unit
@pytest.mark.database
@pytest.mark.asyncio
async def test_sync_status_enum_transitions(clean_db, sample_user_data):
    """TC-012: SyncStatus Enum State Transitions"""
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
    
    # Create sync log with PENDING status
    sync_log = SyncLog(
        source_id=source.id,
        status=SyncStatus.PENDING
    )
    session.add(sync_log)
    await session.commit()
    await session.refresh(sync_log)
    assert sync_log.status == SyncStatus.PENDING
    
    # Update to SYNCING
    sync_log.status = SyncStatus.SYNCING
    await session.commit()
    await session.refresh(sync_log)
    assert sync_log.status == SyncStatus.SYNCING
    
    # Update to SUCCESS
    sync_log.status = SyncStatus.SUCCESS
    await session.commit()
    await session.refresh(sync_log)
    assert sync_log.status == SyncStatus.SUCCESS
