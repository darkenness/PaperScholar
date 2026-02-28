"""Evaluation API — quality assessment endpoints for generated diagrams/plots.
Implements P1-2 from the dev plan."""

import base64
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.generation import GenerationResult, GenerationTask
from app.models.user import User
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evaluate", tags=["质量评估"])


class EvaluateRequest(BaseModel):
    gt_image_base64: Optional[str] = None  # Ground truth image (optional for standalone)


class EvaluateResponse(BaseModel):
    task_id: str
    task_type: str
    eval_type: str  # "referenced" or "standalone"
    dimensions: dict  # Per-dimension results
    overall_outcome: Optional[str] = None
    overall_score: Optional[float] = None
    overall_reasoning: Optional[str] = None


@router.post("/{task_id}", response_model=EvaluateResponse)
async def evaluate_task(
    task_id: str,
    req: EvaluateRequest = EvaluateRequest(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate the quality of a generated diagram/plot.

    If gt_image_base64 is provided, runs referenced comparison (Human vs Model).
    Otherwise, runs standalone quality assessment.
    """
    # Fetch task and result
    task_result = await db.execute(
        select(GenerationTask).where(
            GenerationTask.id == task_id,
            GenerationTask.user_id == user.id,
        )
    )
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Task is not completed yet")

    # Get the result with image
    result_query = await db.execute(
        select(GenerationResult).where(
            GenerationResult.task_id == task_id,
            GenerationResult.user_id == user.id,
        ).order_by(GenerationResult.candidate_index)
    )
    result = result_query.scalars().first()
    if not result or not result.image_path:
        raise HTTPException(status_code=400, detail="No generated image found for this task")

    # Load model image
    import os
    from app.config import settings
    abs_image_path = os.path.join(settings.UPLOAD_DIR, result.image_path)
    if not os.path.exists(abs_image_path):
        raise HTTPException(status_code=400, detail="Generated image file not found on disk")

    with open(abs_image_path, "rb") as f:
        model_image_base64 = base64.b64encode(f.read()).decode()

    # Build chat load balancer
    from app.services.generation_service import _build_load_balancer
    try:
        chat_lb = await _build_load_balancer(
            db, user.id, "chat",
            key_id=task.chat_key_id,
            model_name=task.chat_model,
        )
        if not chat_lb:
            raise RuntimeError("No chat model available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize chat model: {e}")

    from app.services.evaluation_service import evaluate_generation, evaluate_standalone

    if req.gt_image_base64:
        # Referenced comparison mode
        eval_results = await evaluate_generation(
            chat_lb=chat_lb,
            task_type=task.task_type,
            content=task.content or "",
            visual_intent=task.visual_intent or "",
            gt_image_base64=req.gt_image_base64,
            model_image_base64=model_image_base64,
        )

        # Save eval details to result
        result.eval_details = eval_results
        result.quality_score = _outcome_to_score(eval_results.get("overall_outcome", "Unknown"))
        await db.commit()

        return EvaluateResponse(
            task_id=str(task_id),
            task_type=task.task_type,
            eval_type="referenced",
            dimensions={
                dim: {
                    "outcome": eval_results.get(f"{dim}_outcome", "Unknown"),
                    "reasoning": eval_results.get(f"{dim}_reasoning", ""),
                }
                for dim in ["faithfulness", "conciseness", "readability", "aesthetics"]
            },
            overall_outcome=eval_results.get("overall_outcome"),
            overall_reasoning=eval_results.get("overall_reasoning"),
        )
    else:
        # Standalone quality assessment
        eval_results = await evaluate_standalone(
            chat_lb=chat_lb,
            task_type=task.task_type,
            content=task.content or "",
            visual_intent=task.visual_intent or "",
            model_image_base64=model_image_base64,
        )

        result.eval_details = eval_results
        result.quality_score = eval_results.get("overall_score")
        await db.commit()

        return EvaluateResponse(
            task_id=str(task_id),
            task_type=task.task_type,
            eval_type="standalone",
            dimensions={
                dim: {
                    "score": eval_results.get(f"{dim}_score"),
                    "reasoning": eval_results.get(f"{dim}_reasoning", ""),
                }
                for dim in ["readability", "aesthetics"]
            },
            overall_score=eval_results.get("overall_score"),
        )


def _outcome_to_score(outcome: str) -> float:
    """Convert evaluation outcome to a numeric quality score."""
    mapping = {
        "Model": 0.9,
        "Both are good": 0.75,
        "Human": 0.4,
        "Both are bad": 0.2,
        "Unknown": 0.5,
        "Error": 0.0,
    }
    return mapping.get(outcome, 0.5)
