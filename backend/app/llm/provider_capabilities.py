from typing import Dict

PROVIDER_CAPABILITIES: Dict[str, Dict[str, bool]] = {
    "openai_compat": {
        "chat": True,
        "vision": True,
        "image_generation": True,  # depends on the selected model and upstream API
    },
    "openai_images": {
        "chat": False,
        "vision": False,
        "image_generation": True,  # OpenAI Images API or compatible relay
    },
    "gemini": {
        "chat": True,
        "vision": True,
        "image_generation": True,
    },
    "anthropic": {
        "chat": True,
        "vision": True,
        "image_generation": False,
    },
}

GEMINI_IMAGE_MODEL_ALIASES = {
    "nano-banana": "gemini-2.5-flash-image",
    "nano-banana-pro": "gemini-3-pro-image-preview",
    "gemini-2.5-flash-preview-image": "gemini-2.5-flash-image",
}

GPT_IMAGE_FIXED_SIZE_OPTIONS = ["1024x1024", "1536x1024", "1024x1536"]

OPENAI_IMAGE_SIZE_OPTIONS = {
    "gpt-image-1": GPT_IMAGE_FIXED_SIZE_OPTIONS,
    "gpt-image-1.5": GPT_IMAGE_FIXED_SIZE_OPTIONS,
    "gpt-image-1-mini": GPT_IMAGE_FIXED_SIZE_OPTIONS,
}


def supports_chat(provider: str) -> bool:
    return PROVIDER_CAPABILITIES.get(provider, {}).get("chat", False)


def supports_image_generation(provider: str) -> bool:
    return PROVIDER_CAPABILITIES.get(provider, {}).get("image_generation", False)


def validate_provider_for_model_type(model_type: str, provider: str) -> None:
    if model_type == "chat" and not supports_chat(provider):
        raise ValueError(f"Provider '{provider}' does not support chat completions")
    if model_type == "image" and not supports_image_generation(provider):
        raise ValueError(f"Provider '{provider}' does not support image generation")


def normalize_image_model(provider: str, model: str | None) -> str:
    """Normalize only known convenience aliases while preserving custom names.

    OpenAI-compatible providers intentionally pass model names through unchanged
    so OpenRouter and third-party relay model ids remain fully configurable.
    """
    model_name = (model or "").strip()
    if provider == "gemini":
        return GEMINI_IMAGE_MODEL_ALIASES.get(model_name, model_name or "gemini-2.5-flash-image")
    if provider == "openai_images":
        return model_name or "gpt-image-1"
    return model_name


def normalize_image_size(value: str | None) -> str:
    if not value:
        return "1K"
    v = value.upper()
    if v not in {"1K", "2K", "4K"}:
        return "1K"
    return v


def build_image_config(aspect_ratio: str | None, image_size: str | None) -> dict:
    return {
        "aspect_ratio": aspect_ratio or "1:1",
        "image_size": normalize_image_size(image_size),
    }


def image_size_options(provider: str, model: str | None) -> list[str]:
    if provider != "openai_images":
        return []
    return OPENAI_IMAGE_SIZE_OPTIONS.get((model or "").strip().lower(), [])


def image_size_mode(provider: str, model: str | None) -> str:
    if provider == "openai_images":
        return "fixed" if image_size_options(provider, model) else "custom"
    return "quality"


def image_model_capabilities(provider: str, model: str | None) -> dict:
    return {
        "size_mode": image_size_mode(provider, model),
        "size_options": image_size_options(provider, model),
    }


def resolve_openai_image_size(
    model: str,
    aspect_ratio: str | None,
    image_size: str | None,
    explicit_size: str | None = None,
) -> str:
    options = OPENAI_IMAGE_SIZE_OPTIONS.get((model or "").strip().lower(), [])
    requested = (explicit_size or image_size or "").strip()
    if options:
        if requested in options:
            return requested
        ratio = (aspect_ratio or "").strip()
        if ratio in {"16:9", "3:2", "landscape"}:
            return "1536x1024"
        if ratio in {"9:16", "2:3", "3:4", "portrait"}:
            return "1024x1536"
        return "1024x1024"

    if requested == "auto":
        return "auto"
    if requested and "x" in requested:
        import re
        if not re.fullmatch(r"[1-9][0-9]{1,4}x[1-9][0-9]{1,4}",requested):
            raise ValueError("尺寸必须为 WIDTHxHEIGHT 或 auto")
        return requested
    ratio = (aspect_ratio or "").strip()
    if ratio in {"16:9", "3:2", "landscape"}:
        return "1536x1024"
    if ratio in {"9:16", "2:3", "3:4", "portrait"}:
        return "1024x1536"
    return "1024x1024"


def should_use_openai_images_api(base_url: str | None, model: str, mode: str | None = None) -> bool:
    """Choose the OpenAI Images endpoint for GPT Image/DALL-E style models.

    OpenRouter image models use chat completions with modalities, so keep them on
    the chat path even when their model id contains provider prefixes. Passing
    mode="images" forces the Images API, which is used by the explicit
    openai_images provider and compatible relays.
    """
    if mode == "images":
        return True
    if mode == "chat":
        return False

    normalized_base = (base_url or "").lower()
    normalized_model = (model or "").lower()
    if "openrouter.ai" in normalized_base:
        return False
    return normalized_model.startswith("gpt-image") or normalized_model.startswith("dall-e")
