"""Validate provider outputs without rewriting or recompressing scientific figures."""
import io
from PIL import Image

class InvalidModelOutputError(RuntimeError):
    """An upstream request returned no usable output."""


def validate_image_bytes(value: bytes) -> bytes:
    if not isinstance(value, bytes) or not value:
        raise InvalidModelOutputError("Image provider returned no image bytes")
    if len(value) > 64 * 1024 * 1024:
        raise InvalidModelOutputError("Image response exceeds the 64 MiB safety limit")
    try:
        with Image.open(io.BytesIO(value)) as img:
            if img.width * img.height > 50_000_000:
                raise ValueError("image pixel limit exceeded")
            img.verify()
        with Image.open(io.BytesIO(value)) as img:
            img.load()
    except Exception as exc:
        raise InvalidModelOutputError("Provider response is not a decodable image") from exc
    return value
