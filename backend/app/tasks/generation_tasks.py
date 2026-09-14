"""Celery tasks for figure generation."""
import asyncio
import logging
from typing import Any, Dict, Optional
from celery import Task
from app.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.generation import GenerationTask
from app.services.generation_service import GenerationService
from app.services.key_pool_service import get_key_pool_manager
from sqlalchemy import select

logger = logging.getLogger(__name__)


class CallbackTask(Task):
    """Base task with callback support."""

    def on_success(self, retval, task_id, args, kwargs):
        """Called when task succeeds."""
        logger.info(f"Task {task_id} succeeded")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when task fails."""
        logger.error(f"Task {task_id} failed: {exc}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called when task is retried."""
        logger.warning(f"Task {task_id} retrying: {exc}")


@celery_app.task(
    base=CallbackTask,
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def generate_figure_task(
    self,
    task_id: str,
    user_id: int,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Celery task for figure generation.

    Args:
        task_id: Generation task UUID
        user_id: User ID
        config: Generation configuration

    Returns:
        Result dictionary with status and data
    """
    try:
        # Run async generation in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _run_generation_async(task_id, user_id, config)
            )
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Generation task {task_id} failed: {e}", exc_info=True)
        # Update task status in database
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_update_task_failed(task_id, str(e)))
        finally:
            loop.close()
        raise


async def _run_generation_async(
    task_id: str,
    user_id: int,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Run generation asynchronously."""
    async with AsyncSessionLocal() as db:
        # Get task from database
        result = await db.execute(
            select(GenerationTask).where(GenerationTask.id == task_id)
        )
        task = result.scalar_one_or_none()

        if not task:
            raise ValueError(f"Task {task_id} not found")

        # Update status to processing
        task.status = "processing"
        await db.commit()

        # Get key pool manager
        key_pool = await get_key_pool_manager()

        # Run generation
        service = GenerationService(db, key_pool)
        result = await service.generate_with_monitoring(
            task_id=task_id,
            user_id=user_id,
            config=config,
        )

        return result


async def _update_task_failed(task_id: str, error: str):
    """Update task status to failed."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(GenerationTask).where(GenerationTask.id == task_id)
        )
        task = result.scalar_one_or_none()

        if task:
            task.status = "failed"
            task.error_message = error
            await db.commit()


@celery_app.task(bind=True)
def health_check_task(self):
    """Health check task for monitoring."""
    return {"status": "healthy", "task_id": self.request.id}


@celery_app.task
def cleanup_old_tasks():
    """Cleanup old completed tasks (run periodically)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_cleanup_old_tasks_async())
        return result
    finally:
        loop.close()


async def _cleanup_old_tasks_async():
    """Cleanup old tasks asynchronously."""
    from datetime import datetime, timedelta
    from sqlalchemy import delete

    async with AsyncSessionLocal() as db:
        # Delete tasks older than 30 days
        cutoff = datetime.utcnow() - timedelta(days=30)
        result = await db.execute(
            delete(GenerationTask).where(
                GenerationTask.created_at < cutoff,
                GenerationTask.status.in_(["completed", "failed", "cancelled"]),
            )
        )
        await db.commit()

        return {"deleted": result.rowcount}
