import base64
from typing import Any, Optional

import httpx

from app.llm.base_client import BaseLLMClient


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude API client."""

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com", model: str = "claude-sonnet-4-20250514", **kwargs):
        super().__init__(api_key=api_key, base_url=base_url, model=model, **kwargs)

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    async def chat(self, messages: list[dict], temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs) -> str:
        system_msg = None
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                user_messages.append(msg)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": user_messages,
            "max_tokens": max_tokens or 4096,
            "temperature": temperature,
        }
        if system_msg:
            payload["system"] = system_msg

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]

    async def chat_with_images(self, contents: list[Any], temperature: float = 0.7, max_tokens: Optional[int] = None, system_prompt: Optional[str] = None, **kwargs) -> str:
        message_content = []
        for item in contents:
            if isinstance(item, str):
                message_content.append({"type": "text", "text": item})
            elif isinstance(item, dict) and item.get("type") == "image_base64":
                message_content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": item.get("media_type", "image/png"),
                        "data": item["data"],
                    },
                })
            elif isinstance(item, bytes):
                b64 = base64.b64encode(item).decode()
                message_content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": b64},
                })

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": message_content}],
            "max_tokens": max_tokens or 4096,
            "temperature": temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]

    async def generate_image(self, prompt: str, **kwargs) -> Optional[bytes]:
        # Anthropic does not natively support image generation
        return None

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/messages",
                    headers=self._headers(),
                    json={
                        "model": self.model,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
                return resp.status_code in (200, 429)
        except Exception:
            return False
