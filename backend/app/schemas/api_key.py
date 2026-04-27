from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    model_type: str = Field(..., pattern="^(chat|image)$")
    provider: str = Field(..., pattern="^(openai_compat|openai_images|gemini|anthropic)$")
    base_url: Optional[str] = None
    api_key: str = Field(..., min_length=10)
    model_name: Optional[str] = None


class ApiKeyUpdate(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = Field(None, min_length=10)
    model_name: Optional[str] = None
    priority: Optional[int] = None
    is_enabled: Optional[bool] = None


class ApiKeyResponse(BaseModel):
    id: int
    model_type: str
    provider: str
    base_url: Optional[str]
    api_key_preview: str
    model_name: Optional[str]
    is_verified: bool
    is_enabled: bool
    priority: int
    last_verified_at: Optional[datetime]
    last_error: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyListResponse(BaseModel):
    chat_keys: list[ApiKeyResponse]
    image_keys: list[ApiKeyResponse]


class ApiKeyVerifyResponse(BaseModel):
    is_verified: bool
    message: str


class ApiApplicationCreate(BaseModel):
    reason: str = Field(..., min_length=10, max_length=1000)


class ApiApplicationResponse(BaseModel):
    id: int
    status: str
    reason: Optional[str]
    review_comment: Optional[str]
    created_at: datetime
    reviewed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ApiApplicationReview(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$")
    comment: Optional[str] = None
