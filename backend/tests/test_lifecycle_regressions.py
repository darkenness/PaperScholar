import inspect
from pathlib import Path
import uuid

import pytest

from app.config import settings
from app.models.generation import GenerationResult, GenerationTask


@pytest.mark.asyncio
async def test_delete_task_removes_all_task_artifacts(database):
    """Deleting a task removes every candidate artifact under its task root."""
    from app.api.generate import delete_task
    from app.models.user import User

    task_id = uuid.uuid4()
    async with database() as db:
        task = GenerationTask(
            id=task_id,
            user_id=1,
            task_type="diagram",
            status="completed",
            content="content",
        )
        db.add(task)
        db.add_all(
            [
                GenerationResult(
                    task_id=task_id,
                    user_id=1,
                    candidate_index=0,
                    image_path=f"results/{task_id}/candidate_0/image.png",
                    svg_path=f"results/{task_id}/candidate_0/final.svg",
                    pdf_path=f"results/{task_id}/candidate_0/final.pdf",
                ),
                GenerationResult(
                    task_id=task_id,
                    user_id=1,
                    candidate_index=1,
                    image_path=f"results/{task_id}/candidate_1/image.png",
                    thumbnail_path=f"results/{task_id}/candidate_1/thumb.png",
                ),
            ]
        )
        await db.commit()

        task_root = Path(settings.UPLOAD_DIR) / "results" / str(task_id)
        for relative in (
            "candidate_0/image.png",
            "candidate_0/final.svg",
            "candidate_0/final.pdf",
            "candidate_1/image.png",
            "candidate_1/thumb.png",
            "orphan-checkpoint.json",
        ):
            path = task_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"artifact")

        outside = Path(settings.UPLOAD_DIR) / "results" / "other-task" / "keep.png"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_bytes(b"keep")

        response = await delete_task(task_id, User(id=1), db)

        assert response == {"message": "任务已删除"}
        assert not task_root.exists()
        assert outside.exists()


def test_entrypoint_runs_alembic_before_server():
    entrypoint = Path(__file__).parents[1] / "entrypoint.sh"
    text = entrypoint.read_text(encoding="utf-8")
    migrate_at = text.index('command.upgrade(config, "head")')
    server_at = text.index("uvicorn app.main:app")
    assert migrate_at < server_at


def test_backend_image_uses_migration_entrypoint():
    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text(encoding="utf-8")
    assert "ENTRYPOINT [\"./entrypoint.sh\"]" in dockerfile


def test_cleanup_old_tasks_delegates_to_cleanup_service(monkeypatch):
    """The legacy Celery entry point must still execute cleanup work."""
    from app.tasks.generation_tasks import cleanup_old_tasks

    called = False

    async def fake_cleanup():
        nonlocal called
        called = True
        return 7

    monkeypatch.setattr("app.services.cleanup_service.cleanup_expired_references", fake_cleanup)
    result = cleanup_old_tasks.run()

    assert called
    assert result == {"deleted": 7}
    assert len(inspect.signature(cleanup_old_tasks.run).parameters) == 0
