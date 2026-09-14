import asyncio
import base64
from urllib.parse import urlsplit, urlunsplit
from typing import Any, Optional

from app.llm.base_client import BaseLLMClient
from app.llm.provider_capabilities import normalize_image_model, normalize_image_size


class GeminiNativeClient(BaseLLMClient):
    """Google Gemini native API client using google-genai SDK."""

    def __init__(self, api_key: str, base_url: Optional[str] = None, model: str = "gemini-2.5-pro", **kwargs):
        super().__init__(api_key=api_key, base_url=base_url, model=model, **kwargs)
        from google import genai
        options = {}
        if base_url and base_url.strip():
            url = urlsplit(base_url.strip())
            if url.scheme not in {"http", "https"} or not url.netloc or url.query or url.fragment or url.username:
                raise ValueError("Gemini base_url must be an HTTP(S) endpoint without credentials, query, or fragment")
            path = url.path.rstrip("/")
            version = path.rsplit("/", 1)[-1]
            if version in {"v1", "v1beta", "v1alpha"}:
                path = path.rsplit("/", 1)[0]
                options["api_version"] = version
            options["base_url"] = urlunsplit((url.scheme, url.netloc, path, "", ""))
        self._genai_client = genai.Client(api_key=api_key, **({"http_options": options} if options else {}))

    def _image_model(self, override: Optional[str] = None) -> str:
        return normalize_image_model("gemini", override or self.model)

    async def chat(self, messages: list[dict], temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs) -> str:
        from google.genai import types

        contents = []
        system_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_messages.append(msg["content"])
                continue
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens or 50000,
            system_instruction="\n\n".join(system_messages) or None,
        )

        response = await self._genai_client.aio.models.generate_content(
            model=self.model, contents=contents, config=config,
        )

        return self._extract_final_text(response)

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

        return self._extract_final_text(response)

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
            system_instruction=kwargs.get("system_instruction"),
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
            system_instruction=kwargs.get("system_instruction"),
        )

        response = await self._genai_client.aio.models.generate_content(
            model=image_model,
            contents=[types.Content(role="user", parts=parts)],
            config=config,
        )

        return self._extract_inline_image(response)

    @staticmethod
    def _extract_inline_image(response) -> Optional[bytes]:
        candidates = getattr(response, "candidates", None) or []
        content = getattr(candidates[0], "content", None) if candidates else None
        for part in getattr(content, "parts", None) or []:
            blob = getattr(part, "inline_data", None)
            if not getattr(part, "thought", False) and blob and (getattr(blob, "mime_type", "") or "").startswith("image/"):
                return blob.data
        return None

    @staticmethod
    def _extract_final_text(response) -> str:
        candidates = getattr(response, "candidates", None) or []
        content = getattr(candidates[0], "content", None) if candidates else None
        return "".join(
            part.text for part in (getattr(content, "parts", None) or [])
            if not getattr(part, "thought", False) and isinstance(getattr(part, "text", None), str)
        )

    async def health_check(self) -> bool:
        """Probe the configured model through the same SDK/endpoint as real calls.

        This is a small, potentially billable text request, not an edit/vision test.
        """
        try:
            text = await asyncio.wait_for(
                self.chat([{"role": "user", "content": "Reply only OK."}], max_tokens=64),
                timeout=30,
            )
            return bool(text and text.strip())
        except Exception:
            return False
