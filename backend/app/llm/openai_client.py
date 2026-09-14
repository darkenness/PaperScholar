import base64
import io
from PIL import Image
from typing import Any, Optional

import httpx

from app.llm.base_client import BaseLLMClient
from app.llm.remote_asset import download_image
from app.llm.image_validation import validate_image_bytes, InvalidModelOutputError
from app.llm.provider_capabilities import (
    build_image_config,
    resolve_openai_image_size,
    should_use_openai_images_api,
)


class OpenAICompatClient(BaseLLMClient):
    """OpenAI-compatible API client.

    Image generation supports two explicitly configurable modes:
    - ``image_api_mode='chat'`` for OpenRouter and chat-completions relays that
      return image data via ``message.images`` or content parts.
    - ``image_api_mode='images'`` for OpenAI Images API compatible endpoints such
      as GPT Image and compatible third-party relays.

    ``base_url`` and ``model`` are intentionally passed through unchanged so the
    admin UI can freely configure third-party relay URLs and model names.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "gemini-2.5-pro",
        image_api_mode: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(api_key=api_key, base_url=base_url, model=model, **kwargs)
        self.base_url = (self.base_url or "https://openrouter.ai/api/v1").strip().rstrip("/")
        self.image_api_mode = image_api_mode
        self.options = kwargs.get("api_options") or {}
        self.timeout = self.options.get("timeout_seconds",180)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def chat(self, messages: list[dict], temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload[self.options.get("token_parameter","max_tokens")] = max_tokens

        if not self.options.get("send_temperature", True):
            payload.pop("temperature",None)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return self._extract_text(data)

    async def chat_with_images(self, contents: list[Any], temperature: float = 0.7, max_tokens: Optional[int] = None, system_prompt: Optional[str] = None, **kwargs) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": self._build_chat_content(contents)})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload[self.options.get("token_parameter","max_tokens")] = max_tokens

        if not self.options.get("send_temperature", True):
            payload.pop("temperature",None)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return self._extract_text(data)

    async def generate_image(self, prompt: str, **kwargs) -> Optional[bytes]:
        image_model = kwargs.get("image_model") or self.model
        mode = kwargs.get("image_api_mode") or self.image_api_mode
        image_kwargs = dict(kwargs)
        image_kwargs.pop("image_model", None)
        image_kwargs.pop("image_api_mode", None)
        if should_use_openai_images_api(self.base_url, image_model, mode):
            return await self._generate_image_via_images_api(prompt, image_model, **image_kwargs)
        return await self._generate_image_via_chat(prompt, image_model, **image_kwargs)

    async def generate_image_with_images(self, prompt: str, images: list[dict], **kwargs) -> Optional[bytes]:
        """Keep source images and use the explicitly selected protocol."""
        if not images:
            raise ValueError("Image editing requires at least one source image")
        image_model = kwargs.get("image_model") or self.model
        mode = kwargs.get("image_api_mode") or self.image_api_mode
        if should_use_openai_images_api(self.base_url, image_model, mode):
            options = {k: v for k, v in kwargs.items() if k not in {"image_model", "image_api_mode"}}
            return await self._edit_image_via_images_api(prompt, images, image_model, **options)
        user_content: list[dict] = [{"type": "text", "text": prompt}]
        for img in images:
            b64 = img.get("b64", "")
            media_type = img.get("media_type", "image/png")
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{b64}"},
            })

        image_model = kwargs.get("image_model") or self.model
        payload = self._build_image_chat_payload(
            model=image_model,
            messages=([{"role":"system","content":kwargs["system_instruction"]}] if kwargs.get("system_instruction") else []) + [{"role":"user","content":user_content}],
            kwargs=kwargs,
        )

        if not self.options.get("send_temperature", True):
            payload.pop("temperature",None)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return await self._extract_chat_image(resp.json())

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
        if not self.options.get("send_modalities",True):
            payload.pop("modalities",None)
        if self.options.get("send_image_config",True) and (kwargs.get("aspect_ratio") or kwargs.get("image_size")):
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

        payload = self._build_image_chat_payload(model=image_model, messages=messages, kwargs=kwargs)

        if not self.options.get("send_temperature", True):
            payload.pop("temperature",None)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return await self._extract_chat_image(resp.json())

    async def _generate_image_via_images_api(self, prompt: str, image_model: str, **kwargs) -> Optional[bytes]:
        if kwargs.get("system_instruction"):
            prompt = f"{kwargs['system_instruction']}\n\n{prompt}"
        payload: dict[str, Any] = {
            "model": image_model,
            "prompt": prompt,
            "n": kwargs.get("n", 1),
        }
        size = resolve_openai_image_size(
            image_model,
            kwargs.get("aspect_ratio"),
            kwargs.get("image_size"),
            kwargs.get("size"),
        )
        if size:
            payload["size"] = size
        quality = kwargs.get("quality") or self.options.get("image_quality")
        if quality:
            payload["quality"] = quality

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/images/generations",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return await self._extract_image_from_images_response(resp.json(), client)

    async def _edit_image_via_images_api(self, prompt: str, images: list[dict], image_model: str, **kwargs) -> Optional[bytes]:
        """Use multipart /images/edits; never silently discard image inputs."""
        from app.llm.image_validation import validate_image_bytes
        if kwargs.get("system_instruction"):
            prompt = f"{kwargs['system_instruction']}\n\n{prompt}"
        form = {"model": image_model, "prompt": prompt, "n": str(kwargs.get("n", 1))}
        size = resolve_openai_image_size(image_model, kwargs.get("aspect_ratio"), kwargs.get("image_size"), kwargs.get("size"))
        if size:
            form["size"] = size
        quality = kwargs.get("quality") or self.options.get("image_quality")
        if quality:
            form["quality"] = str(quality)
        files = []
        for index, item in enumerate(images):
            value = item.get("b64")
            raw = base64.b64decode(value, validate=True) if isinstance(value, str) else value
            validate_image_bytes(raw)
            # Derive MIME from bytes, not from a possibly stale PNG label.
            with Image.open(io.BytesIO(raw)) as image:
                fmt = image.format
            if fmt not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("Images API editing requires PNG, JPEG, or WEBP input")
            mime = Image.MIME[fmt]
            field = "image" if len(images) == 1 else "image[]"
            files.append((field, (f"source_{index}.{fmt.lower()}", raw, mime)))
        headers = {k: v for k, v in self._headers().items() if k.lower() != "content-type"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/images/edits", headers=headers, data=form, files=files)
            response.raise_for_status()
            return await self._extract_image_from_images_response(response.json(), client)

    async def _extract_image_from_images_response(self, data, client=None):
        for item in data.get("data") or []:
            if item.get("b64_json"):
                return validate_image_bytes(base64.b64decode(item["b64_json"]))
            if item.get("url"):
                return await download_image(item["url"], trusted_origin=self.base_url, timeout=self.timeout)
        return None

    async def _extract_chat_image(self, data):
        raw=self._extract_image_from_response(data)
        if raw:
            return validate_image_bytes(raw)
        import re
        message=((data.get("choices") or [{}])[0].get("message") or {})
        urls=[]
        for item in message.get("images") or []:
            value=item.get("image_url") or item.get("url")
            urls.append(value.get("url") if isinstance(value,dict) else value)
        content=message.get("content")
        if isinstance(content,list):
            for item in content:
                if isinstance(item,dict) and item.get("type") in {"image_url","image"}:
                    value=item.get("image_url") or item.get("url") or item.get("image")
                    urls.append(value.get("url") if isinstance(value,dict) else value)
        elif isinstance(content,str):
            urls.extend(re.findall(r"!\[[^\]]*\]\((https?://[^\s)]+)\)",content))
        for url in urls:
            if isinstance(url,str) and url.startswith(("http://","https://")):
                return await download_image(url,trusted_origin=self.base_url,timeout=self.timeout)
        return None

    @staticmethod
    def _extract_text(data):
        message=((data.get("choices") or [{}])[0].get("message") or {})
        content=message.get("content")
        if isinstance(content,str):
            return content
        if isinstance(content,list):
            return "\n".join(x["text"] for x in content if isinstance(x,dict) and isinstance(x.get("text"),str))
        raise InvalidModelOutputError("上游未返回有效文本，请核对模型与接口协议")

    @staticmethod
    def _decode_data_url(url: str) -> Optional[bytes]:
        if not isinstance(url,str) or not url.startswith("data:image/") or "," not in url:
            return None
        return base64.b64decode(url.split(",", 1)[1])

    @staticmethod
    def _extract_image_from_response(data: dict) -> Optional[bytes]:
        """Extract image bytes from chat-completions image responses."""
        import re

        message = ((data.get("choices") or [{}])[0].get("message") or {})

        # OpenRouter image output format: choices[0].message.images[].image_url.url
        for image in message.get("images") or []:
            value = image.get("image_url") or {}
            url = value.get("url", "") if isinstance(value,dict) else value
            decoded = OpenAICompatClient._decode_data_url(url)
            if decoded:
                return decoded

        content = message.get("content")
        if isinstance(content, list):
            for part in content:
                if not isinstance(part,dict):
                    continue
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
        image_model = kwargs.get("image_model") or self.model
        mode = kwargs.get("image_api_mode") or self.image_api_mode
        if should_use_openai_images_api(self.base_url, image_model, mode):
            texts, images = [], []
            for item in contents:
                if isinstance(item, str):
                    texts.append(item)
                elif isinstance(item, dict) and item.get("type") == "image_base64":
                    images.append({"b64": item["data"], "media_type": item.get("media_type", "image/png")})
                elif isinstance(item, bytes):
                    images.append({"b64": item})
                else:
                    raise ValueError("Unsupported multimodal content; refusing to discard it")
            prompt = "\n".join(texts)
            if images:
                return await self.generate_image_with_images(prompt, images, **kwargs)
            return await self.generate_image(prompt, **kwargs)
        payload = self._build_image_chat_payload(
            model=image_model,
            messages=[{"role": "user", "content": self._build_chat_content(contents)}],
            kwargs=kwargs,
        )

        if not self.options.get("send_temperature", True):
            payload.pop("temperature",None)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return await self._extract_chat_image(resp.json())

    async def health_check(self) -> bool:
        """Verify API key by sending a minimal chat request."""
        try:
            await self.chat([{"role": "user", "content": "hi"}], max_tokens=1)
            return True
        except Exception:
            return False
