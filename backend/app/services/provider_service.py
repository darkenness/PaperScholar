"""Shared personal/admin configuration and capability-specific probes."""
import asyncio
import base64
import io
import time
from datetime import datetime, timezone

import httpx
from PIL import Image
from app.core.security import decrypt_api_key, encrypt_api_key, mask_api_key
from app.llm.client_factory import LLMClientFactory
from app.llm.endpoint_config import normalize_base_url, endpoint_preview, effective_model
from app.llm.image_validation import validate_image_bytes
from app.llm.load_balancer import LoadBalancer
from app.llm.provider_capabilities import validate_provider_for_model_type
from app.schemas.api_key import ApiKeyResponse

CAPABILITIES = {"chat", "vision", "image_generation", "image_edit"}


def validate_model_name(provider, model_name):
    if provider == "openai_compat" and not (model_name or "").strip():
        raise ValueError("openai_compat 必须提供模型 ID")


def serialize_config(cfg):
    try:
        preview = mask_api_key(decrypt_api_key(cfg.api_key_encrypted))
    except Exception:
        preview = "***"
    try:
        endpoints = endpoint_preview(cfg.provider, cfg.base_url)
    except ValueError:
        endpoints = {}
    return ApiKeyResponse(
        id=cfg.id, model_type=cfg.model_type, provider=cfg.provider,
        base_url=cfg.base_url, api_key_preview=preview, model_name=cfg.model_name,
        display_name=cfg.display_name, api_options=cfg.api_options or {},
        capability_status=cfg.capability_status or {}, endpoints=endpoints,
        is_verified=cfg.is_verified, is_enabled=cfg.is_enabled, priority=cfg.priority,
        last_verified_at=cfg.last_verified_at, last_error=cfg.last_error, created_at=cfg.created_at,
    )


def update_config_fields(cfg, req, *, system=False):
    old = (cfg.provider, cfg.base_url, cfg.model_name, cfg.api_key_encrypted, cfg.api_options)
    fields = req.model_fields_set
    provider = req.provider if "provider" in fields and req.provider is not None else cfg.provider
    model_name = req.model_name if "model_name" in fields else cfg.model_name
    if provider != cfg.provider and "base_url" not in fields:
        raise ValueError("切换 provider 时必须同时提供 base_url")
    validate_model_name(provider, model_name)
    base_url = normalize_base_url(req.base_url if "base_url" in fields else cfg.base_url, provider)
    for name in ("provider", "display_name", "model_name", "is_enabled"):
        if name in fields and getattr(req, name) is not None:
            setattr(cfg, name, getattr(req, name))
    cfg.provider = provider
    cfg.base_url = base_url
    if req.api_key is not None:
        if not req.api_key.strip():
            raise ValueError("API Key 不能为空")
        cfg.api_key_encrypted = encrypt_api_key(req.api_key.strip())
    if req.api_options is not None:
        cfg.api_options = req.api_options.model_dump()
    if not system and req.priority is not None:
        cfg.priority = req.priority
    validate_provider_for_model_type(cfg.model_type, cfg.provider)
    if old != (cfg.provider, cfg.base_url, cfg.model_name, cfg.api_key_encrypted, cfg.api_options):
        cfg.is_verified = False
        cfg.capability_status = {}
        cfg.last_error = None
        cfg.last_verified_at = None


def _probe_image():
    out=io.BytesIO()
    Image.new("RGB", (32,32), "red").save(out, format="PNG")
    return out.getvalue()


async def probe_config(cfg, capability="default"):
    capability = ("image_generation" if cfg.model_type == "image" else "chat") if capability == "default" else capability
    if capability not in CAPABILITIES:
        raise ValueError("未知测试能力")
    validate_model_name(cfg.provider, cfg.model_name)
    raw_key = decrypt_api_key(cfg.api_key_encrypted)
    started = time.monotonic()
    status, message, error_code = "passed", "测试通过", None
    try:
        client=LLMClientFactory.create(provider=cfg.provider, api_key=raw_key, base_url=cfg.base_url,
            model=effective_model(cfg.provider, cfg.model_type, cfg.model_name), api_options=cfg.api_options or {})
        async with asyncio.timeout((cfg.api_options or {}).get("timeout_seconds",180)):
            if capability == "chat":
                result=await client.chat([{"role":"user","content":"Reply OK."}], max_tokens=32)
            elif capability == "vision":
                result=await client.chat_with_images(contents=["Name the dominant color.", {"type":"image_base64","data":base64.b64encode(_probe_image()).decode(),"media_type":"image/png"}], max_tokens=64)
            elif capability == "image_generation":
                result=await client.generate_image(prompt="A black circle on white.", aspect_ratio="1:1", image_size="1K")
            else:
                result=await client.generate_image_with_images(prompt="Change the red square to blue. Preserve composition.", images=[{"b64":base64.b64encode(_probe_image()).decode(),"media_type":"image/png"}], aspect_ratio="1:1", image_size="1K")
            if capability.startswith("image_"):
                await asyncio.to_thread(validate_image_bytes, result)
            elif not isinstance(result,str) or not result.strip():
                raise ValueError("上游没有返回有效文本")
    except Exception as exc:
        status="failed"
        error_code=LoadBalancer._status_code(exc)
        message=str(exc) or type(exc).__name__
        if isinstance(exc,httpx.HTTPStatusError):
            try:
                detail=exc.response.json().get("error",{})
                message=f"HTTP {exc.response.status_code}: " + str(detail.get("message",detail) if isinstance(detail,dict) else detail)
            except Exception:
                message=f"HTTP {exc.response.status_code}: 接口请求失败"
        message=message.replace(raw_key,"***")[:1500]
    checked=datetime.now(timezone.utc)
    latency=int((time.monotonic()-started)*1000)
    checks=dict(cfg.capability_status or {})
    checks[capability]={"status":status,"checked_at":checked.isoformat(),"latency_ms":latency,"error_code":error_code,"message":message}
    cfg.capability_status=checks
    if capability == ("image_generation" if cfg.model_type == "image" else "chat"):
        cfg.is_verified=status=="passed"
        cfg.last_verified_at=checked
        cfg.last_error=None if cfg.is_verified else message
    return {"is_verified":cfg.is_verified,"capability":capability,"status":status,"message":message,"latency_ms":latency,"error_code":error_code,"capability_status":checks}


async def discover_models(cfg):
    root=normalize_base_url(cfg.base_url,cfg.provider)
    key=decrypt_api_key(cfg.api_key_encrypted)
    if cfg.provider in {"openai_compat","openai_images"}:
        url,headers=root+"/models",{"Authorization":f"Bearer {key}"}
    elif cfg.provider=="gemini":
        suffix="/models" if root.endswith(("/v1", "/v1beta", "/v1alpha")) else "/v1beta/models"
        url,headers=root+suffix,{"x-goog-api-key":key}
    else:
        url,headers=root+"/v1/models",{"x-api-key":key,"anthropic-version":"2023-06-01"}
    async with httpx.AsyncClient(timeout=20) as client:
        res=await client.get(url,headers=headers)
        if res.status_code in {404,405}:
            return {"models":[],"message":"此服务不提供模型列表，请手动输入模型 ID"}
        res.raise_for_status()
        data=res.json()
    items=data.get("data") or data.get("models") or []
    ids=sorted({str(item.get("id") or item.get("name","")).removeprefix("models/") for item in items if isinstance(item,dict)})
    return {"models":[m for m in ids if m],"message":"模型列表仅供选择，仍需单独测试所需能力。"}
