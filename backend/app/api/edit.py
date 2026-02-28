"""Edit API — vectorization, SVG editing, and paper extraction endpoints."""

import base64
import io
import os
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.models.generation import GenerationResult, GenerationTask
from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter(prefix="/edit", tags=["图表编辑"])


@router.post("")
async def create_edit_task(
    image: UploadFile = File(...),
    sam_backend: str = Form("fal"),
    sam_api_key: Optional[str] = Form(None),
    sam_prompts: str = Form("icon,diagram,arrow"),
    reference_image: Optional[UploadFile] = File(None),
    chat_model_name: Optional[str] = Form(None),
    chat_key_id: Optional[int] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload an image and run the vectorization pipeline (autofigure-edit style)."""
    content = await image.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"文件太大，最大 {settings.MAX_UPLOAD_SIZE_MB}MB")

    # Build LLM client from user's keys (with optional model selection)
    from app.services.generation_service import _build_load_balancer
    chat_lb = await _build_load_balancer(db, user.id, "chat", key_id=chat_key_id, model_name=chat_model_name)
    if not chat_lb:
        raise HTTPException(status_code=400, detail="没有可用的 Chat 模型 API Key")

    # Save uploaded image
    task_uuid = _uuid.uuid4()
    task_id = task_uuid.hex[:12]
    task_dir = os.path.join(settings.UPLOAD_DIR, "edit", task_id)
    os.makedirs(task_dir, exist_ok=True)

    figure_path = os.path.join(task_dir, "figure.png")
    with open(figure_path, "wb") as f:
        f.write(content)

    # Run edit pipeline
    from app.services.edit_service import run_edit_pipeline
    result = await run_edit_pipeline(
        image_bytes=content,
        sam_api_key=sam_api_key,
        sam_backend=sam_backend,
        sam_prompts=sam_prompts,
        chat_lb=chat_lb,
    )

    # Save SVG template
    svg_path = None
    if result.get("svg_template"):
        svg_path = os.path.join(task_dir, "template.svg")
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(result["svg_template"])

    # Save icon crops to disk for later assembly
    if result.get("icon_crops"):
        from app.services.edit_service import save_icon_crops
        await save_icon_crops(task_dir, result["icon_crops"])

    # Save to history
    now = datetime.now(timezone.utc)
    task_record = GenerationTask(
        id=task_uuid, user_id=user.id, task_type="edit",
        content=sam_prompts, pipeline_mode="vectorize",
        status="completed", started_at=now, completed_at=now, progress=1.0,
    )
    db.add(task_record)
    await db.flush()
    result_record = GenerationResult(
        task_id=task_uuid, user_id=user.id, candidate_index=0,
        image_path=f"edit/{task_id}/figure.png",
        svg_path=f"edit/{task_id}/template.svg" if svg_path else None,
    )
    db.add(result_record)
    await db.commit()

    return {
        "task_id": task_id,
        "figure_url": f"/uploads/edit/{task_id}/figure.png",
        "svg_template": result.get("svg_template"),
        "svg_url": f"/uploads/edit/{task_id}/template.svg" if svg_path else None,
        "boxes": result.get("boxes", []),
        "icon_count": len(result.get("icon_crops", [])),
        "icons": [
            {"label": ic["label"], "width": ic["width"], "height": ic["height"]}
            for ic in result.get("icon_crops", [])
        ],
    }


@router.post("/svg-generate")
async def generate_svg(
    description: str = Form(...),
    content: str = Form(""),
    max_iterations: int = Form(5),
    quality_threshold: float = Form(8.0),
    chat_model_name: Optional[str] = Form(None),
    chat_key_id: Optional[int] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate an SVG figure using AutoFigure-style iterative refinement."""
    from app.services.generation_service import _build_load_balancer
    chat_lb = await _build_load_balancer(db, user.id, "chat", key_id=chat_key_id, model_name=chat_model_name)
    if not chat_lb:
        raise HTTPException(status_code=400, detail="没有可用的 Chat 模型 API Key")

    from app.services.svg_service import generate_svg_figure
    result = await generate_svg_figure(
        description=description,
        content=content,
        chat_lb=chat_lb,
        max_iterations=max_iterations,
        quality_threshold=quality_threshold,
    )

    # Save SVG
    if result.get("svg_code"):
        task_uuid = _uuid.uuid4()
        task_id = task_uuid.hex[:12]
        task_dir = os.path.join(settings.UPLOAD_DIR, "svg", task_id)
        os.makedirs(task_dir, exist_ok=True)
        svg_path = os.path.join(task_dir, "figure.svg")
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(result["svg_code"])
        result["svg_url"] = f"/uploads/svg/{task_id}/figure.svg"

        # Save to history
        now = datetime.now(timezone.utc)
        task_record = GenerationTask(
            id=task_uuid, user_id=user.id, task_type="edit",
            content=content[:500] if content else None,
            visual_intent=description[:200],
            pipeline_mode="svg-generate", status="completed",
            started_at=now, completed_at=now, progress=1.0,
        )
        db.add(task_record)
        await db.flush()
        result_record = GenerationResult(
            task_id=task_uuid, user_id=user.id, candidate_index=0,
            svg_path=f"svg/{task_id}/figure.svg",
        )
        db.add(result_record)
        await db.commit()

    return result


@router.post("/extract-methodology")
async def extract_methodology_from_paper(
    file: UploadFile = File(...),
    chat_model_name: Optional[str] = Form(None),
    chat_key_id: Optional[int] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract methodology section from a paper (PDF, Markdown, or text file).

    Returns the extracted methodology text that can be used as input
    for figure generation.
    """
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"文件太大，最大 {settings.MAX_UPLOAD_SIZE_MB}MB")

    filename = file.filename or "paper.pdf"

    from app.services.generation_service import _build_load_balancer
    chat_lb = await _build_load_balancer(db, user.id, "chat", key_id=chat_key_id, model_name=chat_model_name)
    if not chat_lb:
        raise HTTPException(status_code=400, detail="没有可用的 Chat 模型 API Key")

    from app.services.extractor_service import extract_methodology
    methodology = await extract_methodology(
        file_bytes=content,
        filename=filename,
        chat_lb=chat_lb,
    )

    if not methodology:
        raise HTTPException(status_code=422, detail="无法从文件中提取方法论，请确保文件包含足够的方法描述内容")

    return {
        "methodology": methodology,
        "char_count": len(methodology),
        "source_filename": filename,
    }


@router.post("/assemble")
async def assemble_final_svg(
    task_id: str = Form(...),
    chat_model_name: Optional[str] = Form(None),
    chat_key_id: Optional[int] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assemble final SVG by replacing placeholders with actual icon images.

    Takes a previously vectorized task (with template SVG + icon crops)
    and produces the final assembled SVG with icons embedded.
    """
    task_dir = os.path.join(settings.UPLOAD_DIR, "edit", task_id)
    template_path = os.path.join(task_dir, "template.svg")

    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="未找到该任务的 SVG 模板，请先执行矢量化")

    with open(template_path, "r", encoding="utf-8") as f:
        template_svg = f.read()

    # Load icon crops from the figure
    figure_path = os.path.join(task_dir, "figure.png")
    if not os.path.exists(figure_path):
        raise HTTPException(status_code=404, detail="未找到原始图片")

    from app.services.generation_service import _build_load_balancer
    chat_lb = await _build_load_balancer(db, user.id, "chat", key_id=chat_key_id, model_name=chat_model_name)

    from app.services.edit_service import assemble_final_svg as do_assemble
    final_svg = await do_assemble(
        template_svg=template_svg,
        task_dir=task_dir,
        chat_lb=chat_lb,
    )

    if not final_svg:
        raise HTTPException(status_code=500, detail="SVG 组装失败")

    # Save final SVG
    final_path = os.path.join(task_dir, "final.svg")
    with open(final_path, "w", encoding="utf-8") as f:
        f.write(final_svg)

    return {
        "task_id": task_id,
        "final_svg": final_svg,
        "final_svg_url": f"/uploads/edit/{task_id}/final.svg",
    }
