from typing import Optional

from app.llm.base_client import BaseLLMClient
from app.llm.openai_client import OpenAICompatClient
from app.llm.gemini_client import GeminiNativeClient
from app.llm.anthropic_client import AnthropicClient


class LLMClientFactory:
    """Factory for creating LLM clients based on provider type."""

    @staticmethod
    def create(
        provider: str,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = "",
        **kwargs,
    ) -> BaseLLMClient:
        if provider == "openai_compat":
            return OpenAICompatClient(
                api_key=api_key,
                base_url=base_url or "https://openrouter.ai/api/v1",
                model=model,
                image_api_mode="chat",
                **kwargs,
            )
        elif provider == "openai_images":
            return OpenAICompatClient(
                api_key=api_key,
                base_url=base_url or "https://api.openai.com/v1",
                model=model or "gpt-image-1",
                image_api_mode="images",
                **kwargs,
            )
        elif provider == "gemini":
            return GeminiNativeClient(
                api_key=api_key,
                base_url=base_url,
                model=model or "gemini-2.5-pro",
                **kwargs,
            )
        elif provider == "anthropic":
            return AnthropicClient(
                api_key=api_key,
                base_url=base_url or "https://api.anthropic.com",
                model=model or "claude-sonnet-4-20250514",
                **kwargs,
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")
