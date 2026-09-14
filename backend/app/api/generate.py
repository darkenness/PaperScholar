import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Header, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.core.database import get_db
from app.models.generation import GenerationResult, GenerationTask, PipelineEvent
from app.models.user import User
from app.schemas.generation import (
    AvailableModelsResponse,
    ContinueGenerationRequest,
    FavoriteRequest,
    GenerateRequest,
    ResultResponse,
    TaskCreateResponse,
    TaskStatusResponse,
)
from app.api.deps import get_current_user, get_stream_user

router = APIRouter(prefix="/generate", tags=["图表生成"])

# Track background tasks
from app.services.task_control import launch_task, cancel_local_task
from app.services.artifact_service import safe_artifact_path
from app.services.generation_service import _build_load_balancer, _load_references


@router.get("/available-models", response_model=AvailableModelsResponse)
async def get_available_models(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return available chat and image models for the current user, grouped by model name."""
    from app.services.generation_service import get_available_models
    data = await get_available_models(db, user.id)
    return AvailableModelsResponse(**data)


@router.post("", response_model=TaskCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_generation_task(
    req: GenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        chat=await _build_load_balancer(db,user.id,"chat",req.chat_key_id,req.chat_model_name)
        image=await _build_load_balancer(db,user.id,"image",req.image_key_id,req.image_model_name) if req.task_type=="diagram" else None
        if not chat or (req.task_type=="diagram" and not image):
            raise ValueError("请先配置并测试理解模型与所需生图模型")
        await _load_references(db,user.id,req.reference_image_ids)
        if req.retrieval_setting=="manual" and not req.reference_image_ids:
            raise ValueError("手动参考需要至少一张参考图")
        if req.pipeline_mode=="dev_polish":
            raise ValueError("请通过已生成图片的继续修改或图片精修入口进行操作")
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    task = GenerationTask(
        request_params=req.model_dump(mode="json"),
        user_id=user.id,
        task_type=req.task_type,
        content=req.content,
        visual_intent=req.visual_intent,
        pipeline_mode=req.pipeline_mode,
        retrieval_setting=req.retrieval_setting,
        num_candidates=req.num_candidates,
        aspect_ratio=req.aspect_ratio,
        max_critic_rounds=req.max_critic_rounds,
        optimize_input=req.optimize_input,
        vector_export=req.vector_export,
        cost_budget_usd=req.budget_usd,
        chat_model=req.chat_model_name,
        chat_key_id=req.chat_key_id,
        image_model=req.image_model_name,
        image_key_id=req.image_key_id,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Launch pipeline execution as background task
    from app.services.generation_service import run_generation_task
    extra_params = {
        "retriever_content_limit": req.retriever_content_limit,
        "retriever_top_k": req.retriever_top_k,
        "retriever_pool_size": req.retriever_pool_size,
        "image_size": req.image_size,
        "vector_export": req.vector_export,
    }
    launch_task(task.id,run_generation_task(task.id))

    return TaskCreateResponse(
        task_id=task.id,
        status=task.status,
        stream_url=f"/api/v1/generate/{task.id}/stream",
    )


@router.post("/{task_id}/continue", response_model=TaskCreateResponse, status_code=status.HTTP_201_CREATED)
async def continue_generation_task(
    task_id: uuid.UUID,
    req: ContinueGenerationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    parent_result = await db.execute(
        select(GenerationTask).where(
            GenerationTask.id == task_id,
            GenerationTask.user_id == user.id,
            GenerationTask.status.in_(["completed","failed","cancelled"]),
        )
    )
    parent = parent_result.scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=404, detail="找不到可续跑的历史任务")

    source_result_query = select(GenerationResult).where(
        GenerationResult.task_id == task_id,
        GenerationResult.user_id == user.id,
    )
    if req.result_id is not None:
        source_result_query = source_result_query.where(GenerationResult.id == req.result_id)
    else:
        source_result_query = source_result_query.where(GenerationResult.candidate_index == 0)
    source_result = (await db.execute(source_result_query)).scalar_one_or_none()
    if not source_result:
        raise HTTPException(status_code=404, detail="找不到可续跑的来源结果")

    if req.source_event_id is not None:
        event=await db.scalar(select(PipelineEvent).where(PipelineEvent.id==req.source_event_id,PipelineEvent.task_id==parent.id))
        details=event.event_data if event else {}
        if not details or not details.get("image_path") or details.get("candidate_index")!=source_result.candidate_index:
            raise HTTPException(400,"所选历史图片与候选结果不匹配")
    params={**(parent.request_params or {}),**req.model_dump(mode="json"),"continue_from_result_id":source_result.id,"reference_image_ids":[]}
    if req.image_size is None:
        params["image_size"]=(parent.request_params or {}).get("image_size")
    task = GenerationTask(
        request_params=params,
        user_id=user.id,
        task_type=parent.task_type,
        content=parent.content,
        visual_intent=parent.visual_intent,
        pipeline_mode="continue_feedback",
        retrieval_setting=parent.retrieval_setting,
        num_candidates=1,
        aspect_ratio=parent.aspect_ratio,
        max_critic_rounds=req.additional_critic_rounds,
        optimize_input=False,
        vector_export=req.vector_export,
        cost_budget_usd=req.budget_usd,
        chat_model=parent.chat_model,
        chat_key_id=parent.chat_key_id,
        image_model=parent.image_model,
        image_key_id=parent.image_key_id,
        parent_task_id=parent.id,
        user_feedback=req.feedback,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    from app.services.generation_service import run_generation_task
    extra_params = {
        "continue_from_result_id": source_result.id,
        "image_size": req.image_size,
        "vector_export": req.vector_export,
    }
    launch_task(task.id,run_generation_task(task.id))

    return TaskCreateResponse(
        task_id=task.id,
        status=task.status,
        stream_url=f"/api/v1/generate/{task.id}/stream",
    )


@router.get("/{task_id}/stream")
async def stream_task_events(
    task_id: uuid.UUID,
    after: int = Query(0, ge=0),
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    user: User = Depends(get_stream_user),
    db: AsyncSession = Depends(get_db),
):
    user_id=user.id
    try:
        cursor=max(after,int(last_event_id or 0))
    except ValueError:
        raise HTTPException(400,"Invalid event cursor")

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
        last_event_id = cursor
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
                            "id": str(event.id),
                            "event": event.event_type,
                            "data": _json.dumps(event.event_data, ensure_ascii=False),
                        }

                    task_result = await poll_db.execute(
                        select(GenerationTask.status,GenerationTask.error_message).where(GenerationTask.id == task_id)
                    )
                    row=task_result.first()
                    current_status=row[0] if row else None
                    error_message=row[1] if row else "任务不存在"
                    if current_status in ("completed", "failed", "cancelled") or current_status is None:
                        yield {
                            "event": "done",
                            "data": _json.dumps({"task_id":str(task_id),"status":current_status or "failed","message":error_message}),
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
                pdf_url=f"/uploads/{r.pdf_path}" if r.pdf_path else None,
                quality_score=r.quality_score,
                metadata=r.metadata_,
                is_favorited=r.is_favorited,
                created_at=r.created_at,
            )
            for r in results
        ],
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        cost_estimated_usd=task.cost_estimated_usd,
        cost_budget_usd=task.cost_budget_usd,
        cost_details=task.cost_details,
        request_params=task.request_params,
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
            "content": (task.content or "")[:200],
            "visual_intent": (task.visual_intent or "")[:200],
            "chat_model": task.chat_model,
            "image_model": task.image_model,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat(),
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "image_url": f"/uploads/{first_result.image_path}" if first_result and first_result.image_path else None,
            "thumbnail_url": f"/uploads/{first_result.thumbnail_path}" if first_result and first_result.thumbnail_path else None,
            "quality_score": first_result.quality_score if first_result else None,
            "is_favorited": first_result.is_favorited if first_result else False,
            "result_id": first_result.id if first_result else None,
            "cost_estimated_usd": task.cost_estimated_usd,
            "cost_budget_usd": task.cost_budget_usd,
        })

    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.delete("/{task_id}")
async def delete_task(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a generation task and its results."""
    from sqlalchemy.orm import selectinload
    import shutil

    result = await db.execute(
        select(GenerationTask)
        .options(selectinload(GenerationTask.results))
        .where(GenerationTask.id == task_id, GenerationTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status in {"pending","running"}:
        raise HTTPException(status_code=400, detail="运行中的任务不能删除，请先取消")

    # All generated artifacts live below this task-specific directory. Resolve
    # it through the same boundary check used for downloads before removing it.
    task_root = safe_artifact_path(f"results/{task_id}")
    if task_root.is_dir():
        shutil.rmtree(task_root)

    await db.delete(task)
    await db.commit()
    return {"message": "任务已删除"}


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

    changed=await db.scalar(update(GenerationTask).where(GenerationTask.id==task_id,GenerationTask.status.in_(["pending","running"])).values(status="cancelled",completed_at=datetime.now(timezone.utc)).returning(GenerationTask.id))
    if changed is None:
        raise HTTPException(409,"任务已结束，请刷新")
    db.add(PipelineEvent(task_id=task_id,event_type="done",event_data={"status":"cancelled"}))
    await db.commit()
    cancel_local_task(task_id)
    return {"message":"已停止后续执行；上游已提交的请求可能仍计费"}


@router.get("/{task_id}/download")
async def download_task_results(task_id: uuid.UUID, user: User = Depends(get_stream_user), db: AsyncSession = Depends(get_db)):
    import io,zipfile
    from fastapi.responses import StreamingResponse
    task=await db.scalar(select(GenerationTask).where(GenerationTask.id==task_id,GenerationTask.user_id==user.id))
    if task is None:
        raise HTTPException(404,"任务不存在")
    results=(await db.execute(select(GenerationResult).where(GenerationResult.task_id==task_id).order_by(GenerationResult.candidate_index))).scalars().all()
    if not results:
        raise HTTPException(404,"暂无可下载结果")
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as archive:
        for result in results:
            for relative in (result.image_path,result.svg_path,result.pdf_path):
                if relative:
                    path=safe_artifact_path(relative)
                    if path.is_file():
                        archive.write(path,f"candidate_{result.candidate_index}{path.suffix}")
    buf.seek(0)
    return StreamingResponse(buf,media_type="application/zip",headers={"Content-Disposition":f"attachment; filename=task_{str(task_id)[:8]}_results.zip"})


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
