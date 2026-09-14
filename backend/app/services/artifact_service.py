"""Atomic artifacts with original encoded bytes and actual file extensions."""
import base64
import io
import os
import uuid
from pathlib import Path
from PIL import Image
from app.config import settings
from app.llm.image_validation import validate_image_bytes


def safe_artifact_path(relative_path):
    root=Path(settings.UPLOAD_DIR).resolve()
    path=(root/relative_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Invalid artifact path')
    return path


def write_image(task_id,candidate_index,raw,*,stem='image'):
    validate_image_bytes(raw)
    with Image.open(io.BytesIO(raw)) as image:
        ext={'JPEG':'jpg','PNG':'png','WEBP':'webp','GIF':'gif'}.get(image.format)
        if not ext:
            raise ValueError('Unsupported image format')
    stem=''.join(c for c in stem if c.isalnum() or c in '-_')[:60] or 'image'
    rel=f'results/{uuid.UUID(str(task_id))}/candidate_{int(candidate_index)}/{stem}_{uuid.uuid4().hex[:12]}.{ext}'
    path=safe_artifact_path(rel)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_bytes(raw)
    os.replace(tmp,path)
    return rel


def read_image(relative_path):
    return base64.b64encode(validate_image_bytes(safe_artifact_path(relative_path).read_bytes())).decode()
