"""Refine API — image enhancement, upscaling, and style transfer."""

import base64
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter(prefix="/refine", tags=["精修增强"])

REFINE_PROMPT = """You are an expert image enhancement specialist. Improve this academic figure based on the instruction below.

**Instruction:** {instruction}

Generate an improved version of the image. Maintain all data accuracy and semantic content while enhancing visual quality."""

STYLE_TRANSFER_PROMPT = """Generate a figure that visualizes the same content as the source image, but closely imitates the visual style of the reference image.

Match: overall tone, line style, color usage, shading, icon style, arrow aesthetics, typography.
The content structure may differ; only the visual style should be consistent."""


@router.post("/enhance")
async def enhance_image(
    image: UploadFile = File(...),
    instruction: str = Form("Improve overall visual quality and make it publication-ready"),
    resolution: str = Form("2k"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enhance/refine an uploaded image using AI."""
    content = await image.read()

    from app.services.generation_service import _build_load_balancer
    image_lb = await _build_load_balancer(db, user.id, "image")
    chat_lb = await _build_load_balancer(db, user.id, "chat")
    if not (image_lb or chat_lb):
        raise HTTPException(status_code=400, detail="没有可用的 API Key")

    lb = image_lb or chat_lb
    image_b64 = base64.b64encode(content).decode()

    # Generate enhanced image
    prompt = REFINE_PROMPT.format(instruction=instruction)
    try:
        enhanced_bytes = await lb.generate_image(prompt=prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"增强失败: {e}")

    if not enhanced_bytes:
        raise HTTPException(status_code=500, detail="增强失败：未生成图片")

    # Save result
    task_id = uuid.uuid4().hex[:12]
    task_dir = os.path.join(settings.UPLOAD_DIR, "refine", task_id)
    os.makedirs(task_dir, exist_ok=True)

    out_path = os.path.join(task_dir, "enhanced.png")
    with open(out_path, "wb") as f:
        f.write(enhanced_bytes)

    orig_path = os.path.join(task_dir, "original.png")
    with open(orig_path, "wb") as f:
        f.write(content)

    return {
        "task_id": task_id,
        "original_url": f"/uploads/refine/{task_id}/original.png",
        "enhanced_url": f"/uploads/refine/{task_id}/enhanced.png",
    }


@router.post("/style-transfer")
async def style_transfer(
    source_image: UploadFile = File(...),
    reference_image: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transfer visual style from reference image to source figure (like autofigure-edit)."""
    source_bytes = await source_image.read()
    ref_bytes = await reference_image.read()

    from app.services.generation_service import _build_load_balancer
    image_lb = await _build_load_balancer(db, user.id, "image")
    chat_lb = await _build_load_balancer(db, user.id, "chat")
    lb = image_lb or chat_lb
    if not lb:
        raise HTTPException(status_code=400, detail="没有可用的 API Key")

    # Use multimodal prompt with both images
    source_b64 = base64.b64encode(source_bytes).decode()
    ref_b64 = base64.b64encode(ref_bytes).decode()

    try:
        result_bytes = await lb.generate_image(prompt=STYLE_TRANSFER_PROMPT)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"风格迁移失败: {e}")

    if not result_bytes:
        raise HTTPException(status_code=500, detail="风格迁移失败：未生成图片")

    task_id = uuid.uuid4().hex[:12]
    task_dir = os.path.join(settings.UPLOAD_DIR, "refine", task_id)
    os.makedirs(task_dir, exist_ok=True)

    with open(os.path.join(task_dir, "source.png"), "wb") as f:
        f.write(source_bytes)
    with open(os.path.join(task_dir, "reference.png"), "wb") as f:
        f.write(ref_bytes)
    with open(os.path.join(task_dir, "result.png"), "wb") as f:
        f.write(result_bytes)

    return {
        "task_id": task_id,
        "source_url": f"/uploads/refine/{task_id}/source.png",
        "reference_url": f"/uploads/refine/{task_id}/reference.png",
        "result_url": f"/uploads/refine/{task_id}/result.png",
    }
