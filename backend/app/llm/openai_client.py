import base64
from typing import Any, Optional

import httpx

from app.llm.base_client import BaseLLMClient


class OpenAICompatClient(BaseLLMClient):
    """OpenAI-compatible API client (OpenRouter, Bianxie, custom endpoints)."""

    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1", model: str = "gemini-2.5-pro", **kwargs):
        super().__init__(api_key=api_key, base_url=base_url, model=model, **kwargs)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat(self, messages: list[dict], temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def chat_with_images(self, contents: list[Any], temperature: float = 0.7, max_tokens: Optional[int] = None, system_prompt: Optional[str] = None, **kwargs) -> str:
        message_content = []
        for item in contents:
            if isinstance(item, str):
                message_content.append({"type": "text", "text": item})
            elif isinstance(item, dict) and item.get("type") == "image_base64":
                message_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{item.get('media_type', 'image/png')};base64,{item['data']}"},
                })
            elif isinstance(item, bytes):
                b64 = base64.b64encode(item).decode()
                message_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                })

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message_content})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def generate_image(self, prompt: str, **kwargs) -> Optional[bytes]:
        """Generate image via /chat/completions (GPT-4o style).

        The model returns image data inline in the chat response as
        base64-encoded data URIs within image_url content parts.
        """
        system_instruction = kwargs.get("system_instruction")
        messages: list[dict] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": kwargs.get("image_model", self.model),
            "messages": messages,
        }

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return self._extract_image_from_response(data)

    async def generate_image_with_images(self, prompt: str, images: list[dict], **kwargs) -> Optional[bytes]:
        """Image-to-image generation via /chat/completions (GPT-4o style).

        Sends the original image(s) + prompt, and extracts generated image
        from the response.
        """
        # Build multimodal user content: text + input images
        user_content: list[dict] = [{"type": "text", "text": prompt}]
        for img in images:
            b64 = img.get("b64", "")
            media_type = img.get("media_type", "image/png")
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{b64}"},
            })

        messages: list[dict] = [{"role": "user", "content": user_content}]

        payload: dict[str, Any] = {
            "model": kwargs.get("image_model", self.model),
            "messages": messages,
        }

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return self._extract_image_from_response(data)

    @staticmethod
    def _extract_image_from_response(data: dict) -> Optional[bytes]:
        """Extract base64 image bytes from a chat completions response.

        Handles multiple response formats:
        1. content is list with image_url parts (GPT-4o style)
        2. content is list with image parts
        3. content is a string with markdown-style base64 image (e.g. ![image](data:image/...;base64,...))
        4. content is a plain base64 string (some providers)
        """
        import re

        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if content is None:
            return None

        if isinstance(content, list):
            for part in content:
                # Format: {"type": "image_url", "image_url": {"url": "data:image/...;base64,..."}}
                if part.get("type") == "image_url":
                    url = part.get("image_url", {}).get("url", "")
                    if url.startswith("data:"):
                        b64_str = url.split(",", 1)[1]
                        return base64.b64decode(b64_str)
                # Format: {"type": "image", "image": {"data": "base64..."}}
                if part.get("type") == "image":
                    img_data = part.get("image", {})
                    if isinstance(img_data, dict) and "data" in img_data:
                        return base64.b64decode(img_data["data"])

        if isinstance(content, str) and content:
            # Try markdown-style: ![...](data:image/...;base64,...)
            match = re.search(r'data:image/[^;]+;base64,([A-Za-z0-9+/=\s]+)', content)
            if match:
                b64_str = match.group(1).replace('\n', '').replace(' ', '')
                return base64.b64decode(b64_str)

        return None

    async def generate_image_from_chat(self, contents: list, **kwargs) -> Optional[bytes]:
        """Generate image from multimodal chat contents via /chat/completions.

        Accepts the same content format as chat_with_images (text strings,
        image_base64 dicts, raw bytes) but extracts image data from the response
        instead of text.
        """
        user_content: list[dict] = []
        for item in contents:
            if isinstance(item, str):
                user_content.append({"type": "text", "text": item})
            elif isinstance(item, dict) and item.get("type") == "image_base64":
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{item.get('media_type', 'image/png')};base64,{item['data']}"},
                })
            elif isinstance(item, bytes):
                b64 = base64.b64encode(item).decode()
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                })

        messages: list[dict] = [{"role": "user", "content": user_content}]
        payload: dict[str, Any] = {
            "model": kwargs.get("image_model", self.model),
            "messages": messages,
        }

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return self._extract_image_from_response(data)

    async def health_check(self) -> bool:
        """Verify API key by sending a minimal chat request."""
        try:
            await self.chat([{"role": "user", "content": "hi"}], max_tokens=1)
            return True
        except Exception:
            return False
