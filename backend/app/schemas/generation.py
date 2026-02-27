import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    task_type: str = Field(..., pattern="^(diagram|plot)$")
    content: str = Field(..., min_length=10)
    visual_intent: str = Field(..., min_length=5)
    pipeline_mode: str = Field(default="dev_full", pattern="^(vanilla|dev_planner|dev_planner_stylist|dev_planner_critic|dev_full)$")
    retrieval_setting: str = Field(default="auto", pattern="^(auto|manual|random|none)$")
    num_candidates: int = Field(default=1, ge=1, le=20)
    aspect_ratio: Optional[str] = "1:1"
    max_critic_rounds: int = Field(default=3, ge=1, le=5)
    reference_image_ids: Optional[list[int]] = None


class TaskCreateResponse(BaseModel):
    task_id: uuid.UUID
    status: str
    stream_url: str


class TaskStatusResponse(BaseModel):
    task_id: uuid.UUID
    status: str
    progress: float
    current_stage: Optional[str]
    error_message: Optional[str]
    results: list["ResultResponse"]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ResultResponse(BaseModel):
    id: int
    candidate_index: int
    image_url: Optional[str]
    thumbnail_url: Optional[str]
    svg_url: Optional[str]
    quality_score: Optional[float]
    is_favorited: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class HistoryResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[TaskStatusResponse]


class FavoriteRequest(BaseModel):
    is_favorited: bool
