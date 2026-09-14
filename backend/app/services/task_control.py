"""Process-local jobs plus database-authoritative cooperative cancellation.

This is not a durable workflow engine. An upstream accepted request may finish
and bill even after local cancellation. Never auto-retry an entire paid run.
"""
import asyncio
from app.core.database import AsyncSessionLocal
from app.models.generation import GenerationTask
from sqlalchemy import select

_tasks = {}

def launch_task(task_id, coroutine):
    key=str(task_id)
    task=asyncio.create_task(coroutine,name=f'figure:{key}')
    _tasks[key]=task
    def finished(done):
        if _tasks.get(key) is done:
            _tasks.pop(key,None)
        if not done.cancelled():
            done.exception()
    task.add_done_callback(finished)
    return task

def cancel_local_task(task_id):
    task=_tasks.get(str(task_id))
    if task and not task.done():
        task.cancel()

async def assert_task_active(task_id):
    # Import at call time so both API and test runners share their session factory.
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        status=await db.scalar(select(GenerationTask.status).where(GenerationTask.id==task_id))
    if status not in {'pending','running'}:
        raise asyncio.CancelledError('Task is no longer active')

async def shutdown_tasks():
    pending=list(_tasks.values())
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending,return_exceptions=True)
