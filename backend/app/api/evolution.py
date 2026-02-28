"""Pipeline Evolution API — returns intermediate artifacts for visualization.
Implements P1-3 from the dev plan."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.generation import GenerationTask, PipelineEvent
from app.models.user import User
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generate", tags=["Pipeline Evolution"])


class EvolutionStage(BaseModel):
    name: str
    status: str
    round: Optional[int] = None
    description: Optional[str] = None
    image_available: bool = False
    suggestions: Optional[str] = None
    timestamp: Optional[str] = None


class EvolutionResponse(BaseModel):
    task_id: str
    task_type: str
    pipeline_mode: str
    stages: list[EvolutionStage]


@router.get("/{task_id}/evolution", response_model=EvolutionResponse)
async def get_pipeline_evolution(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the pipeline evolution stages with intermediate artifacts for a task.

    Each stage includes:
    - Stage name (planner, stylist, visualizer, critic round N, polish)
    - Description text (truncated)
    - Whether an image is available at this stage
    - Critic suggestions (for critic rounds)
    """
    # Fetch task
    task_result = await db.execute(
        select(GenerationTask).where(
            GenerationTask.id == task_id,
            GenerationTask.user_id == user.id,
        )
    )
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Fetch all pipeline events for this task, ordered by creation time
    events_result = await db.execute(
        select(PipelineEvent).where(
            PipelineEvent.task_id == task_id,
        ).order_by(PipelineEvent.created_at)
    )
    events = events_result.scalars().all()

    # Build evolution stages from events
    stages: list[EvolutionStage] = []
    seen_stages = set()

    for event in events:
        data = event.event_data or {}
        etype = event.event_type

        if etype == "stage":
            stage_name = data.get("name", "unknown")
            stage_status = data.get("status", "unknown")
            round_num = data.get("round")

            # Create a unique key for deduplication
            key = f"{stage_name}_{round_num}" if round_num is not None else stage_name

            if stage_status == "done" and key not in seen_stages:
                seen_stages.add(key)
                stages.append(EvolutionStage(
                    name=stage_name,
                    status=stage_status,
                    round=round_num,
                    timestamp=event.created_at.isoformat() if event.created_at else None,
                ))

        elif etype == "intermediate":
            itype = data.get("type", "")
            stage_name = data.get("stage", "")

            if itype == "text" and stage_name and stages:
                # Attach description to the latest matching stage
                for s in reversed(stages):
                    if s.name == stage_name:
                        content = data.get("content", "")
                        if s.description:
                            s.description += "\n" + content
                        else:
                            s.description = content

                        # Check for critic suggestions
                        if stage_name == "critic":
                            s.suggestions = content
                        break

            elif itype == "image_ready" and stages:
                # Mark the latest stage as having an image
                for s in reversed(stages):
                    if s.name == stage_name or not stage_name:
                        s.image_available = True
                        break

    return EvolutionResponse(
        task_id=str(task_id),
        task_type=task.task_type,
        pipeline_mode=task.pipeline_mode or "unknown",
        stages=stages,
    )
