import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    task_type: str = Field(..., pattern="^(diagram|plot)$")
    content: str = Field(..., min_length=10)
    visual_intent: str = Field(..., min_length=5)
    pipeline_mode: str = Field(default="demo_full", pattern="^(vanilla|dev_planner|dev_planner_stylist|dev_planner_critic|dev_full|demo_planner_critic|demo_full|dev_polish|dev_retriever)$")
    retrieval_setting: str = Field(default="auto", pattern="^(auto|manual|random|none)$")
    num_candidates: int = Field(default=1, ge=1, le=20)
    aspect_ratio: Optional[str] = "1:1"
    max_critic_rounds: int = Field(default=2, ge=1, le=5)
    retriever_content_limit: Optional[int] = Field(default=None, description="Retriever候选内容截断长度，None=不截断（完整内容）")
    retriever_top_k: int = Field(default=10, ge=1, le=20, description="Retriever返回的参考示例数量")
    retriever_pool_size: Optional[int] = Field(default=None, description="Retriever候选池最大条数，None=使用默认值")
    reference_image_ids: Optional[list[int]] = None
    chat_model_name: Optional[str] = Field(default=None, description="指定 chat 模型名称")
    chat_key_id: Optional[int] = Field(default=None, description="指定 chat 供应商（API Key 配置 ID）")
    image_model_name: Optional[str] = Field(default=None, description="指定 image 模型名称")
    image_key_id: Optional[int] = Field(default=None, description="指定 image 供应商（API Key 配置 ID）")


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


class ModelProviderInfo(BaseModel):
    key_id: int
    provider: str
    base_url: Optional[str]
    api_key_preview: str
    is_system: bool
    priority: int

    model_config = {"from_attributes": True}


class ModelGroupInfo(BaseModel):
    model_name: str
    providers: list[ModelProviderInfo]


class AvailableModelsResponse(BaseModel):
    chat_models: list[ModelGroupInfo]
    image_models: list[ModelGroupInfo]
