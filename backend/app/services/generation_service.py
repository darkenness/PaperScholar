"""Generation service: orchestrates pipeline execution with DB persistence and SSE events."""

import asyncio
import base64
import logging
import os
import tempfile
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
from app.llm.provider_capabilities import image_model_capabilities, validate_provider_for_model_type
from app.models.api_key import ApiKeyConfig
from app.models.generation import GenerationResult, GenerationTask, PipelineEvent
from app.models.user import User
from app.services.cost_service import BudgetExceededError, CostTracker
from app.services.usage_service import log_api_usage


async def _get_available_configs(db: AsyncSession, user_id: int, model_type: str) -> list[tuple[ApiKeyConfig, bool]]:
    """Get all available API key configs for a user (own + system), returns list of (config, is_system)."""
    results: list[tuple[ApiKeyConfig, bool]] = []

    result = await db.execute(
        select(ApiKeyConfig)
        .where(
            ApiKeyConfig.user_id == user_id,
            ApiKeyConfig.model_type == model_type,
            ApiKeyConfig.is_verified == True,
            ApiKeyConfig.is_enabled == True,
            ApiKeyConfig.priority >= 0,
        )
        .order_by(ApiKeyConfig.priority.desc(), ApiKeyConfig.id)
    )
    for cfg in result.scalars().all():
        results.append((cfg, False))

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
            .order_by(ApiKeyConfig.id)
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

            capabilities = image_model_capabilities(cfg.provider, model_name) if model_type == "image" else {}
            groups[model_name].append({
                "key_id": cfg.id,
                "provider": cfg.provider,
                "base_url": cfg.base_url,
                "api_key_preview": preview,
                "is_system": is_system,
                "priority": cfg.priority,
                **capabilities,
            })

        key = f"{model_type}_models"
        for name, providers in groups.items():
            capabilities = {}
            if model_type == "image" and providers:
                capabilities = next(
                    ({"size_mode": p["size_mode"], "size_options": p["size_options"]} for p in providers if p["size_mode"] == "fixed"),
                    {"size_mode": providers[0]["size_mode"], "size_options": providers[0]["size_options"]},
                )
            output[key].append({"model_name": name, "providers": providers, **capabilities})

    return output


async def _build_load_balancer(
    db: AsyncSession,
    user_id: int,
    model_type: str,
    key_id: Optional[int] = None,
    model_name: Optional[str] = None,
    wait_callback=None,
    cost_tracker: Optional[CostTracker] = None,
    usage_callback=None,
) -> Optional[LoadBalancer]:
    """Build a LoadBalancer from user's verified API key configs."""
    all_configs = await _get_available_configs(db, user_id, model_type)

    if not all_configs:
        return None

    if key_id is not None:
        all_configs = [(cfg, sys) for cfg, sys in all_configs if cfg.id == key_id]
    elif model_name is not None:
        all_configs = [(cfg, sys) for cfg, sys in all_configs if cfg.model_name == model_name]
    else:
        user_configs = [(cfg, sys) for cfg, sys in all_configs if not sys]
        all_configs = user_configs if user_configs else all_configs

    if not all_configs:
        return None

    client_configs = []
    for cfg, _is_system in all_configs:
        try:
            validate_provider_for_model_type(model_type, cfg.provider)
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
        except Exception as e:
            logger.warning("Skipping invalid %s API key config %s: %s", model_type, cfg.id, e)
            continue

    if not client_configs:
        return None

    start_index = (user_id * 7) if model_type == "image" else user_id
    return LoadBalancer(
        client_configs,
        usage_callback=usage_callback,
        wait_callback=wait_callback,
        cost_tracker=cost_tracker,
        start_index=start_index,
    )


async def _save_event(db: AsyncSession, task_id: uuid.UUID, event_type: str, event_data: dict):
    """Persist a pipeline event to the database."""
    event = PipelineEvent(task_id=task_id, event_type=event_type, event_data=event_data)
    db.add(event)
    await db.commit()


def _read_result_image_base64(result: GenerationResult) -> Optional[str]:
    if not result.image_path:
        return None
    abs_path = os.path.join(settings.UPLOAD_DIR, result.image_path)
    if not os.path.exists(abs_path):
        return None
    with open(abs_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _write_svg_to_pdf(svg_text: str, pdf_abs_path: str) -> tuple[bool, Optional[str]]:
    try:
        import cairosvg
        cairosvg.svg2pdf(bytestring=svg_text.encode("utf-8"), write_to=pdf_abs_path)
        return True, None
    except Exception as e:
        logger.warning("Failed to convert SVG to PDF: %s", e)
        return False, str(e)


async def _maybe_generate_diagram_vector(
    chat_lb: LoadBalancer,
    description: str,
    content: str,
    task_type: str,
    vector_export: str,
    on_event,
) -> tuple[Optional[str], Optional[str], dict]:
    """Generate an experimental true SVG for diagrams using the existing SVG service."""
    vector_export = (vector_export or "none").lower()
    if task_type != "diagram" or vector_export == "none" or not description:
        return None, None, {"status": "skipped"}

    try:
        from app.services.svg_service import generate_svg_figure

        await on_event("stage", {
            "name": "vector_export",
            "status": "running",
            "progress": 0.96,
            "detail": "生成实验性 SVG",
        })
        result = await generate_svg_figure(
            description=description,
            content=content,
            chat_lb=chat_lb,
            max_iterations=1,
            on_event=on_event,
        )
        svg_code = result.get("svg_code")
        if not svg_code:
            return None, None, {"status": "failed", "error": "SVG service returned no SVG"}
        pdf_b64 = None
        pdf_error = None
        if vector_export in ("pdf", "both"):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                ok, pdf_error = _write_svg_to_pdf(svg_code, tmp_path)
                if ok:
                    with open(tmp_path, "rb") as f:
                        pdf_b64 = base64.b64encode(f.read()).decode()
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        status = "generated"
        if vector_export == "pdf" and not pdf_b64:
            status = "failed"
        elif vector_export == "both" and not pdf_b64:
            status = "partial"
        meta = {
            "status": status,
            "kind": "direct_svg_experimental",
        }
        if pdf_error:
            meta["pdf_error"] = pdf_error
        return svg_code if vector_export in ("svg", "both") else None, pdf_b64, {
            **meta,
        }
    except Exception as e:
        logger.warning("Diagram vector export failed: %s", e)
        return None, None, {"status": "failed", "error": str(e), "kind": "direct_svg_experimental"}


async def run_generation_task(task_id: uuid.UUID, extra_params: Optional[dict] = None):
    """Execute a generation task in the background."""
    extra_params = extra_params or {}
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(GenerationTask).where(GenerationTask.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            return

        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            cost_tracker = CostTracker(budget_usd=task.cost_budget_usd)

            chat_lb = await _build_load_balancer(
                db, task.user_id, "chat",
                key_id=task.chat_key_id,
                model_name=task.chat_model,
                cost_tracker=cost_tracker,
            )
            image_lb = await _build_load_balancer(
                db, task.user_id, "image",
                key_id=task.image_key_id,
                model_name=task.image_model,
                cost_tracker=cost_tracker,
            )

            if not chat_lb:
                raise RuntimeError("没有可用的 Chat 模型 API Key，请先在 API 配置中添加并验证")
            if (task.task_type or "diagram") == "diagram" and not image_lb:
                raise RuntimeError(
                    "没有可用的 Image 模型 API Key。请添加并验证 openai_images、openai_compat 或 gemini image key。"
                )
            if not image_lb:
                # Plot tasks can render through generated matplotlib code and do not need an image model.
                image_lb = chat_lb

            if chat_lb._states:
                cfg = chat_lb._states[0].config
                task.chat_provider = cfg.provider
                task.chat_model = cfg.model
            if image_lb._states:
                cfg = image_lb._states[0].config
                task.image_provider = cfg.provider
                task.image_model = cfg.model
            await db.commit()

            dataset_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "PaperBananaBench")
            if not os.path.exists(dataset_path):
                dataset_path = None

            engine = PipelineEngine(chat_lb=chat_lb, image_lb=image_lb, dataset_path=dataset_path)
            _event_lock = asyncio.Lock()

            async def on_event(event_type: str, event_data: dict):
                async with _event_lock:
                    if "progress" in event_data:
                        if event_data["progress"] < task.progress:
                            event_data["progress"] = task.progress
                        task.progress = event_data["progress"]
                    if "name" in event_data:
                        task.current_stage = event_data.get("name")
                    await _save_event(db, task_id, event_type, event_data)
                    await db.commit()

            async def on_wait(event_data: dict):
                event_data.setdefault("progress", task.progress)
                await on_event("stage", event_data)

            async def on_cost_update(summary: dict):
                task.cost_estimated_usd = summary.get("total_usd")
                task.cost_details = summary
                await on_event("cost", summary)

            cost_tracker.on_update = on_cost_update

            if chat_lb:
                chat_lb.set_wait_callback(on_wait)
            if image_lb:
                image_lb.set_wait_callback(on_wait)

            data = {
                "content": task.content,
                "visual_intent": task.visual_intent,
                "aspect_ratio": task.aspect_ratio or "1:1",
                "image_size": extra_params.get("image_size"),
                "task_type": task.task_type or "diagram",
                "retrieval_setting": task.retrieval_setting or "auto",
                "retriever_content_limit": extra_params.get("retriever_content_limit"),
                "retriever_top_k": extra_params.get("retriever_top_k", 10),
                "retriever_pool_size": extra_params.get("retriever_pool_size"),
                "optimize_input": task.optimize_input,
                "vector_export": task.vector_export or extra_params.get("vector_export") or "none",
                "user_feedback": task.user_feedback,
            }

            if (task.pipeline_mode or "") == "continue_feedback":
                source_result_id = extra_params.get("continue_from_result_id")
                source_query = select(GenerationResult).where(GenerationResult.user_id == task.user_id)
                if source_result_id:
                    source_query = source_query.where(GenerationResult.id == source_result_id)
                elif task.parent_task_id:
                    source_query = source_query.where(
                        GenerationResult.task_id == task.parent_task_id,
                        GenerationResult.candidate_index == 0,
                    )
                else:
                    raise RuntimeError("续跑任务缺少来源结果")

                source_result = (await db.execute(source_query.order_by(GenerationResult.candidate_index))).scalars().first()
                if not source_result:
                    raise RuntimeError("找不到可续跑的来源结果")

                source_image_b64 = _read_result_image_base64(source_result)
                if not source_image_b64:
                    raise RuntimeError("来源结果图片不存在，无法续跑")

                data.update({
                    "image_base64": source_image_b64,
                    "planner_description": source_result.planner_desc,
                    "stylist_description": source_result.stylist_desc or source_result.planner_desc,
                    "source_result_id": source_result.id,
                })

            result_data = await engine.run(
                data=data,
                mode=task.pipeline_mode or "dev_full",
                max_critic_rounds=task.max_critic_rounds or 3,
                num_candidates=task.num_candidates or 1,
                on_event=on_event,
            )

            results_dir = os.path.join(settings.UPLOAD_DIR, "results", str(task_id))
            os.makedirs(results_dir, exist_ok=True)

            candidates = result_data.get("candidates", [])
            if not candidates:
                candidates = [result_data]

            for idx, cdata in enumerate(candidates):
                image_path = None
                svg_path = None
                pdf_path = None
                result_metadata = dict(cdata.get("metadata") or {})
                result_metadata["input_optimizer"] = cdata.get("input_optimizer") or result_data.get("input_optimizer")
                result_metadata["vector_export"] = {
                    "requested": task.vector_export or "none",
                    "status": "skipped",
                }
                img_b64 = cdata.get("polished_image_base64") or cdata.get("image_base64")
                if img_b64:
                    try:
                        image_bytes = base64.b64decode(img_b64)
                        image_path = os.path.join("results", str(task_id), f"candidate_{idx}.png")
                        with open(os.path.join(settings.UPLOAD_DIR, image_path), "wb") as f:
                            f.write(image_bytes)
                    except Exception as img_err:
                        logger.warning(f"Failed to save candidate {idx} image: {img_err}")

                vector_export = (task.vector_export or "none").lower()
                if vector_export != "none":
                    vector_svg = cdata.get("vector_svg")
                    vector_pdf_b64 = cdata.get("vector_pdf_base64")
                    vector_meta = {"requested": vector_export, "status": "skipped"}

                    if task.task_type == "diagram" and not vector_svg and not vector_pdf_b64:
                        desc_for_vector = (
                            cdata.get("stylist_description")
                            or cdata.get("planner_description")
                            or result_data.get("stylist_description")
                            or result_data.get("planner_description")
                            or ""
                        )
                        vector_svg, vector_pdf_b64, vector_meta = await _maybe_generate_diagram_vector(
                            chat_lb=chat_lb,
                            description=desc_for_vector,
                            content=task.content or "",
                            task_type=task.task_type or "diagram",
                            vector_export=vector_export,
                            on_event=on_event,
                        )
                    elif task.task_type == "plot":
                        vector_meta = {"requested": vector_export, "status": "generated", "kind": "matplotlib"}

                    if vector_svg:
                        svg_path = os.path.join("results", str(task_id), f"candidate_{idx}.svg")
                        with open(os.path.join(settings.UPLOAD_DIR, svg_path), "w", encoding="utf-8") as f:
                            f.write(vector_svg)
                        vector_meta["svg_path"] = svg_path
                    if vector_pdf_b64:
                        pdf_path = os.path.join("results", str(task_id), f"candidate_{idx}.pdf")
                        with open(os.path.join(settings.UPLOAD_DIR, pdf_path), "wb") as f:
                            f.write(base64.b64decode(vector_pdf_b64))
                        vector_meta["pdf_path"] = pdf_path
                    if not svg_path and not pdf_path and vector_meta.get("status") == "generated":
                        vector_meta["status"] = "failed"
                    result_metadata["vector_export"] = vector_meta

                gen_result = GenerationResult(
                    task_id=task_id,
                    user_id=task.user_id,
                    candidate_index=idx,
                    image_path=image_path,
                    svg_path=svg_path,
                    pdf_path=pdf_path,
                    planner_desc=cdata.get("planner_description") or result_data.get("planner_description"),
                    stylist_desc=cdata.get("stylist_description") or result_data.get("stylist_description"),
                    critic_feedback={
                        f"round_{i}": cdata.get(f"critic_feedback_{i}")
                        for i in range(5)
                        if cdata.get(f"critic_feedback_{i}")
                    },
                    metadata_=result_metadata,
                )
                db.add(gen_result)

            task.status = "completed"
            task.progress = 1.0
            task.current_stage = None
            task.completed_at = datetime.now(timezone.utc)
            task.cost_details = cost_tracker.summary()
            task.cost_estimated_usd = task.cost_details.get("total_usd")
            await db.commit()

            await _save_event(db, task_id, "done", {"status": "completed", "cost": task.cost_details})

            elapsed_ms = int((datetime.now(timezone.utc) - task.started_at).total_seconds() * 1000) if task.started_at else None
            await log_api_usage(
                user_id=task.user_id,
                task_id=str(task_id),
                provider=task.chat_provider,
                model=task.chat_model,
                success=True,
                latency_ms=elapsed_ms,
            )

        except asyncio.CancelledError:
            task.status = "cancelled"
            task.completed_at = datetime.now(timezone.utc)
            if "cost_tracker" in locals():
                task.cost_details = cost_tracker.summary()
                task.cost_estimated_usd = task.cost_details.get("total_usd")
            await db.commit()
            await _save_event(db, task_id, "done", {"status": "cancelled"})
            raise
        except BudgetExceededError as e:
            task.status = "failed"
            task.error_message = str(e)
            task.completed_at = datetime.now(timezone.utc)
            if "cost_tracker" in locals():
                task.cost_details = cost_tracker.summary()
                task.cost_estimated_usd = task.cost_details.get("total_usd")
            await db.commit()
            await _save_event(db, task_id, "error", {"message": str(e), "cost": task.cost_details})
        except Exception as e:
            task.status = "failed"
            task.error_message = str(e)
            task.completed_at = datetime.now(timezone.utc)
            if "cost_tracker" in locals():
                task.cost_details = cost_tracker.summary()
                task.cost_estimated_usd = task.cost_details.get("total_usd")
            await db.commit()
            await _save_event(db, task_id, "error", {"message": str(e)})

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
