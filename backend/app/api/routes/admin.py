"""
Admin API endpoints for data source management

This module provides:
- GET /sources - List all data sources with pagination
- POST /sources - Create new data source with encrypted config
- GET /sources/:id - Get specific data source details
- PUT /sources/:id - Update data source configuration
- DELETE /sources/:id - Soft delete data source
- POST /sources/:id/sync - Trigger manual sync
"""
import math
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.core.encryption import encryption_service
from app.db.session import get_db
from app.middleware.auth_middleware import get_current_active_user, require_admin
from app.models import User, UserRole, DataSource, SyncStatus
from app.schemas.admin import (
    DataSourceCreate,
    DataSourceUpdate,
    DataSourceResponse,
    DataSourceListResponse,
    SyncTriggerResponse,
    DeleteResponse,
)


router = APIRouter()


@router.get(
    "/sources",
    response_model=DataSourceListResponse,
    summary="List all data sources",
    description="Get paginated list of all data sources with sync status. Requires admin role.",
)
@require_admin
async def list_sources(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> DataSourceListResponse:
    """
    List all data sources with pagination.
    
    - **page**: Page number (1-indexed)
    - **page_size**: Number of items per page (1-100)
    
    Returns paginated list with sync status for each source.
    Requires admin authentication.
    """
    try:
        # Count total sources
        count_stmt = select(func.count(DataSource.id))
        count_result = await db.execute(count_stmt)
        total = count_result.scalar_one()
        
        # Calculate pagination
        total_pages = math.ceil(total / page_size) if total > 0 else 1
        offset = (page - 1) * page_size
        
        # Query sources with pagination
        stmt = (
            select(DataSource)
            .offset(offset)
            .limit(page_size)
            .order_by(DataSource.name)
        )
        result = await db.execute(stmt)
        sources = result.scalars().all()
        
        # Decrypt configs and build response
        source_responses = []
        for source in sources:
            try:
                # Decrypt config for response
                decrypted_config = encryption_service.decrypt_config(source.config.get("encrypted", "{}"))
                
                source_responses.append(DataSourceResponse(
                    id=str(source.id),
                    name=source.name,
                    type=source.type,
                    config=decrypted_config,
                    last_sync_at=source.last_sync_at,
                    sync_status=source.sync_status,
                    sync_error=source.sync_error,
                    created_by=str(source.created_by),
                    is_active=source.is_active
                ))
            except Exception as e:
                logger.error(f"Failed to decrypt config for source {source.id}: {e}")
                # Return with masked config if decryption fails
                source_responses.append(DataSourceResponse(
                    id=str(source.id),
                    name=source.name,
                    type=source.type,
                    config={"error": "Failed to decrypt config"},
                    last_sync_at=source.last_sync_at,
                    sync_status=source.sync_status,
                    sync_error=source.sync_error,
                    created_by=str(source.created_by),
                    is_active=source.is_active
                ))
        
        logger.info(f"Listed {len(source_responses)} sources (page {page}/{total_pages})")
        return DataSourceListResponse(
            sources=source_responses,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
        
    except Exception as e:
        logger.error(f"Error listing sources: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list data sources"
        )


@router.post(
    "/sources",
    response_model=DataSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new data source",
    description="Create a new data source with encrypted configuration. Requires admin role.",
)
@require_admin
async def create_source(
    source_data: DataSourceCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> DataSourceResponse:
    """
    Create a new data source.

    - **name**: Unique name for the data source
    - **type**: Source type (confluence, jira, github, onboarding)
    - **config**: Configuration object (will be encrypted using Fernet)

    Configuration is encrypted before storage and decrypted on retrieval.
    Requires admin authentication.
    """
    try:
        # Encrypt the configuration
        encrypted_config_str = encryption_service.encrypt_config(source_data.config)

        # Store encrypted config in a wrapper dict
        encrypted_config_dict = {"encrypted": encrypted_config_str}

        # Create data source
        new_source = DataSource(
            name=source_data.name,
            type=source_data.type,
            config=encrypted_config_dict,
            created_by=current_user.id,
            sync_status=SyncStatus.PENDING,
            is_active=True
        )

        db.add(new_source)
        await db.commit()
        await db.refresh(new_source)

        logger.info(
            f"Data source created: {new_source.name} (id: {new_source.id}, "
            f"type: {new_source.type.value}) by user {current_user.email}"
        )

        return DataSourceResponse(
            id=str(new_source.id),
            name=new_source.name,
            type=new_source.type,
            config=source_data.config,  # Return original unencrypted config
            last_sync_at=new_source.last_sync_at,
            sync_status=new_source.sync_status,
            sync_error=new_source.sync_error,
            created_by=str(new_source.created_by),
            is_active=new_source.is_active
        )

    except Exception as e:
        logger.error(f"Error creating source: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create data source: {str(e)}"
        )


@router.get(
    "/sources/{source_id}",
    response_model=DataSourceResponse,
    summary="Get data source details",
    description="Get specific data source by ID with decrypted configuration. Requires admin role.",
)
@require_admin
async def get_source(
    source_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> DataSourceResponse:
    """
    Get data source details by ID.

    - **source_id**: UUID of the data source

    Returns source with decrypted configuration.
    Requires admin authentication.
    """
    try:
        # Parse UUID
        try:
            source_uuid = UUID(source_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid source ID format"
            )

        # Query source
        result = await db.execute(
            select(DataSource).where(DataSource.id == source_uuid)
        )
        source = result.scalar_one_or_none()

        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Data source not found"
            )

        # Decrypt config
        try:
            decrypted_config = encryption_service.decrypt_config(
                source.config.get("encrypted", "{}")
            )
        except Exception as e:
            logger.error(f"Failed to decrypt config for source {source_id}: {e}")
            decrypted_config = {"error": "Failed to decrypt config"}

        logger.info(f"Retrieved source: {source.name} (id: {source_id})")

        return DataSourceResponse(
            id=str(source.id),
            name=source.name,
            type=source.type,
            config=decrypted_config,
            last_sync_at=source.last_sync_at,
            sync_status=source.sync_status,
            sync_error=source.sync_error,
            created_by=str(source.created_by),
            is_active=source.is_active
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving source {source_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve data source"
        )


@router.put(
    "/sources/{source_id}",
    response_model=DataSourceResponse,
    summary="Update data source",
    description="Update data source name and/or configuration. Requires admin role.",
)
@require_admin
async def update_source(
    source_id: str,
    update_data: DataSourceUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> DataSourceResponse:
    """
    Update data source configuration.

    - **source_id**: UUID of the data source
    - **name**: Optional new name
    - **config**: Optional new configuration (will be encrypted)

    Only provided fields will be updated.
    Requires admin authentication.
    """
    try:
        # Parse UUID
        try:
            source_uuid = UUID(source_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid source ID format"
            )

        # Query source
        result = await db.execute(
            select(DataSource).where(DataSource.id == source_uuid)
        )
        source = result.scalar_one_or_none()

        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Data source not found"
            )

        # Update fields
        if update_data.name is not None:
            source.name = update_data.name

        if update_data.config is not None:
            # Encrypt new config
            encrypted_config_str = encryption_service.encrypt_config(update_data.config)
            source.config = {"encrypted": encrypted_config_str}

        await db.commit()
        await db.refresh(source)

        # Decrypt config for response
        try:
            decrypted_config = encryption_service.decrypt_config(
                source.config.get("encrypted", "{}")
            )
        except Exception as e:
            logger.error(f"Failed to decrypt updated config: {e}")
            decrypted_config = {"error": "Failed to decrypt config"}

        logger.info(
            f"Data source updated: {source.name} (id: {source_id}) by user {current_user.email}"
        )

        return DataSourceResponse(
            id=str(source.id),
            name=source.name,
            type=source.type,
            config=decrypted_config,
            last_sync_at=source.last_sync_at,
            sync_status=source.sync_status,
            sync_error=source.sync_error,
            created_by=str(source.created_by),
            is_active=source.is_active
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating source {source_id}: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update data source"
        )


@router.delete(
    "/sources/{source_id}",
    response_model=DeleteResponse,
    summary="Delete data source",
    description="Soft delete data source by setting is_active=false. Requires admin role.",
)
@require_admin
async def delete_source(
    source_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> DeleteResponse:
    """
    Soft delete a data source.

    - **source_id**: UUID of the data source

    Sets is_active=false instead of permanent deletion.
    Requires admin authentication.
    """
    try:
        # Parse UUID
        try:
            source_uuid = UUID(source_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid source ID format"
            )

        # Query source
        result = await db.execute(
            select(DataSource).where(DataSource.id == source_uuid)
        )
        source = result.scalar_one_or_none()

        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Data source not found"
            )

        # Soft delete
        source.is_active = False
        await db.commit()

        logger.info(
            f"Data source soft deleted: {source.name} (id: {source_id}) "
            f"by user {current_user.email}"
        )

        return DeleteResponse(
            success=True,
            message="Data source soft deleted successfully",
            source_id=source_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting source {source_id}: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete data source"
        )


@router.post(
    "/sources/{source_id}/sync",
    status_code=202,
    response_model=SyncTriggerResponse,
    summary="Trigger manual sync",
    description="Trigger manual data synchronization for a data source. Requires admin role.",
)
@require_admin
async def trigger_sync(
    source_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> SyncTriggerResponse:
    """
    Trigger manual sync for a data source.

    - **source_id**: UUID of the data source

    Queues a Celery task for data ingestion based on source type.
    Requires admin authentication.
    """
    try:
        # Parse UUID
        try:
            source_uuid = UUID(source_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid source ID format"
            )

        # Query source
        result = await db.execute(
            select(DataSource).where(DataSource.id == source_uuid)
        )
        source = result.scalar_one_or_none()

        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Data source not found"
            )

        if not source.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot sync inactive data source"
            )

        # Import Celery app for task dispatch
        from app.tasks.celery_app import celery_app

        # Determine task based on source type
        task_name_map = {
            "confluence": "app.tasks.ingestion.ingest_confluence",
            "jira": "app.tasks.ingestion.ingest_jira",
            "github": "app.tasks.ingestion.ingest_github",
            "onboarding": "app.tasks.ingestion.ingest_onboarding",
        }

        task_name = task_name_map.get(source.type.value)

        if not task_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Sync not implemented for source type: {source.type.value}"
            )

        # Update source status to SYNCING
        source.sync_status = SyncStatus.SYNCING
        source.sync_error = None
        await db.commit()

        # Dispatch Celery task
        task = celery_app.send_task(
            task_name,
            args=[str(source.id)],
            queue="normal"
        )

        logger.info(
            f"Sync task triggered for source {source.name} (id: {source_id}, "
            f"task_id: {task.id}) by user {current_user.email}"
        )

        return SyncTriggerResponse(
            task_id=task.id,
            source_id=source_id,
            status="queued",
            message=f"Data source sync task has been queued for {source.type.value}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering sync for source {source_id}: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger sync"
        )
