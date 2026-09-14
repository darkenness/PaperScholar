from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class ProviderOptions(BaseModel):
    send_modalities: bool = True
    send_image_config: bool = True
    send_temperature: bool = True
    token_parameter: str = Field(default="max_tokens", pattern="^(max_tokens|max_completion_tokens)$")
    image_quality: Optional[str] = Field(default=None, max_length=30)
    max_concurrency: int = Field(default=1, ge=1, le=8)
    timeout_seconds: int = Field(default=180, ge=15, le=600)
    model_config = {"extra": "forbid"}


class ApiKeyCreate(BaseModel):
    model_type: str = Field(..., pattern="^(chat|image)$")
    provider: str = Field(..., pattern="^(openai_compat|openai_images|gemini|anthropic)$")
    base_url: Optional[str] = None
    api_key: str = Field(..., min_length=1, max_length=1000)
    model_name: Optional[str] = None


    display_name: Optional[str] = Field(default=None, max_length=100)
    api_options: ProviderOptions = Field(default_factory=ProviderOptions)

    @field_validator("api_key")
    @classmethod
    def nonempty_key(cls, value):
        if not value.strip():
            raise ValueError("API Key 不能为空")
        return value.strip()

    @model_validator(mode="after")
    def require_openai_compat_model(self):
        if self.provider == "openai_compat" and not (self.model_name or "").strip():
            raise ValueError("openai_compat 必须提供模型 ID")
        return self


class ModelDiscoveryRequest(BaseModel):
    provider: str = Field(..., pattern="^(openai_compat|openai_images|gemini|anthropic)$")
    base_url: Optional[str] = None
    api_key: str = Field(..., min_length=1, max_length=1000)


class ApiKeyUpdate(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = Field(None, min_length=1, max_length=1000)
    model_name: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=0)
    provider: Optional[str] = Field(None, pattern="^(openai_compat|openai_images|gemini|anthropic)$")
    display_name: Optional[str] = Field(default=None, max_length=100)
    api_options: Optional[ProviderOptions] = None
    is_enabled: Optional[bool] = None


class ApiKeyResponse(BaseModel):
    id: int
    model_type: str
    provider: str
    base_url: Optional[str]
    api_key_preview: str
    model_name: Optional[str]
    display_name: Optional[str] = None
    api_options: dict = Field(default_factory=dict)
    capability_status: dict = Field(default_factory=dict)
    endpoints: dict = Field(default_factory=dict)
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
    capability: str = "default"
    status: str = "unknown"
    latency_ms: Optional[int] = None
    error_code: Optional[int] = None
    capability_status: dict = Field(default_factory=dict)


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


class ModelCloneRequest(BaseModel):
    model_type: str = Field(..., pattern="^(chat|image)$")
    provider: str = Field(..., pattern="^(openai_compat|openai_images|gemini|anthropic)$")
    model_name: str = Field(..., min_length=1, max_length=200)
