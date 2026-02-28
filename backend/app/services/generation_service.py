"""Generation service: orchestrates pipeline execution with DB persistence and SSE events."""

import asyncio
import base64
import logging
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.pipeline import PipelineEngine
from app.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import decrypt_api_key, mask_api_key
from app.llm.load_balancer import ClientConfig, LoadBalancer
from app.models.api_key import ApiKeyConfig
from app.models.generation import GenerationResult, GenerationTask, PipelineEvent
from app.models.user import User
from app.services.usage_service import log_api_usage


async def _get_available_configs(db: AsyncSession, user_id: int, model_type: str) -> list[tuple[ApiKeyConfig, bool]]:
    """Get all available API key configs for a user (own + system), returns list of (config, is_system)."""
    results: list[tuple[ApiKeyConfig, bool]] = []

    # 1. User's own verified keys
    result = await db.execute(
        select(ApiKeyConfig)
        .where(
            ApiKeyConfig.user_id == user_id,
            ApiKeyConfig.model_type == model_type,
            ApiKeyConfig.is_verified == True,
            ApiKeyConfig.is_enabled == True,
            ApiKeyConfig.priority >= 0,
        )
        .order_by(ApiKeyConfig.priority.desc())
    )
    for cfg in result.scalars().all():
        results.append((cfg, False))

    # 2. System shared keys (for approved users)
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user and user.system_api_approved:
        result = await db.execute(
            select(ApiKeyConfig)
            .where(
                ApiKeyConfig.priority == -1,
                ApiKeyConfig.model_type == model_type,
                ApiKeyConfig.is_verified == True,
                ApiKeyConfig.is_enabled == True,
            )
        )
        for cfg in result.scalars().all():
            results.append((cfg, True))

    return results


async def get_available_models(db: AsyncSession, user_id: int) -> dict:
    """Return available chat and image models grouped by model_name, with provider details."""
    output = {"chat_models": [], "image_models": []}

    for model_type in ("chat", "image"):
        configs = await _get_available_configs(db, user_id, model_type)
        groups: dict[str, list[dict]] = defaultdict(list)

        for cfg, is_system in configs:
            model_name = cfg.model_name or f"{cfg.provider}_default"
            try:
                raw_key = decrypt_api_key(cfg.api_key_encrypted)
                preview = mask_api_key(raw_key)
            except Exception:
                preview = "***"

            groups[model_name].append({
                "key_id": cfg.id,
                "provider": cfg.provider,
                "base_url": cfg.base_url,
                "api_key_preview": preview,
                "is_system": is_system,
                "priority": cfg.priority,
            })

        key = f"{model_type}_models"
        for name, providers in groups.items():
            output[key].append({"model_name": name, "providers": providers})

    return output


async def _build_load_balancer(
    db: AsyncSession,
    user_id: int,
    model_type: str,
    key_id: Optional[int] = None,
    model_name: Optional[str] = None,
) -> Optional[LoadBalancer]:
    """Build a LoadBalancer from user's verified API key configs.
    
    Selection logic (VoAPI-style):
    - key_id specified: use only that specific key config
    - model_name specified: use all keys matching that model_name
    - neither specified: use all available keys (original behavior)
    
    Fallback priority:
    1. User's own verified keys (priority >= 0)
    2. System shared keys (priority == -1) if user has system_api_approved
    """
    all_configs = await _get_available_configs(db, user_id, model_type)

    if not all_configs:
        return None

    # Apply filters
    if key_id is not None:
        all_configs = [(cfg, sys) for cfg, sys in all_configs if cfg.id == key_id]
    elif model_name is not None:
        all_configs = [(cfg, sys) for cfg, sys in all_configs if cfg.model_name == model_name]
    else:
        # Default: prefer user keys; fall back to system keys only if no user keys
        user_configs = [(cfg, sys) for cfg, sys in all_configs if not sys]
        all_configs = user_configs if user_configs else all_configs

    if not all_configs:
        return None

    client_configs = []
    for cfg, _is_system in all_configs:
        try:
            raw_key = decrypt_api_key(cfg.api_key_encrypted)
            client_configs.append(
                ClientConfig(
                    provider=cfg.provider,
                    api_key=raw_key,
                    base_url=cfg.base_url,
                    model=cfg.model_name or "",
                    priority=max(cfg.priority, 0),
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


async def run_generation_task(task_id: uuid.UUID, extra_params: Optional[dict] = None):
    """Execute a generation task in the background.

    This function is meant to be called from a background worker (Celery)
    or via asyncio.create_task(). It manages its own DB session.
    """
    extra_params = extra_params or {}
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
            # Build load balancers from user's API keys (with optional model selection)
            chat_lb = await _build_load_balancer(
                db, task.user_id, "chat",
                key_id=task.chat_key_id,
                model_name=task.chat_model,
            )
            image_lb = await _build_load_balancer(
                db, task.user_id, "image",
                key_id=task.image_key_id,
                model_name=task.image_model,
            )

            if not chat_lb:
                raise RuntimeError("没有可用的 Chat 模型 API Key，请先在 API 配置中添加并验证")
            if not image_lb:
                # Fall back to chat LB for image if no dedicated image keys
                image_lb = chat_lb
                logger.warning(
                    "No dedicated image API keys configured. Using chat LB as image fallback. "
                    "For best results, configure a dedicated image model key (e.g., Gemini image model)."
                )
                # Warn if the fallback provider doesn't support image generation at all
                if chat_lb and chat_lb._states:
                    provider = chat_lb._states[0].config.provider
                    if provider == "anthropic":
                        logger.error(
                            "Anthropic does not support image generation. "
                            "Diagram generation WILL FAIL. Please add a Gemini or OpenAI image key."
                        )

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
                    # Ensure progress never regresses (monotonic increase guard)
                    if "progress" in event_data:
                        if event_data["progress"] < task.progress:
                            event_data["progress"] = task.progress
                        task.progress = event_data["progress"]
                    if "name" in event_data:
                        task.current_stage = event_data.get("name")
                    await _save_event(db, task_id, event_type, event_data)
                    await db.commit()

            # Prepare pipeline data
            data = {
                "content": task.content,
                "visual_intent": task.visual_intent,
                "aspect_ratio": task.aspect_ratio or "1:1",
                "task_type": task.task_type or "diagram",
                "retrieval_setting": task.retrieval_setting or "auto",
                "retriever_content_limit": extra_params.get("retriever_content_limit"),
                "retriever_top_k": extra_params.get("retriever_top_k", 10),
                "retriever_pool_size": extra_params.get("retriever_pool_size"),
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
