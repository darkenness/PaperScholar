"""Generation service: orchestrates pipeline execution with DB persistence and SSE events."""

import asyncio
import base64
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.pipeline import PipelineEngine
from app.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import decrypt_api_key
from app.llm.load_balancer import ClientConfig, LoadBalancer
from app.models.api_key import ApiKeyConfig
from app.models.generation import GenerationResult, GenerationTask, PipelineEvent
from app.models.user import User
from app.services.usage_service import log_api_usage


async def _build_load_balancer(db: AsyncSession, user_id: int, model_type: str) -> Optional[LoadBalancer]:
    """Build a LoadBalancer from user's verified API key configs."""
    result = await db.execute(
        select(ApiKeyConfig)
        .where(
            ApiKeyConfig.user_id == user_id,
            ApiKeyConfig.model_type == model_type,
            ApiKeyConfig.is_verified == True,
            ApiKeyConfig.is_enabled == True,
        )
        .order_by(ApiKeyConfig.priority.desc())
    )
    configs = result.scalars().all()

    if not configs:
        return None

    client_configs = []
    for cfg in configs:
        try:
            raw_key = decrypt_api_key(cfg.api_key_encrypted)
            client_configs.append(
                ClientConfig(
                    provider=cfg.provider,
                    api_key=raw_key,
                    base_url=cfg.base_url,
                    model=cfg.model_name or "",
                    priority=cfg.priority,
                    api_key_id=cfg.id,
                )
            )
        except Exception:
            continue

    if not client_configs:
        return None

    return LoadBalancer(client_configs)


async def _save_event(db: AsyncSession, task_id: uuid.UUID, event_type: str, event_data: dict):
    """Persist a pipeline event to the database."""
    event = PipelineEvent(task_id=task_id, event_type=event_type, event_data=event_data)
    db.add(event)
    await db.commit()


async def run_generation_task(task_id: uuid.UUID):
    """Execute a generation task in the background.

    This function is meant to be called from a background worker (Celery)
    or via asyncio.create_task(). It manages its own DB session.
    """
    async with AsyncSessionLocal() as db:
        # Load task
        result = await db.execute(select(GenerationTask).where(GenerationTask.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            return

        # Update status to running
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            # Build load balancers from user's API keys
            chat_lb = await _build_load_balancer(db, task.user_id, "chat")
            image_lb = await _build_load_balancer(db, task.user_id, "image")

            if not chat_lb:
                raise RuntimeError("没有可用的 Chat 模型 API Key，请先在 API 配置中添加并验证")
            if not image_lb:
                # Fall back to chat LB for image if no dedicated image keys
                image_lb = chat_lb

            # Record model info
            if chat_lb._states:
                cfg = chat_lb._states[0].config
                task.chat_provider = cfg.provider
                task.chat_model = cfg.model
            if image_lb._states:
                cfg = image_lb._states[0].config
                task.image_provider = cfg.provider
                task.image_model = cfg.model
            await db.commit()

            # Determine dataset path for Retriever
            dataset_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "PaperBananaBench")
            if not os.path.exists(dataset_path):
                dataset_path = None

            # Create pipeline engine
            engine = PipelineEngine(chat_lb=chat_lb, image_lb=image_lb, dataset_path=dataset_path)

            # SSE event callback with lock to prevent concurrent session writes
            _event_lock = asyncio.Lock()

            async def on_event(event_type: str, event_data: dict):
                async with _event_lock:
                    await _save_event(db, task_id, event_type, event_data)
                    if "progress" in event_data:
                        task.progress = event_data["progress"]
                    if "name" in event_data:
                        task.current_stage = event_data.get("name")
                    await db.commit()

            # Prepare pipeline data
            data = {
                "content": task.content,
                "visual_intent": task.visual_intent,
                "aspect_ratio": task.aspect_ratio or "1:1",
                "task_type": task.task_type or "diagram",
                "retrieval_setting": task.retrieval_setting or "auto",
            }

            # Run pipeline with num_candidates support
            result_data = await engine.run(
                data=data,
                mode=task.pipeline_mode or "dev_full",
                max_critic_rounds=task.max_critic_rounds or 3,
                num_candidates=task.num_candidates or 1,
                on_event=on_event,
            )

            # Save results (support multiple candidates)
            results_dir = os.path.join(settings.UPLOAD_DIR, "results", str(task_id))
            os.makedirs(results_dir, exist_ok=True)

            candidates = result_data.get("candidates", [])
            if not candidates:
                # Single candidate mode — wrap result_data as the only candidate
                candidates = [result_data]

            for idx, cdata in enumerate(candidates):
                image_path = None
                img_b64 = cdata.get("polished_image_base64") or cdata.get("image_base64")
                if img_b64:
                    try:
                        image_bytes = base64.b64decode(img_b64)
                        image_path = os.path.join("results", str(task_id), f"candidate_{idx}.png")
                        with open(os.path.join(settings.UPLOAD_DIR, image_path), "wb") as f:
                            f.write(image_bytes)
                    except Exception as img_err:
                        logger.warning(f"Failed to save candidate {idx} image: {img_err}")

                gen_result = GenerationResult(
                    task_id=task_id,
                    user_id=task.user_id,
                    candidate_index=idx,
                    image_path=image_path,
                    planner_desc=cdata.get("planner_description") or result_data.get("planner_description"),
                    stylist_desc=cdata.get("stylist_description") or result_data.get("stylist_description"),
                    critic_feedback={
                        f"round_{i}": cdata.get(f"critic_feedback_{i}")
                        for i in range(5)
                        if cdata.get(f"critic_feedback_{i}")
                    },
                )
                db.add(gen_result)

            # Mark complete
            task.status = "completed"
            task.progress = 1.0
            task.current_stage = None
            task.completed_at = datetime.now(timezone.utc)
            await db.commit()

            await _save_event(db, task_id, "done", {"status": "completed"})

            # Log API usage for the completed task
            elapsed_ms = int((datetime.now(timezone.utc) - task.started_at).total_seconds() * 1000) if task.started_at else None
            await log_api_usage(
                user_id=task.user_id,
                task_id=str(task_id),
                provider=task.chat_provider,
                model=task.chat_model,
                success=True,
                latency_ms=elapsed_ms,
            )

        except Exception as e:
            task.status = "failed"
            task.error_message = str(e)
            task.completed_at = datetime.now(timezone.utc)
            await db.commit()
            await _save_event(db, task_id, "error", {"message": str(e)})

            # Log failed API usage
            elapsed_ms = int((datetime.now(timezone.utc) - task.started_at).total_seconds() * 1000) if task.started_at else None
            await log_api_usage(
                user_id=task.user_id,
                task_id=str(task_id),
                provider=task.chat_provider,
                model=task.chat_model,
                success=False,
                error_message=str(e),
                latency_ms=elapsed_ms,
            )
