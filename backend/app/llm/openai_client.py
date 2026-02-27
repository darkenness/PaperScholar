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
        # Map aspect_ratio to size if no explicit size given
        size = kwargs.get("size")
        if not size:
            aspect_ratio = kwargs.get("aspect_ratio", "1:1")
            size_map = {
                "1:1": "1024x1024",
                "16:9": "1792x1024",
                "4:3": "1344x1024",
                "3:2": "1536x1024",
                "21:9": "1792x768",
                "9:16": "1024x1792",
                "3:4": "1024x1344",
            }
            size = size_map.get(aspect_ratio, "1024x1024")

        payload = {
            "model": kwargs.get("image_model", self.model),
            "prompt": prompt,
            "n": 1,
            "size": size,
            "response_format": "b64_json",
        }

        max_attempts = kwargs.get("max_attempts", 3)
        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient(timeout=180) as client:
                    resp = await client.post(
                        f"{self.base_url}/images/generations",
                        headers=self._headers(),
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    item = data["data"][0]
                    b64_data = item.get("b64_json")
                    url_data = item.get("url")

                    if b64_data:
                        return base64.b64decode(b64_data)
                    elif url_data:
                        img_resp = await client.get(url_data)
                        img_resp.raise_for_status()
                        return img_resp.content
            except Exception as e:
                if attempt < max_attempts - 1:
                    import asyncio
                    await asyncio.sleep(min(5 * (2 ** attempt), 30))
                else:
                    raise
        return None

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False
