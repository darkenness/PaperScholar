"""Celery application for async task processing."""
import os
from celery import Celery
from kombu import Queue, Exchange

# Redis connection from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "paperscholar",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.generation_tasks"],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3300,  # 55 min soft limit
    worker_prefetch_multiplier=1,  # One task at a time per worker
    worker_max_tasks_per_child=50,  # Restart worker after 50 tasks
    task_acks_late=True,  # Acknowledge after task completion
    task_reject_on_worker_lost=True,
    # Rate limiting per task type
    task_annotations={
        "app.tasks.generation_tasks.generate_figure_task": {
            "rate_limit": "10/m",  # 10 tasks per minute
        },
    },
)

# Define queues with priority
celery_app.conf.task_queues = (
    Queue("default", Exchange("default"), routing_key="default", priority=5),
    Queue("high_priority", Exchange("high_priority"), routing_key="high", priority=10),
    Queue("low_priority", Exchange("low_priority"), routing_key="low", priority=1),
)

# Default queue
celery_app.conf.task_default_queue = "default"
celery_app.conf.task_default_exchange = "default"
celery_app.conf.task_default_routing_key = "default"
