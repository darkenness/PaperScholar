from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.database import get_db
from app.core.security import encrypt_api_key, decrypt_api_key, mask_api_key
from app.llm.provider_capabilities import validate_provider_for_model_type
from app.models.api_key import ApiApplication, ApiKeyConfig
from app.models.generation import GenerationTask
from app.models.system import Announcement, ApiUsageLog, SystemConfig
from app.models.user import User
from app.schemas.api_key import ApiApplicationResponse, ApiApplicationReview
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/admin", tags=["管理后台"])


class SystemKeyCreate(BaseModel):
    model_type: str
    provider: str
    api_key: str
    base_url: Optional[str] = None
    model_name: Optional[str] = None


class SystemKeyUpdate(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None


# ── Users ──

@router.get("/users")
async def list_users(
    page: int = 1,
    page_size: int = 20,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * page_size
    total_result = await db.execute(select(func.count(User.id)))
    total = total_result.scalar()

    result = await db.execute(
        select(User).order_by(User.id.desc()).offset(offset).limit(page_size)
    )
    users = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            UserResponse(
                id=u.id, username=u.username, email=u.email, role=u.role,
                is_active=u.is_active, system_api_approved=u.system_api_approved,
                created_at=u.created_at.isoformat(),
            )
            for u in users
        ],
    }


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    role: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="角色只能是 user 或 admin")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.role = role
    await db.commit()
    return {"message": f"用户 {user.username} 角色已更新为 {role}"}


@router.put("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="不能禁用自己")

    user.is_active = not user.is_active
    await db.commit()
    return {"message": f"用户 {user.username} 已{'启用' if user.is_active else '禁用'}"}


# ── API Applications Review ──

@router.get("/applications")
async def list_applications(
    status_filter: str = "pending",
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(ApiApplication).order_by(ApiApplication.created_at.desc())
    if status_filter != "all":
        query = query.where(ApiApplication.status == status_filter)

    result = await db.execute(query)
    apps = result.scalars().all()

    items = []
    for a in apps:
        user_result = await db.execute(select(User).where(User.id == a.user_id))
        user = user_result.scalar_one_or_none()
        items.append({
            "id": a.id,
            "user_id": a.user_id,
            "username": user.username if user else "unknown",
            "email": user.email if user else "unknown",
            "reason": a.reason,
            "status": a.status,
            "review_comment": a.review_comment,
            "created_at": a.created_at.isoformat(),
            "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
        })

    return {"items": items}


@router.put("/applications/{app_id}")
async def review_application(
    app_id: int,
    req: ApiApplicationReview,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ApiApplication).where(ApiApplication.id == app_id))
    app_obj = result.scalar_one_or_none()
    if not app_obj:
        raise HTTPException(status_code=404, detail="申请不存在")
    if app_obj.status != "pending":
        raise HTTPException(status_code=400, detail="该申请已被审核")

    app_obj.status = req.status
    app_obj.review_comment = req.comment
    app_obj.reviewed_by = admin.id
    app_obj.reviewed_at = datetime.now(timezone.utc)

    if req.status == "approved":
        user_result = await db.execute(select(User).where(User.id == app_obj.user_id))
        user = user_result.scalar_one_or_none()
        if user:
            user.system_api_approved = True

    await db.commit()
    return {"message": f"申请已{'批准' if req.status == 'approved' else '拒绝'}"}


# ── Stats ──

@router.get("/stats")
async def get_stats(admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_tasks = (
        await db.execute(
            select(func.count(GenerationTask.id)).where(GenerationTask.created_at >= today_start)
        )
    ).scalar()
    total_tasks = (await db.execute(select(func.count(GenerationTask.id)))).scalar()
    pending_apps = (
        await db.execute(
            select(func.count(ApiApplication.id)).where(ApiApplication.status == "pending")
        )
    ).scalar()

    return {
        "total_users": total_users,
        "today_tasks": today_tasks,
        "total_tasks": total_tasks,
        "pending_applications": pending_apps,
    }


# ── System API Keys (shared keys for approved users) ──

@router.get("/system-keys")
async def list_system_keys(admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    """List all system-level API keys (owned by admin, user_id=admin.id)."""
    result = await db.execute(
        select(ApiKeyConfig)
        .where(ApiKeyConfig.user_id == admin.id, ApiKeyConfig.priority == -1)
        .order_by(ApiKeyConfig.model_type, ApiKeyConfig.id)
    )
    keys = result.scalars().all()
    items = []
    for k in keys:
        try:
            preview = mask_api_key(decrypt_api_key(k.api_key_encrypted))
        except Exception:
            preview = "***"
        items.append({
            "id": k.id, "model_type": k.model_type, "provider": k.provider,
            "base_url": k.base_url, "api_key_preview": preview,
            "model_name": k.model_name, "is_verified": k.is_verified,
            "is_enabled": k.is_enabled,
        })
    return {"items": items}


@router.post("/system-keys", status_code=status.HTTP_201_CREATED)
async def add_system_key(
    req: SystemKeyCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Add a system-level API key. Uses priority=-1 as a marker for system keys."""
    try:
        validate_provider_for_model_type(req.model_type, req.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    cfg = ApiKeyConfig(
        user_id=admin.id,
        model_type=req.model_type,
        provider=req.provider,
        base_url=req.base_url,
        api_key_encrypted=encrypt_api_key(req.api_key),
        model_name=req.model_name,
        priority=-1,  # marker: system key
        is_verified=False,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return {"id": cfg.id, "message": "系统API Key已添加，请验证有效性"}


@router.post("/system-keys/{key_id}/verify")
async def verify_system_key(key_id: int, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    """Verify a system API key by making a test request.

    Chat keys use a minimal chat health check. Image keys must return actual
    image bytes so unsupported providers or incorrect image models fail early.
    """
    result = await db.execute(select(ApiKeyConfig).where(ApiKeyConfig.id == key_id, ApiKeyConfig.priority == -1))
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="系统API Key不存在")

    from app.llm.client_factory import LLMClientFactory

    raw_key = decrypt_api_key(cfg.api_key_encrypted)
    verified = False
    error_msg = ""
    try:
        validate_provider_for_model_type(cfg.model_type, cfg.provider)
        client = LLMClientFactory.create(
            provider=cfg.provider,
            api_key=raw_key,
            base_url=cfg.base_url,
            model=cfg.model_name or "",
        )
        if cfg.model_type == "image":
            img = await client.generate_image(
                prompt="A simple black circle on a plain white background.",
                image_model=cfg.model_name or "",
                aspect_ratio="1:1",
                image_size="1K",
            )
            verified = bool(img and len(img) > 512)
            if not verified:
                error_msg = "图片模型验证失败：未返回有效图片数据"
        else:
            verified = await client.health_check()
            if not verified:
                error_msg = "health_check 返回 False（API 连接失败或认证无效）"
    except Exception as e:
        error_msg = str(e)

    cfg.is_verified = verified
    cfg.last_verified_at = datetime.now(timezone.utc)
    cfg.last_error = error_msg if not verified else None
    await db.commit()
    return {"is_verified": verified, "message": "验证通过" if verified else f"验证失败: {error_msg}"}


@router.put("/system-keys/{key_id}")
async def update_system_key(
    key_id: int,
    req: SystemKeyUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a system API key's configuration."""
    result = await db.execute(select(ApiKeyConfig).where(ApiKeyConfig.id == key_id, ApiKeyConfig.priority == -1))
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="系统API Key不存在")

    if req.base_url is not None:
        cfg.base_url = req.base_url or None
    if req.api_key is not None and len(req.api_key) >= 10:
        cfg.api_key_encrypted = encrypt_api_key(req.api_key)
        cfg.is_verified = False
    if req.model_name is not None:
        cfg.model_name = req.model_name or None
        cfg.is_verified = False

    try:
        validate_provider_for_model_type(cfg.model_type, cfg.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()
    await db.refresh(cfg)

    try:
        preview = mask_api_key(decrypt_api_key(cfg.api_key_encrypted))
    except Exception:
        preview = "***"
    return {
        "id": cfg.id, "model_type": cfg.model_type, "provider": cfg.provider,
        "base_url": cfg.base_url, "api_key_preview": preview,
        "model_name": cfg.model_name, "is_verified": cfg.is_verified,
        "is_enabled": cfg.is_enabled, "message": "已更新",
    }


@router.delete("/system-keys/{key_id}")
async def delete_system_key(key_id: int, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ApiKeyConfig).where(ApiKeyConfig.id == key_id, ApiKeyConfig.priority == -1))
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="系统API Key不存在")
    await db.delete(cfg)
    await db.commit()
    return {"message": "已删除"}


# ── System Config ──

@router.get("/configs")
async def get_configs(admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SystemConfig).order_by(SystemConfig.config_key))
    configs = result.scalars().all()
    return {
        "items": [
            {"key": c.config_key, "value": c.config_value, "description": c.description}
            for c in configs
        ]
    }


@router.put("/configs/{key}")
async def update_config(
    key: str,
    value: dict,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SystemConfig).where(SystemConfig.config_key == key))
    cfg = result.scalar_one_or_none()
    if not cfg:
        cfg = SystemConfig(config_key=key, config_value=value, updated_by=admin.id)
        db.add(cfg)
    else:
        cfg.config_value = value
        cfg.updated_by = admin.id
    await db.commit()
    return {"message": f"配置 {key} 已更新"}


# ── Announcements ──

@router.get("/announcements")
async def list_announcements(admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Announcement).order_by(Announcement.id.desc()))
    items = result.scalars().all()
    return {
        "items": [
            {
                "id": a.id, "content": a.content, "is_important": a.is_important,
                "is_active": a.is_active, "created_at": a.created_at.isoformat(),
            }
            for a in items
        ]
    }


@router.post("/announcements", status_code=status.HTTP_201_CREATED)
async def create_announcement(
    content: str,
    is_important: bool = False,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    ann = Announcement(content=content, is_important=is_important, created_by=admin.id)
    db.add(ann)
    await db.commit()
    return {"message": "公告已发布"}


@router.delete("/announcements/{ann_id}")
async def delete_announcement(ann_id: int, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Announcement).where(Announcement.id == ann_id))
    ann = result.scalar_one_or_none()
    if not ann:
        raise HTTPException(status_code=404, detail="公告不存在")
    await db.delete(ann)
    await db.commit()
    return {"message": "公告已删除"}


# ── Style Guide Generation (P2-1) ──

class StyleGuideGenerateRequest(BaseModel):
    venue: str = "NeurIPS 2025"
    category: str = "diagram"  # diagram or plot
    images_base64: list[str]  # List of base64 encoded reference images
    captions: Optional[list[str]] = None
    save_as_default: bool = False  # Whether to overwrite the default style guide


@router.post("/generate-style-guide")
async def generate_style_guide_endpoint(
    req: StyleGuideGenerateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Generate a style guide from uploaded reference images (admin only).

    Uses LLM to analyze common visual patterns across reference images
    and produces a comprehensive Markdown style guide.
    """
    if not req.images_base64:
        raise HTTPException(status_code=400, detail="至少需要一张参考图片")

    if req.category not in ("diagram", "plot"):
        raise HTTPException(status_code=400, detail="category 必须为 diagram 或 plot")

    reference_images = []
    for idx, b64 in enumerate(req.images_base64):
        caption = req.captions[idx] if req.captions and idx < len(req.captions) else None
        reference_images.append({
            "base64": b64,
            "caption": caption or f"Reference {idx + 1}",
        })

    from app.services.generation_service import _build_load_balancer
    try:
        chat_lb = await _build_load_balancer(db, admin.id, "chat")
        if not chat_lb:
            raise RuntimeError("No chat model available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"初始化模型失败: {e}")

    from app.services.style_guide_service import generate_style_guide, save_style_guide

    existing_path = None
    if req.save_as_default:
        from app.services.style_guide_service import STYLE_GUIDE_DIR
        existing_path = str(STYLE_GUIDE_DIR / f"neurips2025_{req.category}_style_guide.md")

    guide_content = await generate_style_guide(
        chat_lb=chat_lb,
        reference_images=reference_images,
        venue=req.venue,
        category=req.category,
        existing_guide_path=existing_path,
    )

    result = {"content": guide_content, "saved": False}

    if req.save_as_default:
        filename = f"neurips2025_{req.category}_style_guide.md"
        saved_path = await save_style_guide(guide_content, filename)
        result["saved"] = True
        result["saved_path"] = saved_path

    return result
