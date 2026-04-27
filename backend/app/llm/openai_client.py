import base64
from typing import Any, Optional

import httpx

from app.llm.base_client import BaseLLMClient
from app.llm.provider_capabilities import (
    build_image_config,
    normalize_image_size,
    should_use_openai_images_api,
)


class OpenAICompatClient(BaseLLMClient):
    """OpenAI-compatible API client.

    Supports two image-generation modes while keeping base URL and model names
    fully configurable:
    - OpenAI Images API for gpt-image* / dall-e* models and compatible relays.
    - Chat Completions image output for OpenRouter/Nano Banana-style models.
    """

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
        message_content = self._build_chat_content(contents)

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
        image_model = kwargs.get("image_model", self.model)
        mode = kwargs.get("image_api_mode")
        if should_use_openai_images_api(self.base_url, image_model, mode):
            return await self._generate_image_via_images_api(prompt, image_model, **kwargs)
        return await self._generate_image_via_chat(prompt, image_model, **kwargs)

    async def generate_image_with_images(self, prompt: str, images: list[dict], **kwargs) -> Optional[bytes]:
        """Image-to-image generation via chat completions.

        This path is used for OpenRouter/Nano Banana-style multimodal image
        models. Native OpenAI Images API edit/variation support is intentionally
        not overloaded here because relay behavior varies widely.
        """
        user_content: list[dict] = [{"type": "text", "text": prompt}]
        for img in images:
            b64 = img.get("b64", "")
            media_type = img.get("media_type", "image/png")
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{b64}"},
            })

        image_model = kwargs.get("image_model", self.model)
        payload = self._build_image_chat_payload(
            model=image_model,
            messages=[{"role": "user", "content": user_content}],
            kwargs=kwargs,
        )

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return self._extract_image_from_response(resp.json())

    @staticmethod
    def _build_chat_content(contents: list[Any]) -> list[dict]:
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
        return message_content

    def _build_image_chat_payload(self, model: str, messages: list[dict], kwargs: dict) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            # Required by OpenRouter image output models. Compatible relays that
            # ignore unknown fields should safely ignore this.
            "modalities": ["image", "text"],
        }
        if kwargs.get("aspect_ratio") or kwargs.get("image_size"):
            payload["image_config"] = build_image_config(
                kwargs.get("aspect_ratio"),
                kwargs.get("image_size"),
            )
        return payload

    async def _generate_image_via_chat(self, prompt: str, image_model: str, **kwargs) -> Optional[bytes]:
        system_instruction = kwargs.get("system_instruction")
        messages: list[dict] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload = self._build_image_chat_payload(
            model=image_model,
            messages=messages,
            kwargs=kwargs,
        )

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return self._extract_image_from_response(resp.json())

    async def _generate_image_via_images_api(self, prompt: str, image_model: str, **kwargs) -> Optional[bytes]:
        payload: dict[str, Any] = {
            "model": image_model,
            "prompt": prompt,
            "n": kwargs.get("n", 1),
        }
        size = self._map_openai_image_size(kwargs.get("aspect_ratio"), kwargs.get("size"))
        if size:
            payload["size"] = size
        quality = kwargs.get("quality")
        if quality:
            payload["quality"] = quality

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self.base_url}/images/generations",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return await self._extract_image_from_images_response(data, client)

    @staticmethod
    def _map_openai_image_size(aspect_ratio: Optional[str], explicit_size: Optional[str]) -> Optional[str]:
        if explicit_size:
            return explicit_size
        ratio = (aspect_ratio or "").strip()
        if ratio in {"16:9", "3:2", "landscape"}:
            return "1536x1024"
        if ratio in {"9:16", "2:3", "portrait"}:
            return "1024x1536"
        return "1024x1024"

    @staticmethod
    async def _extract_image_from_images_response(data: dict, client: httpx.AsyncClient) -> Optional[bytes]:
        items = data.get("data") or []
        if not items:
            return None
        first = items[0]
        b64_json = first.get("b64_json")
        if b64_json:
            return base64.b64decode(b64_json)
        url = first.get("url")
        if url:
            resp = await client.get(url, timeout=180)
            resp.raise_for_status()
            return resp.content
        return None

    @staticmethod
    def _decode_data_url(url: str) -> Optional[bytes]:
        if not url.startswith("data:") or "," not in url:
            return None
        b64_str = url.split(",", 1)[1]
        return base64.b64decode(b64_str)

    @staticmethod
    def _extract_image_from_response(data: dict) -> Optional[bytes]:
        """Extract image bytes from chat-completions image responses.

        Handles OpenRouter's `message.images`, OpenAI-style content parts, and
        markdown/data-url fallbacks returned by third-party relays.
        """
        import re

        message = data.get("choices", [{}])[0].get("message", {})

        for image in message.get("images") or []:
            url = (image.get("image_url") or {}).get("url", "")
            decoded = OpenAICompatClient._decode_data_url(url)
            if decoded:
                return decoded

        content = message.get("content")
        if isinstance(content, list):
            for part in content:
                if part.get("type") == "image_url":
                    decoded = OpenAICompatClient._decode_data_url(
                        part.get("image_url", {}).get("url", "")
                    )
                    if decoded:
                        return decoded
                if part.get("type") == "image":
                    img_data = part.get("image", {})
                    if isinstance(img_data, dict) and "data" in img_data:
                        return base64.b64decode(img_data["data"])

        if isinstance(content, str) and content:
            match = re.search(r"data:image/[^;]+;base64,([A-Za-z0-9+/=\s]+)", content)
            if match:
                b64_str = match.group(1).replace("\n", "").replace(" ", "")
                return base64.b64decode(b64_str)

        return None

    async def generate_image_from_chat(self, contents: list, **kwargs) -> Optional[bytes]:
        user_content = self._build_chat_content(contents)
        image_model = kwargs.get("image_model", self.model)
        payload = self._build_image_chat_payload(
            model=image_model,
            messages=[{"role": "user", "content": user_content}],
            kwargs=kwargs,
        )

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return self._extract_image_from_response(resp.json())

    async def health_check(self) -> bool:
        """Verify API key by sending a minimal chat request."""
        try:
            await self.chat([{"role": "user", "content": "hi"}], max_tokens=1)
            return True
        except Exception:
            return False
