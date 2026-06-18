"""
Pydantic schemas for admin API endpoints
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.source import SourceType, SyncStatus


# ============================================================================
# Data Source Schemas
# ============================================================================

class DataSourceCreate(BaseModel):
    """Request schema for creating a new data source"""
    name: str = Field(..., min_length=1, max_length=255, description="Data source name")
    type: SourceType = Field(..., description="Data source type")
    config: Dict[str, Any] = Field(..., description="Source configuration (will be encrypted)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Company Confluence",
                "type": "confluence",
                "config": {
                    "url": "https://company.atlassian.net/wiki",
                    "username": "admin@company.com",
                    "api_token": "secret_token_here",
                    "space_keys": ["ENG", "PROD"]
                }
            }
        }


class DataSourceUpdate(BaseModel):
    """Request schema for updating a data source"""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Updated data source name")
    config: Optional[Dict[str, Any]] = Field(None, description="Updated source configuration (will be encrypted)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Updated Confluence Name",
                "config": {
                    "url": "https://company.atlassian.net/wiki",
                    "username": "admin@company.com",
                    "api_token": "new_token_here",
                    "space_keys": ["ENG", "PROD", "OPS"]
                }
            }
        }


class DataSourceResponse(BaseModel):
    """Response schema for data source"""
    id: str = Field(..., description="Data source UUID")
    name: str = Field(..., description="Data source name")
    type: SourceType = Field(..., description="Data source type")
    config: Dict[str, Any] = Field(..., description="Decrypted source configuration")
    last_sync_at: Optional[datetime] = Field(None, description="Last sync timestamp")
    sync_status: SyncStatus = Field(..., description="Current sync status")
    sync_error: Optional[str] = Field(None, description="Last sync error message")
    created_by: str = Field(..., description="Creator user UUID")
    is_active: bool = Field(..., description="Active status")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Company Confluence",
                "type": "confluence",
                "config": {
                    "url": "https://company.atlassian.net/wiki",
                    "space_keys": ["ENG", "PROD"]
                },
                "last_sync_at": "2024-01-01T12:00:00Z",
                "sync_status": "success",
                "sync_error": None,
                "created_by": "user-uuid-here",
                "is_active": True
            }
        }


class DataSourceListResponse(BaseModel):
    """Response schema for paginated data source list"""
    sources: List[DataSourceResponse] = Field(..., description="List of data sources")
    total: int = Field(..., description="Total number of sources")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")
    
    class Config:
        json_schema_extra = {
            "example": {
                "sources": [],
                "total": 10,
                "page": 1,
                "page_size": 20,
                "total_pages": 1
            }
        }


class SyncTriggerResponse(BaseModel):
    """Response schema for manual sync trigger"""
    task_id: str = Field(..., description="Celery task ID")
    source_id: str = Field(..., description="Data source UUID")
    status: str = Field(..., description="Task status")
    message: str = Field(..., description="Status message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "celery-task-uuid-here",
                "source_id": "123e4567-e89b-12d3-a456-426614174000",
                "status": "queued",
                "message": "Data source sync task has been queued"
            }
        }


class DeleteResponse(BaseModel):
    """Response schema for delete operation"""
    success: bool = Field(..., description="Deletion success status")
    message: str = Field(..., description="Status message")
    source_id: str = Field(..., description="Deleted source UUID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Data source soft deleted successfully",
                "source_id": "123e4567-e89b-12d3-a456-426614174000"
            }
        }
