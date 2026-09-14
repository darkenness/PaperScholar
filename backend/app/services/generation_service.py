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

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.pipeline import PipelineEngine
from app.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import decrypt_api_key, mask_api_key
from app.llm.load_balancer import ClientConfig, LoadBalancer
from app.llm.provider_capabilities import image_model_capabilities, validate_provider_for_model_type
from app.models.api_key import ApiKeyConfig
from app.models.generation import GenerationResult, GenerationTask, PipelineEvent, UploadedReference
from app.models.user import User
from app.services.cost_service import BudgetExceededError, CostTracker
from app.services.usage_service import log_api_usage
from app.services.artifact_service import write_image,read_image,safe_artifact_path
from app.services.task_control import assert_task_active
from app.llm.endpoint_config import effective_model
from functools import partial


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
            model_name = effective_model(cfg.provider,cfg.model_type,cfg.model_name)
            if not model_name:
                continue
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
                "display_name": cfg.display_name,
                "capability_status": cfg.capability_status or {},
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
    before_call=None,
) -> Optional[LoadBalancer]:
    """Build a LoadBalancer from user's verified API key configs."""
    all_configs = await _get_available_configs(db, user_id, model_type)

    if not all_configs:
        return None

    if key_id is not None:
        all_configs = [(cfg, sys) for cfg, sys in all_configs if cfg.id == key_id]
    elif model_name is not None:
        all_configs = [(cfg, sys) for cfg, sys in all_configs if effective_model(cfg.provider,cfg.model_type,cfg.model_name) == model_name]
    else:
        user_configs = [(cfg, sys) for cfg, sys in all_configs if not sys]
        all_configs = user_configs if user_configs else all_configs
        chosen = effective_model(all_configs[0][0].provider,model_type,all_configs[0][0].model_name)
        all_configs = [(cfg,sys) for cfg,sys in all_configs if effective_model(cfg.provider,model_type,cfg.model_name)==chosen]

    if not all_configs:
        return None

    if key_id is not None and model_name and any(effective_model(cfg.provider,model_type,cfg.model_name) != model_name for cfg,_ in all_configs):
        raise ValueError("选择的模型与供应商不匹配，请刷新模型列表")

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
                    model=effective_model(cfg.provider,model_type,cfg.model_name),
                    api_options=cfg.api_options or {},
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
        before_call=before_call,
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
    except BudgetExceededError:
        raise
    except Exception as e:
        logger.warning("Diagram vector export failed: %s", e)
        return None, None, {"status": "failed", "error": str(e), "kind": "direct_svg_experimental"}


async def _load_references(db, user_id, ids):
    if not ids:
        return []
    ids=list(dict.fromkeys(ids))
    refs=(await db.execute(select(UploadedReference).where(UploadedReference.id.in_(ids), UploadedReference.user_id==user_id, UploadedReference.is_deleted==False))).scalars().all()
    if len(refs)!=len(ids):
        raise ValueError('部分参考图不存在或无权访问')
    out=[]
    for ref in refs:
        if ref.expires_at and ref.expires_at.replace(tzinfo=timezone.utc)<=datetime.now(timezone.utc):
            raise ValueError('参考图已过期，请重新上传')
        out.append({'id':f'uploaded_{ref.id}','content':'User-provided visual reference. Borrow composition/style only, never its scientific claims.','visual_intent':ref.file_name or 'Visual reference','image_base64':read_image(ref.file_path)})
    return out


async def run_generation_task(task_id, extra_params=None):
    """Claim once, persist previews, finalize conditionally without losing cancellation."""
    task_id=uuid.UUID(str(task_id))
    task=None; cost_tracker=None
    checkpoints={}; completed=[]
    outcome,error='completed',None
    try:
        async with AsyncSessionLocal() as db:
            claimed=await db.scalar(update(GenerationTask).where(GenerationTask.id==task_id,GenerationTask.status=='pending').values(status='running',started_at=datetime.now(timezone.utc)).returning(GenerationTask.id))
            await db.commit()
            if claimed is None:
                return
            task=await db.get(GenerationTask,task_id)
            params={**(task.request_params or {}),**(extra_params or {})}
            cost_tracker=CostTracker(budget_usd=task.cost_budget_usd)
            chat_lb=await _build_load_balancer(db,task.user_id,'chat',key_id=task.chat_key_id,model_name=task.chat_model,cost_tracker=cost_tracker,before_call=partial(assert_task_active,task_id))
            image_lb=await _build_load_balancer(db,task.user_id,'image',key_id=task.image_key_id,model_name=task.image_model,cost_tracker=cost_tracker,before_call=partial(assert_task_active,task_id))
            if not chat_lb:
                raise RuntimeError('没有可用的理解模型，请在供应商设置中配置并测试')
            if task.task_type=='diagram' and not image_lb:
                raise RuntimeError('没有可用的生图模型，请配置并测试所需接口')
            image_lb=image_lb or chat_lb
            refs=await _load_references(db,task.user_id,params.get('reference_image_ids'))
            data={**params,'content':task.content,'original_content':task.content,'visual_intent':task.visual_intent,
                  'aspect_ratio':task.aspect_ratio or '1:1','task_type':task.task_type or 'diagram',
                  'retrieval_setting':task.retrieval_setting or 'auto','optimize_input':task.optimize_input,
                  'vector_export':task.vector_export or 'none','user_feedback':task.user_feedback,'retrieved_examples':refs}
            if task.pipeline_mode=='continue_feedback':
                src=await db.scalar(select(GenerationResult).where(GenerationResult.id==params.get('continue_from_result_id'),GenerationResult.task_id==task.parent_task_id,GenerationResult.user_id==task.user_id))
                if src is None or not src.image_path:
                    raise RuntimeError('来源图片不存在，无法继续修改')
                src_path=src.image_path; desc=src.stylist_desc or src.planner_desc or task.content
                if params.get('source_event_id'):
                    event=await db.scalar(select(PipelineEvent).where(PipelineEvent.id==params['source_event_id'],PipelineEvent.task_id==task.parent_task_id))
                    details=event.event_data if event else {}
                    if not details or not details.get('image_path') or details.get('candidate_index')!=src.candidate_index:
                        raise RuntimeError('所选历史图片与候选结果不匹配')
                    src_path=details['image_path'];desc=details.get('description') or desc
                data.update(image_base64=read_image(src_path),planner_description=src.planner_desc or task.content,stylist_description=desc)
            await db.commit()
        # The read session is closed before any model I/O; concurrent callbacks
        # create their own sessions instead of sharing an AsyncSession.
        event_lock=asyncio.Lock()
        progress=0.0; branches={}; texts={}
        async def on_event(kind,event_data):
            nonlocal progress
            await assert_task_active(task_id)
            async with event_lock:
                payload=dict(event_data)
                ci=int(payload.get('candidate_index',-1));payload.setdefault('candidate_index',ci)
                if kind=='intermediate' and payload.get('type')=='text':
                    texts[(ci,payload.get('stage'))]=payload.get('content','')
                if kind=='intermediate' and payload.get('image_base64'):
                    raw=base64.b64decode(payload.pop('image_base64'))
                    path=await asyncio.to_thread(write_image,task_id,max(ci,0),raw,stem=f"{payload.get('stage','render')}_{payload.get('round',0)}")
                    payload.update(type='image',image_path=path,image_url=f'/uploads/{path}')
                    checkpoints.setdefault(max(ci,0),{'candidate_index':max(ci,0),'image_path':path,
                        'planner_description':texts.get((ci,'planner')) or texts.get((-1,'planner')),
                        'stylist_description':payload.get('description') or texts.get((ci,'stylist')) or texts.get((-1,'stylist')),
                        'metadata':{'checkpoint':True}})
                if 'progress' in payload:
                    current=min(.99,max(0.,float(payload['progress'])))
                    if ci>=0 and (task.num_candidates or 1)>1:
                        branches[ci]=max(branches.get(ci,0),current)
                        current=sum(branches.values())/task.num_candidates
                    progress=max(progress,current);payload['progress']=progress
                async with AsyncSessionLocal() as event_db:
                    await event_db.execute(update(GenerationTask).where(GenerationTask.id==task_id,GenerationTask.status=='running').values(progress=progress,current_stage=payload.get('name',payload.get('stage'))))
                    event_db.add(PipelineEvent(task_id=task_id,event_type=kind,event_data=payload))
                    await event_db.commit()
        async def on_wait(payload):
            await on_event('stage',{**payload,'name':'queue','status':'waiting','detail':payload.get('status')})
        async def on_cost(summary):
            await on_event('cost',summary)
        async def on_usage(**details):
            await on_event('usage',{k:v for k,v in details.items() if k!='error_message'})
        cost_tracker.on_update=on_cost
        for lb in {chat_lb,image_lb}:
            lb.set_wait_callback(on_wait)
            lb._usage_callback=on_usage
        dataset=getattr(settings,'REFERENCE_DATASET_DIR','') or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),'data','PaperBananaBench')
        engine=PipelineEngine(chat_lb,image_lb,dataset_path=dataset)
        result=await engine.run(data=data,mode=task.pipeline_mode or 'demo_full',
            max_critic_rounds=task.max_critic_rounds if task.max_critic_rounds is not None else 3,
            num_candidates=task.num_candidates or 1,on_event=on_event)
        await assert_task_active(task_id)
        for index,item in enumerate(result.get('candidates') or [result]):
            ci=max(0,item.get('candidate_index',index))
            b64=item.get('polished_image_base64') or item.get('image_base64')
            if not b64:
                continue
            path=await asyncio.to_thread(write_image,task_id,ci,base64.b64decode(b64),stem='final')
            desc=item.get('stylist_description') or item.get('planner_description') or ''
            # Save a usable final raster before optional export can fail/stop.
            record={'candidate_index':ci,'image_path':path,'planner_description':item.get('planner_description'),
                'stylist_description':desc,'critic_feedback':{f'round_{i}':item[f'critic_feedback_{i}'] for i in range(5) if item.get(f'critic_feedback_{i}')},
                'metadata':{**(item.get('metadata') or {}),'candidate_strategy':params.get('candidate_strategy','samples'),
                    'quality_guard':params.get('quality_guard',True),'candidate_failures':result.get('candidate_failures',[])}}
            completed.append(record)
            svg,pdf=item.get('vector_svg'),item.get('vector_pdf_base64')
            vector={'status':'skipped','requested':task.vector_export or 'none'}
            if task.task_type=='diagram' and task.vector_export not in {None,'none'}:
                svg,pdf,vector=await _maybe_generate_diagram_vector(chat_lb,desc,task.content or '',task.task_type,task.vector_export,on_event)
            if svg:
                rel=f'results/{task_id}/candidate_{ci}/final.svg';safe_artifact_path(rel).write_text(svg,encoding='utf-8');record['svg_path']=rel
            if pdf:
                rel=f'results/{task_id}/candidate_{ci}/final.pdf';safe_artifact_path(rel).write_bytes(base64.b64decode(pdf));record['pdf_path']=rel
            record['metadata']['vector_export']=vector
        if not completed and task.pipeline_mode!='dev_retriever':
            raise RuntimeError('没有有效图片输出；本次运行未完成')
    except asyncio.CancelledError:
        outcome,error='cancelled','已停止后续调用；上游已接受的请求可能仍计费。'
    except Exception as exc:
        outcome,error='failed',str(exc)
        logger.exception('Generation failed: %s',task_id)
    finally:
        if task is not None:
            async def finalize():
                nonlocal outcome
                async with AsyncSessionLocal() as db:
                    current=await db.scalar(select(GenerationTask).where(GenerationTask.id==task_id).with_for_update())
                    if current is None:
                        return
                    if current.status=='cancelled':
                        outcome='cancelled'
                    elif current.status!='running':
                        return
                    current.status=outcome;current.current_stage=None;current.error_message=error;current.completed_at=datetime.now(timezone.utc)
                    if outcome=='completed':
                        current.progress=1.
                    if cost_tracker:
                        current.cost_details=cost_tracker.summary();current.cost_estimated_usd=current.cost_details['total_usd']
                    records={item['candidate_index']:item for item in checkpoints.values()}
                    records.update({item['candidate_index']:item for item in completed})
                    for item in records.values():
                        db.add(GenerationResult(task_id=task_id,user_id=task.user_id,candidate_index=item['candidate_index'],
                            image_path=item['image_path'],svg_path=item.get('svg_path'),pdf_path=item.get('pdf_path'),
                            planner_desc=item.get('planner_description'),stylist_desc=item.get('stylist_description'),
                            critic_feedback=item.get('critic_feedback'),metadata_=item.get('metadata')))
                    db.add(PipelineEvent(task_id=task_id,event_type='done',event_data={'status':outcome,'message':error,'cost':cost_tracker.summary() if cost_tracker else None}))
                    await db.commit()
            await asyncio.shield(finalize())
