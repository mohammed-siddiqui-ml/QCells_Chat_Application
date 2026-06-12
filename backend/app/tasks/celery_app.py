"""
Celery application configuration for asynchronous task processing.

This module configures the Celery application with:
- RabbitMQ as the message broker
- Redis as the result backend
- Task routing with priority queues
- Retry policies with exponential backoff
- Task time limits
- Celery beat schedule for periodic tasks
"""
from celery import Celery
from celery.schedules import crontab
from kombu import Queue, Exchange

from app.core.config import settings


# Initialize Celery application
celery_app = Celery(
    "genai_kb_tasks",
    broker=settings.RABBITMQ_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task time limits
    task_soft_time_limit=600,  # 10 minutes soft limit (warning)
    task_time_limit=900,  # 15 minutes hard limit (kill task)
    
    # Task retry settings
    task_acks_late=True,  # Acknowledge task after completion
    task_reject_on_worker_lost=True,  # Reject task if worker dies
    task_track_started=True,  # Track when task starts
    
    # Default retry policy
    task_default_retry_delay=60,  # 1 minute default retry delay
    task_max_retries=3,  # Maximum 3 retries
    
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    result_backend_transport_options={
        "master_name": "mymaster",
        "retry_on_timeout": True,
    },
    
    # Worker settings
    worker_prefetch_multiplier=4,  # Prefetch 4 tasks per worker
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    worker_disable_rate_limits=False,
    
    # Logging
    worker_hijack_root_logger=False,
    worker_log_format="[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
    worker_task_log_format="[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s",
)

# Define task routing with priority queues
default_exchange = Exchange("default", type="direct")

celery_app.conf.task_queues = (
    Queue("high_priority", exchange=default_exchange, routing_key="high_priority", priority=10),
    Queue("normal", exchange=default_exchange, routing_key="normal", priority=5),
    Queue("low_priority", exchange=default_exchange, routing_key="low_priority", priority=1),
)

# Default queue for tasks
celery_app.conf.task_default_queue = "normal"
celery_app.conf.task_default_exchange = "default"
celery_app.conf.task_default_routing_key = "normal"

# Task routes - map specific tasks to specific queues
celery_app.conf.task_routes = {
    # High priority tasks
    "app.tasks.ingestion.process_urgent_document": {"queue": "high_priority"},
    "app.tasks.ingestion.sync_critical_source": {"queue": "high_priority"},
    
    # Normal priority tasks
    "app.tasks.ingestion.ingest_confluence": {"queue": "normal"},
    "app.tasks.ingestion.ingest_jira": {"queue": "normal"},
    "app.tasks.ingestion.generate_embeddings": {"queue": "normal"},
    
    # Low priority tasks
    "app.tasks.maintenance.cleanup_old_data": {"queue": "low_priority"},
    "app.tasks.maintenance.refresh_statistics": {"queue": "low_priority"},
}

# Celery Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    # Data refresh every 6 hours (at 00:00, 06:00, 12:00, 18:00 UTC)
    "scheduled-data-refresh": {
        "task": "app.tasks.scheduled.sync_all_sources",
        "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours
        "options": {
            "queue": "normal",
            "expires": 3600,  # Task expires if not executed within 1 hour
        },
    },
    # Cleanup old task results every day at 2 AM UTC
    "cleanup-old-results": {
        "task": "app.tasks.maintenance.cleanup_task_results",
        "schedule": crontab(minute=0, hour=2),  # Daily at 2 AM
        "options": {
            "queue": "low_priority",
        },
    },
    # Health check every 5 minutes
    "celery-health-check": {
        "task": "app.tasks.monitoring.celery_health_check",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
        "options": {
            "queue": "low_priority",
            "expires": 300,  # Expire after 5 minutes
        },
    },
}

# Auto-discover tasks from all registered apps
celery_app.autodiscover_tasks(["app.tasks"])


# Base task class with automatic retry on failure
class BaseTask(celery_app.Task):
    """Base task with automatic retry and error handling."""
    
    autoretry_for = (Exception,)  # Retry on any exception
    retry_kwargs = {"max_retries": 3}
    retry_backoff = True  # Use exponential backoff
    retry_backoff_max = 600  # Maximum backoff time: 10 minutes
    retry_jitter = True  # Add randomness to backoff to prevent thundering herd


# Make BaseTask the default task class
celery_app.Task = BaseTask


__all__ = ["celery_app"]
