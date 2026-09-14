"""Pipeline Evolution API — returns intermediate artifacts for visualization.
Implements P1-3 from the dev plan."""

import logging
import uuid
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
    candidate_index: int = 0
    image_url: Optional[str] = None
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
    task_id: uuid.UUID,
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
        ).order_by(PipelineEvent.id)
    )
    events = events_result.scalars().all()

    stages = build_evolution_stages(events)

    return EvolutionResponse(
        task_id=str(task_id),
        task_type=task.task_type,
        pipeline_mode=task.pipeline_mode or "unknown",
        stages=stages,
    )


def build_evolution_stages(events) -> list[EvolutionStage]:
    """Merge events by explicit candidate/stage/round; do not wait for 'done'.

    Missing legacy identifiers cannot be reconstructed; they remain candidate 0.
    Producers should include candidate_index and round on every event.
    """
    stages = {}
    active_round = {}
    for event in events:
        data = event.event_data or {}
        event_type = event.event_type
        if event_type not in {"stage", "intermediate"}:
            continue
        name = data.get("name") if event_type == "stage" else data.get("stage")
        if not name:
            continue
        candidate = data.get("candidate_index", data.get("candidate", 0))
        candidate = 0 if candidate is None else int(candidate)
        pair = (candidate, name)
        if "round" in data:
            round_num = data["round"]
            active_round[pair] = round_num
        else:
            round_num = active_round.get(pair)
        key = (candidate, name, round_num)
        stage = stages.get(key)
        if stage is None:
            stage = EvolutionStage(
                name=name, status="running", candidate_index=candidate, round=round_num,
                timestamp=event.created_at.isoformat() if event.created_at else None,
            )
            stages[key] = stage
        if event_type == "stage":
            stage.status = data.get("status", stage.status)
            if data.get("detail") and not stage.description:
                stage.description = data["detail"]
        elif data.get("type") == "text":
            content = data.get("content") or ""
            stage.description = (stage.description + "\n" + content) if stage.description else content
            if name == "critic":
                stage.suggestions = content
        elif data.get("type") in {"image_ready", "image"}:
            stage.image_available = True
            if data.get("image_url"):
                stage.image_url = data["image_url"]
    return list(stages.values())
