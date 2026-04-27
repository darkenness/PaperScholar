from typing import Dict

PROVIDER_CAPABILITIES: Dict[str, Dict[str, bool]] = {
    "openai_compat": {
        "chat": True,
        "vision": True,
        "image_generation": True,  # depends on the selected model and upstream API
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


def supports_image_generation(provider: str) -> bool:
    return PROVIDER_CAPABILITIES.get(provider, {}).get("image_generation", False)


def validate_provider_for_model_type(model_type: str, provider: str) -> None:
    if model_type == "image" and not supports_image_generation(provider):
        raise ValueError(f"Provider '{provider}' does not support image generation")


def normalize_image_model(provider: str, model: str | None) -> str:
    """Normalize only known convenience aliases while preserving custom model names.

    OpenAI-compatible providers intentionally pass model names through unchanged so
    OpenRouter and third-party relay names remain fully configurable.
    """
    model_name = (model or "").strip()
    if provider == "gemini":
        return GEMINI_IMAGE_MODEL_ALIASES.get(model_name, model_name or "gemini-2.5-flash-image")
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


def should_use_openai_images_api(base_url: str | None, model: str, mode: str | None = None) -> bool:
    """Choose the OpenAI Images endpoint for GPT Image/DALL-E style models.

    OpenRouter image models use chat completions with modalities, so keep them on
    the chat path even when their model id contains provider prefixes.
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
