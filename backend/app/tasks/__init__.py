"""
Celery tasks package for asynchronous job processing.

This package contains Celery tasks for:
- Data ingestion from external sources
- Scheduled data synchronization
- Background processing of embeddings
- Periodic cleanup and maintenance
"""
from app.tasks.celery_app import celery_app

__all__ = ["celery_app"]
