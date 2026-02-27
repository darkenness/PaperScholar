from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, api_key: str, base_url: Optional[str] = None, model: str = "", **kwargs):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    @abstractmethod
    async def chat(self, messages: list[dict], temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs) -> str:
        """Send chat messages and return text response."""

    @abstractmethod
    async def chat_with_images(self, contents: list[Any], temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs) -> str:
        """Send multimodal content (text + images) and return text response."""

    @abstractmethod
    async def generate_image(self, prompt: str, **kwargs) -> Optional[bytes]:
        """Generate an image from a text prompt. Returns raw image bytes or None."""

    async def health_check(self) -> bool:
        """Check if the API key is valid. Returns True if accessible."""
        try:
            await self.chat([{"role": "user", "content": "hi"}], max_tokens=1)
            return True
        except Exception:
            return False
