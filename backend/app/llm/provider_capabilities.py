from typing import Dict

PROVIDER_CAPABILITIES: Dict[str, Dict[str, bool]] = {
    "openai_compat": {
        "chat": True,
        "vision": True,
        "image_generation": True,  # depends on model but assume yes
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


def supports_image_generation(provider: str) -> bool:
    return PROVIDER_CAPABILITIES.get(provider, {}).get("image_generation", False)


def validate_provider_for_model_type(model_type: str, provider: str) -> None:
    if model_type == "image" and not supports_image_generation(provider):
        raise ValueError(f"Provider '{provider}' does not support image generation")


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
