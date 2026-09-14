import base64
from typing import Any, Optional

from app.llm.base_client import BaseLLMClient
from app.llm.provider_capabilities import normalize_image_model, normalize_image_size


class GeminiNativeClient(BaseLLMClient):
    """Google Gemini native API client using google-genai SDK."""

    def __init__(self, api_key: str, base_url: Optional[str] = None, model: str = "gemini-2.5-pro", **kwargs):
        super().__init__(api_key=api_key, base_url=base_url, model=model, **kwargs)
        from google import genai
        self._genai_client = genai.Client(api_key=api_key)

    def _image_model(self, override: Optional[str] = None) -> str:
        return normalize_image_model("gemini", override or self.model)

    async def chat(self, messages: list[dict], temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs) -> str:
        from google.genai import types

        contents = []
        for msg in messages:
            role = "user" if msg["role"] in ("user", "system") else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens or 50000,
        )

        response = await self._genai_client.aio.models.generate_content(
            model=self.model, contents=contents, config=config,
        )

        if response.candidates and response.candidates[0].content.parts:
            return response.candidates[0].content.parts[0].text
        return ""

    async def chat_with_images(self, contents: list[Any], temperature: float = 0.7, max_tokens: Optional[int] = None, system_prompt: Optional[str] = None, **kwargs) -> str:
        from google.genai import types

        parts = []
        for item in contents:
            if isinstance(item, str):
                parts.append(types.Part(text=item))
            elif isinstance(item, dict) and item.get("type") == "image_base64":
                parts.append(types.Part(inline_data=types.Blob(
                    mime_type=item.get("media_type", "image/png"),
                    data=base64.b64decode(item["data"]),
                )))
            elif isinstance(item, bytes):
                parts.append(types.Part(inline_data=types.Blob(
                    mime_type="image/png", data=item,
                )))

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens or 50000,
            system_instruction=system_prompt if system_prompt else None,
        )

        response = await self._genai_client.aio.models.generate_content(
            model=self.model,
            contents=[types.Content(role="user", parts=parts)],
            config=config,
        )

        if response.candidates and response.candidates[0].content.parts:
            return response.candidates[0].content.parts[0].text
        return ""

    async def generate_image(self, prompt: str, **kwargs) -> Optional[bytes]:
        from google.genai import types

        image_model = self._image_model(kwargs.get("image_model"))
        aspect_ratio = kwargs.get("aspect_ratio", "1:1")
        image_size = normalize_image_size(kwargs.get("image_size"))
        system_instruction = kwargs.get("system_instruction")

        image_config_kwargs = {"aspect_ratio": aspect_ratio, "image_size": image_size}

        config = types.GenerateContentConfig(
            temperature=1.0,
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(**image_config_kwargs),
            system_instruction=system_instruction if system_instruction else None,
        )

        response = await self._genai_client.aio.models.generate_content(
            model=image_model,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=config,
        )

        return self._extract_inline_image(response)

    async def generate_image_with_images(self, prompt: str, images: list[dict], **kwargs) -> Optional[bytes]:
        """Generate an image using Gemini with input images (image-to-image)."""
        from google.genai import types

        image_model = self._image_model(kwargs.get("image_model"))
        aspect_ratio = kwargs.get("aspect_ratio", "1:1")
        image_size = normalize_image_size(kwargs.get("image_size"))

        parts = [types.Part(text=prompt)]
        for img in images:
            img_data = base64.b64decode(img["b64"]) if isinstance(img["b64"], str) else img["b64"]
            parts.append(types.Part(inline_data=types.Blob(
                mime_type=img.get("media_type", "image/png"),
                data=img_data,
            )))

        config = types.GenerateContentConfig(
            temperature=1.0,
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio, image_size=image_size),
        )

        response = await self._genai_client.aio.models.generate_content(
            model=image_model,
            contents=[types.Content(role="user", parts=parts)],
            config=config,
        )

        return self._extract_inline_image(response)

    async def generate_image_from_chat(self, contents: list, **kwargs) -> Optional[bytes]:
        """Generate an image from multimodal content using Gemini image models."""
        from google.genai import types

        image_model = self._image_model(kwargs.get("image_model"))
        aspect_ratio = kwargs.get("aspect_ratio", "1:1")
        image_size = normalize_image_size(kwargs.get("image_size"))

        parts = []
        for item in contents:
            if isinstance(item, str):
                parts.append(types.Part(text=item))
            elif isinstance(item, dict) and item.get("type") == "image_base64":
                parts.append(types.Part(inline_data=types.Blob(
                    mime_type=item.get("media_type", "image/png"),
                    data=base64.b64decode(item["data"]),
                )))
            elif isinstance(item, bytes):
                parts.append(types.Part(inline_data=types.Blob(
                    mime_type="image/png", data=item,
                )))

        config = types.GenerateContentConfig(
            temperature=1.0,
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio, image_size=image_size),
        )

        response = await self._genai_client.aio.models.generate_content(
            model=image_model,
            contents=[types.Content(role="user", parts=parts)],
            config=config,
        )

        return self._extract_inline_image(response)

    @staticmethod
    def _extract_inline_image(response) -> Optional[bytes]:
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    return part.inline_data.data
        return None

    async def health_check(self) -> bool:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}"
                )
                return resp.status_code == 200
        except Exception:
            return False
