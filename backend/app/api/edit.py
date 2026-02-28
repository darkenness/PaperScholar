"""Edit API — vectorization and SVG editing endpoints."""

import base64
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
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
    task_id = uuid.uuid4().hex[:12]
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
        task_id = uuid.uuid4().hex[:12]
        task_dir = os.path.join(settings.UPLOAD_DIR, "svg", task_id)
        os.makedirs(task_dir, exist_ok=True)
        svg_path = os.path.join(task_dir, "figure.svg")
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(result["svg_code"])
        result["svg_url"] = f"/uploads/svg/{task_id}/figure.svg"

    return result
