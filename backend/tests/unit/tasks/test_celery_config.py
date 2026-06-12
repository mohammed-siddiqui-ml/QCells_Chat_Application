"""
Unit tests for Celery application configuration.

Tests TC-001 through TC-007 and TC-012 from the test plan.
These tests verify the Celery configuration without requiring external services.
"""
import pytest
from celery.schedules import crontab
from kombu import Queue, Exchange

from app.tasks.celery_app import celery_app, BaseTask
from app.core.config import settings


@pytest.mark.unit
class TestCeleryAppInitialization:
    """Test Case TC-001: Celery App Initialization with RabbitMQ Broker"""
    
    def test_celery_broker_configuration(self):
        """Verify Celery app is configured with correct broker URL."""
        assert celery_app.conf.broker_url == settings.RABBITMQ_URL
        assert "amqp://" in celery_app.conf.broker_url or "memory://" in celery_app.conf.broker_url
    
    def test_celery_result_backend(self):
        """Verify Celery result backend is configured correctly."""
        assert celery_app.conf.result_backend == settings.CELERY_RESULT_BACKEND
        assert "redis://" in celery_app.conf.result_backend or "cache+" in celery_app.conf.result_backend
    
    def test_celery_app_name(self):
        """Verify Celery application has correct name."""
        assert celery_app.main == "genai_kb_tasks"


@pytest.mark.unit
class TestPriorityQueueConfiguration:
    """Test Case TC-002: Priority Queue Definitions"""
    
    def test_queue_count(self):
        """Verify 3 priority queues are defined."""
        assert len(celery_app.conf.task_queues) == 3
    
    def test_queue_names(self):
        """Verify queue names are correct."""
        queue_names = [q.name for q in celery_app.conf.task_queues]
        assert "high_priority" in queue_names
        assert "normal" in queue_names
        assert "low_priority" in queue_names
    
    def test_high_priority_queue(self):
        """Verify high_priority queue configuration."""
        high_queue = next(q for q in celery_app.conf.task_queues if q.name == "high_priority")
        assert high_queue.routing_key == "high_priority"
        assert high_queue.exchange.name == "default"
        assert high_queue.exchange.type == "direct"

    def test_normal_queue(self):
        """Verify normal queue configuration."""
        normal_queue = next(q for q in celery_app.conf.task_queues if q.name == "normal")
        assert normal_queue.routing_key == "normal"
        assert normal_queue.exchange.name == "default"

    def test_low_priority_queue(self):
        """Verify low_priority queue configuration."""
        low_queue = next(q for q in celery_app.conf.task_queues if q.name == "low_priority")
        assert low_queue.routing_key == "low_priority"
        assert low_queue.exchange.name == "default"


@pytest.mark.unit
class TestTaskRouting:
    """Test Case TC-003: Task Routing Configuration"""
    
    def test_task_routes_exist(self):
        """Verify task routes are configured."""
        assert celery_app.conf.task_routes is not None
        assert isinstance(celery_app.conf.task_routes, dict)
    
    def test_high_priority_routing(self):
        """Verify high priority tasks route to high_priority queue."""
        assert celery_app.conf.task_routes.get("app.tasks.ingestion.process_urgent_document") == {"queue": "high_priority"}
        assert celery_app.conf.task_routes.get("app.tasks.ingestion.sync_critical_source") == {"queue": "high_priority"}
    
    def test_normal_priority_routing(self):
        """Verify normal priority tasks route to normal queue."""
        assert celery_app.conf.task_routes.get("app.tasks.ingestion.ingest_confluence") == {"queue": "normal"}
        assert celery_app.conf.task_routes.get("app.tasks.ingestion.ingest_jira") == {"queue": "normal"}
    
    def test_low_priority_routing(self):
        """Verify low priority tasks route to low_priority queue."""
        assert celery_app.conf.task_routes.get("app.tasks.maintenance.cleanup_old_data") == {"queue": "low_priority"}
    
    def test_default_queue(self):
        """Verify default queue is 'normal'."""
        assert celery_app.conf.task_default_queue == "normal"


@pytest.mark.unit
class TestRetryPolicy:
    """Test Case TC-004: Retry Policy with Exponential Backoff"""
    
    def test_max_retries(self):
        """Verify max retries is set to 3."""
        assert celery_app.conf.task_max_retries == 3
    
    def test_base_task_retry_config(self):
        """Verify BaseTask has correct retry configuration."""
        assert BaseTask.retry_kwargs["max_retries"] == 3
        assert BaseTask.retry_backoff is True
        assert BaseTask.retry_backoff_max == 600
        assert BaseTask.retry_jitter is True
    
    def test_autoretry_for_exceptions(self):
        """Verify BaseTask auto-retries on exceptions."""
        assert BaseTask.autoretry_for == (Exception,)


@pytest.mark.unit
class TestTaskTimeLimits:
    """Test Case TC-005: Task Time Limits"""

    def test_soft_time_limit(self):
        """Verify soft time limit is 600 seconds (10 minutes)."""
        assert celery_app.conf.task_soft_time_limit == 600

    def test_hard_time_limit(self):
        """Verify hard time limit is 900 seconds (15 minutes)."""
        assert celery_app.conf.task_time_limit == 900


@pytest.mark.unit
class TestCeleryBeatSchedule:
    """Test Cases TC-006 and TC-007: Celery Beat Schedule"""

    def test_beat_schedule_exists(self):
        """Verify beat schedule is configured."""
        assert celery_app.conf.beat_schedule is not None
        assert isinstance(celery_app.conf.beat_schedule, dict)

    def test_scheduled_data_refresh(self):
        """Verify scheduled-data-refresh task configuration."""
        task = celery_app.conf.beat_schedule.get("scheduled-data-refresh")
        assert task is not None
        assert task["task"] == "app.tasks.scheduled.sync_all_sources"
        assert isinstance(task["schedule"], crontab)
        assert task["schedule"].minute == {0}
        assert task["schedule"].hour == {0, 6, 12, 18}  # Every 6 hours
        assert task["options"]["queue"] == "normal"
        assert task["options"]["expires"] == 3600

    def test_cleanup_old_results(self):
        """Verify cleanup-old-results task configuration."""
        task = celery_app.conf.beat_schedule.get("cleanup-old-results")
        assert task is not None
        assert task["task"] == "app.tasks.maintenance.cleanup_task_results"
        assert isinstance(task["schedule"], crontab)
        assert task["schedule"].minute == {0}
        assert task["schedule"].hour == {2}  # Daily at 2 AM
        assert task["options"]["queue"] == "low_priority"

    def test_celery_health_check(self):
        """Verify celery-health-check task configuration."""
        task = celery_app.conf.beat_schedule.get("celery-health-check")
        assert task is not None
        assert task["task"] == "app.tasks.monitoring.celery_health_check"
        assert isinstance(task["schedule"], crontab)
        assert task["schedule"].minute == {0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}  # Every 5 minutes
        assert task["options"]["queue"] == "low_priority"
        assert task["options"]["expires"] == 300


@pytest.mark.unit
class TestConfigurationValidation:
    """Test Case TC-012: Configuration Validation"""

    def test_task_serializer(self):
        """Verify task serializer is JSON."""
        assert celery_app.conf.task_serializer == "json"

    def test_accept_content(self):
        """Verify accept_content includes JSON."""
        assert "json" in celery_app.conf.accept_content

    def test_timezone(self):
        """Verify timezone is UTC."""
        assert celery_app.conf.timezone == "UTC"

    def test_task_acks_late(self):
        """Verify task_acks_late is enabled."""
        assert celery_app.conf.task_acks_late is True

    def test_task_track_started(self):
        """Verify task_track_started is enabled."""
        assert celery_app.conf.task_track_started is True

    def test_worker_prefetch_multiplier(self):
        """Verify worker_prefetch_multiplier is set."""
        assert celery_app.conf.worker_prefetch_multiplier == 4
