"""Refine API — image enhancement, upscaling, and style transfer."""

import base64
import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.models.user import User
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/refine", tags=["精修增强"])

REFINE_PROMPT = """You are an expert image enhancement specialist for academic publications.

**Instruction:** {instruction}

Please generate an improved version of the provided image. Maintain all data accuracy and semantic content while enhancing visual quality. Output ONLY the improved image."""

STYLE_TRANSFER_PROMPT = """You are a professional figure style transfer expert.

I am providing two images:
1. **Source figure** (first image) — this contains the content to preserve.
2. **Reference style image** (second image) — this shows the target visual style.

Generate a new figure that keeps the exact same content/structure as the source figure, but renders it in the visual style of the reference image.

Match: overall tone, line style, color usage, shading, icon style, arrow aesthetics, typography.
Output ONLY the resulting image."""


async def _generate_image_with_input(
    image_lb: Optional["LoadBalancer"],
    chat_lb: Optional["LoadBalancer"],
    prompt: str,
    input_images: list[dict],
    aspect_ratio: str = "1:1",
) -> Optional[bytes]:
    """Generate an image using multimodal input (text + images).

    Strategy:
    1. Try image_lb.generate_image_with_input if available (native image gen with input)
    2. Fall back to chat_lb.chat_with_images for models that support image output
       (e.g., Gemini 2.0 Flash with response_modalities=["IMAGE"])
    3. Fall back to image_lb.generate_image with prompt only (loses input images)
    """
    # Build multimodal contents: prompt text + input images
    contents = [prompt]
    for img in input_images:
        contents.append({
            "type": "image_base64",
            "data": img["b64"],
            "media_type": img.get("media_type", "image/png"),
        })

    # Strategy 1: Try Gemini-style native image generation with input images
    lb = image_lb or chat_lb
    if lb:
        try:
            result_bytes = await lb.generate_image_with_images(
                prompt=prompt,
                images=input_images,
                aspect_ratio=aspect_ratio,
            )
            if result_bytes:
                return result_bytes
        except (AttributeError, NotImplementedError):
            pass
        except Exception as e:
            logger.warning(f"generate_image_with_images failed: {e}")

    # Strategy 2: Use chat_with_images and extract image from response
    if chat_lb:
        try:
            result_bytes = await chat_lb.generate_image_from_chat(
                contents=contents,
                aspect_ratio=aspect_ratio,
            )
            if result_bytes:
                return result_bytes
        except (AttributeError, NotImplementedError):
            pass
        except Exception as e:
            logger.warning(f"generate_image_from_chat failed: {e}")

    # Strategy 3: Fallback — pure text prompt (loses input images)
    if lb:
        logger.warning("Falling back to text-only image generation (input images not used)")
        return await lb.generate_image(prompt=prompt, aspect_ratio=aspect_ratio)

    return None


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

    image_b64 = base64.b64encode(content).decode()
    prompt = REFINE_PROMPT.format(instruction=instruction)

    try:
        enhanced_bytes = await _generate_image_with_input(
            image_lb=image_lb,
            chat_lb=chat_lb,
            prompt=prompt,
            input_images=[{"b64": image_b64, "media_type": "image/png"}],
        )
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
    if not (image_lb or chat_lb):
        raise HTTPException(status_code=400, detail="没有可用的 API Key")

    source_b64 = base64.b64encode(source_bytes).decode()
    ref_b64 = base64.b64encode(ref_bytes).decode()

    try:
        result_bytes = await _generate_image_with_input(
            image_lb=image_lb,
            chat_lb=chat_lb,
            prompt=STYLE_TRANSFER_PROMPT,
            input_images=[
                {"b64": source_b64, "media_type": "image/png"},
                {"b64": ref_b64, "media_type": "image/png"},
            ],
        )
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
