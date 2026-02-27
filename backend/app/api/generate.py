import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.database import get_db
from app.models.generation import GenerationResult, GenerationTask, PipelineEvent
from app.models.user import User
from app.schemas.generation import (
    FavoriteRequest,
    GenerateRequest,
    ResultResponse,
    TaskCreateResponse,
    TaskStatusResponse,
)
from app.api.deps import get_current_user

router = APIRouter(prefix="/generate", tags=["图表生成"])

# Track background tasks
_background_tasks: dict[str, asyncio.Task] = {}


@router.post("", response_model=TaskCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_generation_task(
    req: GenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = GenerationTask(
        user_id=user.id,
        task_type=req.task_type,
        content=req.content,
        visual_intent=req.visual_intent,
        pipeline_mode=req.pipeline_mode,
        retrieval_setting=req.retrieval_setting,
        num_candidates=req.num_candidates,
        aspect_ratio=req.aspect_ratio,
        max_critic_rounds=req.max_critic_rounds,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Launch pipeline execution as background task
    from app.services.generation_service import run_generation_task
    bg_task = asyncio.create_task(run_generation_task(task.id))
    _background_tasks[str(task.id)] = bg_task

    # Cleanup finished tasks
    for tid in list(_background_tasks.keys()):
        if _background_tasks[tid].done():
            del _background_tasks[tid]

    return TaskCreateResponse(
        task_id=task.id,
        status=task.status,
        stream_url=f"/api/v1/generate/{task.id}/stream",
    )


@router.get("/{task_id}/stream")
async def stream_task_events(
    task_id: uuid.UUID,
    token: str = Query(..., description="JWT token for SSE auth (EventSource can't send headers)"),
    db: AsyncSession = Depends(get_db),
):
    # Authenticate via query param since browser EventSource doesn't support custom headers
    from app.core.security import decode_access_token
    from sqlalchemy import select as sa_select

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="无效的Token")
    user_id = int(payload.get("sub", 0))

    result = await db.execute(
        select(GenerationTask).where(
            GenerationTask.id == task_id, GenerationTask.user_id == user_id
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    import json as _json
    from app.core.database import AsyncSessionLocal

    async def event_generator():
        """Use independent DB sessions per poll cycle to avoid stale/closed session issues."""
        last_event_id = 0
        while True:
            try:
                async with AsyncSessionLocal() as poll_db:
                    events_result = await poll_db.execute(
                        select(PipelineEvent)
                        .where(PipelineEvent.task_id == task_id, PipelineEvent.id > last_event_id)
                        .order_by(PipelineEvent.id)
                    )
                    new_events = events_result.scalars().all()

                    for event in new_events:
                        last_event_id = event.id
                        yield {
                            "event": event.event_type,
                            "data": _json.dumps(event.event_data, ensure_ascii=False),
                        }

                    task_result = await poll_db.execute(
                        select(GenerationTask.status).where(GenerationTask.id == task_id)
                    )
                    current_status = task_result.scalar_one_or_none()
                    if current_status in ("completed", "failed", "cancelled"):
                        yield {
                            "event": "done",
                            "data": _json.dumps({"task_id": str(task_id), "status": current_status}),
                        }
                        break
            except Exception as e:
                yield {"event": "error", "data": _json.dumps({"message": str(e)})}
                break

            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GenerationTask).where(
            GenerationTask.id == task_id, GenerationTask.user_id == user.id
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    results_result = await db.execute(
        select(GenerationResult)
        .where(GenerationResult.task_id == task_id)
        .order_by(GenerationResult.candidate_index)
    )
    results = results_result.scalars().all()

    return TaskStatusResponse(
        task_id=task.id,
        status=task.status,
        progress=task.progress,
        current_stage=task.current_stage,
        error_message=task.error_message,
        results=[
            ResultResponse(
                id=r.id,
                candidate_index=r.candidate_index,
                image_url=f"/uploads/{r.image_path}" if r.image_path else None,
                thumbnail_url=f"/uploads/{r.thumbnail_path}" if r.thumbnail_path else None,
                svg_url=f"/uploads/{r.svg_path}" if r.svg_path else None,
                quality_score=r.quality_score,
                is_favorited=r.is_favorited,
                created_at=r.created_at,
            )
            for r in results
        ],
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


@router.get("/history/list")
async def get_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    task_type: str = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(GenerationTask).where(GenerationTask.user_id == user.id)
    count_query = select(func.count(GenerationTask.id)).where(GenerationTask.user_id == user.id)

    if task_type:
        query = query.where(GenerationTask.task_type == task_type)
        count_query = count_query.where(GenerationTask.task_type == task_type)

    total = (await db.execute(count_query)).scalar()

    result = await db.execute(
        query.order_by(GenerationTask.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    tasks = result.scalars().all()

    items = []
    for task in tasks:
        r_result = await db.execute(
            select(GenerationResult)
            .where(GenerationResult.task_id == task.id, GenerationResult.candidate_index == 0)
        )
        first_result = r_result.scalar_one_or_none()

        items.append({
            "task_id": str(task.id),
            "task_type": task.task_type,
            "pipeline_mode": task.pipeline_mode,
            "status": task.status,
            "progress": task.progress,
            "created_at": task.created_at.isoformat(),
            "image_url": f"/uploads/{first_result.image_path}" if first_result and first_result.image_path else None,
            "thumbnail_url": f"/uploads/{first_result.thumbnail_path}" if first_result and first_result.thumbnail_path else None,
            "quality_score": first_result.quality_score if first_result else None,
            "is_favorited": first_result.is_favorited if first_result else False,
        })

    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GenerationTask).where(
            GenerationTask.id == task_id, GenerationTask.user_id == user.id
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status not in ("pending", "running"):
        raise HTTPException(status_code=400, detail="只能取消待执行或运行中的任务")

    task.status = "cancelled"
    task.completed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "任务已取消"}


@router.get("/{task_id}/download")
async def download_task_results(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download all result images for a task as a ZIP file."""
    import io
    import zipfile
    from fastapi.responses import StreamingResponse
    from app.config import settings

    result = await db.execute(
        select(GenerationTask).where(
            GenerationTask.id == task_id, GenerationTask.user_id == user.id
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="任务未完成，无法下载")

    results_result = await db.execute(
        select(GenerationResult)
        .where(GenerationResult.task_id == task_id)
        .order_by(GenerationResult.candidate_index)
    )
    results = results_result.scalars().all()

    if not results:
        raise HTTPException(status_code=404, detail="无可下载的结果")

    import os
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in results:
            if r.image_path:
                abs_path = os.path.join(settings.UPLOAD_DIR, r.image_path)
                if os.path.exists(abs_path):
                    zf.write(abs_path, f"candidate_{r.candidate_index}.png")
            if r.svg_path:
                abs_path = os.path.join(settings.UPLOAD_DIR, r.svg_path)
                if os.path.exists(abs_path):
                    zf.write(abs_path, f"candidate_{r.candidate_index}.svg")

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=task_{str(task_id)[:8]}_results.zip"},
    )


@router.post("/results/{result_id}/favorite")
async def toggle_favorite(
    result_id: int,
    req: FavoriteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GenerationResult).where(
            GenerationResult.id == result_id, GenerationResult.user_id == user.id
        )
    )
    gen_result = result.scalar_one_or_none()
    if not gen_result:
        raise HTTPException(status_code=404, detail="结果不存在")

    gen_result.is_favorited = req.is_favorited
    await db.commit()
    return {"message": "已更新收藏状态"}
