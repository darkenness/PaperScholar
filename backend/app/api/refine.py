"""Refine API — image enhancement, upscaling, and style transfer."""

import base64
import logging
import os
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.models.generation import GenerationResult, GenerationTask
from app.models.user import User
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/refine", tags=["精修增强"])

REFINE_PROMPT = """You are an expert image enhancement specialist for academic publications.

**Instruction:** {instruction}
**Target aspect ratio:** {aspect_ratio}
**Target resolution:** {resolution}

Please generate an improved version of the provided image. Maintain all data accuracy and semantic content while enhancing visual quality. Output ONLY the improved image."""

STYLE_TRANSFER_PROMPT = """You are a professional figure style transfer expert.

I am providing two images:
1. **Source figure** (first image) — this contains the content to preserve.
2. **Reference style image** (second image) — this shows the target visual style.

**Target aspect ratio:** {aspect_ratio}
**Target resolution:** {resolution}

Generate a new figure that keeps the exact same content/structure as the source figure, but renders it in the visual style of the reference image.

Match: overall tone, line style, color usage, shading, icon style, arrow aesthetics, typography.
Output ONLY the resulting image."""


async def _generate_image_with_input(
    image_lb: Optional["LoadBalancer"],
    chat_lb: Optional["LoadBalancer"],
    prompt: str,
    input_images: list[dict],
    aspect_ratio: str = "1:1",
    image_size: str = "1k",
) -> Optional[bytes]:
    """Generate an image using multimodal input (text + images).

    Uses generate_image_with_images which handles both Gemini native and
    OpenAI-compat providers. Falls back to text-only generation only if
    the method is not supported at all (AttributeError/NotImplementedError).
    """
    lb = image_lb or chat_lb
    if not lb:
        return None

    # Primary: image-to-image generation (passes original image to model)
    try:
        result_bytes = await lb.generate_image_with_images(
            prompt=prompt,
            images=input_images,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
        )
        if result_bytes:
            return result_bytes
    except (AttributeError, NotImplementedError):
        logger.info("generate_image_with_images not supported, trying fallback")
    except Exception as e:
        logger.warning(f"generate_image_with_images failed: {e}")

    # Fallback: text-only image generation (loses input images)
    logger.warning("Falling back to text-only image generation (input images not used)")
    return await lb.generate_image(prompt=prompt, aspect_ratio=aspect_ratio, image_size=image_size)


@router.post("/enhance")
async def enhance_image(
    image: UploadFile = File(...),
    instruction: str = Form("Improve overall visual quality and make it publication-ready"),
    resolution: str = Form("2K"),
    aspect_ratio: str = Form("16:9"),
    chat_model_name: Optional[str] = Form(None),
    chat_key_id: Optional[int] = Form(None),
    image_model_name: Optional[str] = Form(None),
    image_key_id: Optional[int] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enhance/refine an uploaded image using AI.
    
    resolution: Target resolution — "2K" or "4K". Higher resolution takes longer but yields better quality.
    aspect_ratio: Target aspect ratio — "16:9", "4:3", "3:4", "1:1", "9:16".
    """
    content = await image.read()
    modelSel_image = image_model_name  # capture for history

    from app.services.generation_service import _build_load_balancer
    image_lb = await _build_load_balancer(db, user.id, "image", key_id=image_key_id, model_name=image_model_name)
    chat_lb = await _build_load_balancer(db, user.id, "chat", key_id=chat_key_id, model_name=chat_model_name)
    if not (image_lb or chat_lb):
        raise HTTPException(status_code=400, detail="没有可用的 API Key")

    image_b64 = base64.b64encode(content).decode()
    prompt = REFINE_PROMPT.format(instruction=instruction, aspect_ratio=aspect_ratio, resolution=resolution)

    try:
        enhanced_bytes = await _generate_image_with_input(
            image_lb=image_lb,
            chat_lb=chat_lb,
            prompt=prompt,
            input_images=[{"b64": image_b64, "media_type": "image/png"}],
            aspect_ratio=aspect_ratio,
            image_size=resolution,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"增强失败: {e}")

    if not enhanced_bytes:
        raise HTTPException(status_code=500, detail="增强失败：未生成图片")

    # Save result files
    task_id = _uuid.uuid4()
    short_id = task_id.hex[:12]
    task_dir = os.path.join(settings.UPLOAD_DIR, "refine", short_id)
    os.makedirs(task_dir, exist_ok=True)

    out_path = os.path.join(task_dir, "enhanced.png")
    with open(out_path, "wb") as f:
        f.write(enhanced_bytes)

    orig_path = os.path.join(task_dir, "original.png")
    with open(orig_path, "wb") as f:
        f.write(content)

    # Save to history
    now = datetime.now(timezone.utc)
    task_record = GenerationTask(
        id=task_id, user_id=user.id, task_type="refine_enhance",
        content=instruction, visual_intent=f"{resolution} · {aspect_ratio}",
        pipeline_mode="enhance", status="completed",
        image_model=modelSel_image or None,
        started_at=now, completed_at=now, progress=1.0,
    )
    db.add(task_record)
    await db.flush()
    result_record = GenerationResult(
        task_id=task_id, user_id=user.id, candidate_index=0,
        image_path=f"refine/{short_id}/enhanced.png",
    )
    db.add(result_record)
    await db.commit()

    return {
        "task_id": short_id,
        "original_url": f"/uploads/refine/{short_id}/original.png",
        "enhanced_url": f"/uploads/refine/{short_id}/enhanced.png",
    }


@router.post("/style-transfer")
async def style_transfer(
    source_image: UploadFile = File(...),
    reference_image: UploadFile = File(...),
    resolution: str = Form("2K"),
    aspect_ratio: str = Form("16:9"),
    chat_model_name: Optional[str] = Form(None),
    chat_key_id: Optional[int] = Form(None),
    image_model_name: Optional[str] = Form(None),
    image_key_id: Optional[int] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transfer visual style from reference image to source figure.
    
    resolution: Target resolution — "2K" or "4K".
    aspect_ratio: Target aspect ratio — "16:9", "4:3", "3:4", "1:1", "9:16".
    """
    source_bytes = await source_image.read()
    ref_bytes = await reference_image.read()
    modelSel_image = image_model_name  # capture for history

    from app.services.generation_service import _build_load_balancer
    image_lb = await _build_load_balancer(db, user.id, "image", key_id=image_key_id, model_name=image_model_name)
    chat_lb = await _build_load_balancer(db, user.id, "chat", key_id=chat_key_id, model_name=chat_model_name)
    if not (image_lb or chat_lb):
        raise HTTPException(status_code=400, detail="没有可用的 API Key")

    source_b64 = base64.b64encode(source_bytes).decode()
    ref_b64 = base64.b64encode(ref_bytes).decode()
    prompt = STYLE_TRANSFER_PROMPT.format(aspect_ratio=aspect_ratio, resolution=resolution)

    try:
        result_bytes = await _generate_image_with_input(
            image_lb=image_lb,
            chat_lb=chat_lb,
            prompt=prompt,
            input_images=[
                {"b64": source_b64, "media_type": "image/png"},
                {"b64": ref_b64, "media_type": "image/png"},
            ],
            aspect_ratio=aspect_ratio,
            image_size=resolution,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"风格迁移失败: {e}")

    if not result_bytes:
        raise HTTPException(status_code=500, detail="风格迁移失败：未生成图片")

    task_id = _uuid.uuid4()
    short_id = task_id.hex[:12]
    task_dir = os.path.join(settings.UPLOAD_DIR, "refine", short_id)
    os.makedirs(task_dir, exist_ok=True)

    with open(os.path.join(task_dir, "source.png"), "wb") as f:
        f.write(source_bytes)
    with open(os.path.join(task_dir, "reference.png"), "wb") as f:
        f.write(ref_bytes)
    with open(os.path.join(task_dir, "result.png"), "wb") as f:
        f.write(result_bytes)

    # Save to history
    now = datetime.now(timezone.utc)
    task_record = GenerationTask(
        id=task_id, user_id=user.id, task_type="refine_style",
        visual_intent=f"{resolution} · {aspect_ratio}",
        pipeline_mode="style-transfer", status="completed",
        image_model=modelSel_image or None,
        started_at=now, completed_at=now, progress=1.0,
    )
    db.add(task_record)
    await db.flush()
    result_record = GenerationResult(
        task_id=task_id, user_id=user.id, candidate_index=0,
        image_path=f"refine/{short_id}/result.png",
    )
    db.add(result_record)
    await db.commit()

    return {
        "task_id": short_id,
        "source_url": f"/uploads/refine/{short_id}/source.png",
        "reference_url": f"/uploads/refine/{short_id}/reference.png",
        "result_url": f"/uploads/refine/{short_id}/result.png",
    }
