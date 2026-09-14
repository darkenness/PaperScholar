"""Optional Celery adapter for the idempotent persisted task runner."""
import asyncio
from app.celery_app import celery_app

@celery_app.task
def generate_figure_task(task_id, user_id=None, config=None):
    from app.services.generation_service import run_generation_task
    from app.core.database import engine
    async def run():
        try:
            await run_generation_task(task_id)
        finally:
            await engine.dispose()
    asyncio.run(run())
    return {"task_id":task_id}

@celery_app.task(bind=True)
def health_check_task(self):
    return {"status":"healthy","task_id":self.request.id}

@celery_app.task
def cleanup_old_tasks():
    """Compatibility entry point for the existing scheduled Celery task."""
    from app.services.cleanup_service import cleanup_expired_references

    async def run_cleanup():
        return await cleanup_expired_references()

    return {"deleted": asyncio.run(run_cleanup())}
