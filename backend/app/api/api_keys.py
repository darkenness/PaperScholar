from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decrypt_api_key, encrypt_api_key, mask_api_key
from app.models.api_key import ApiApplication, ApiKeyConfig
from app.models.user import User
from app.schemas.api_key import (
    ApiApplicationCreate,
    ApiApplicationResponse,
    ApiApplicationReview,
    ApiKeyCreate,
    ApiKeyListResponse,
    ApiKeyResponse,
    ApiKeyUpdate,
    ApiKeyVerifyResponse,
)
from app.api.deps import get_current_admin, get_current_user

router = APIRouter(prefix="/api-keys", tags=["API Key管理"])


def _to_response(cfg: ApiKeyConfig) -> ApiKeyResponse:
    try:
        raw_key = decrypt_api_key(cfg.api_key_encrypted)
        preview = mask_api_key(raw_key)
    except Exception:
        preview = "***"
    return ApiKeyResponse(
        id=cfg.id,
        model_type=cfg.model_type,
        provider=cfg.provider,
        base_url=cfg.base_url,
        api_key_preview=preview,
        model_name=cfg.model_name,
        is_verified=cfg.is_verified,
        is_enabled=cfg.is_enabled,
        priority=cfg.priority,
        last_verified_at=cfg.last_verified_at,
        last_error=cfg.last_error,
        created_at=cfg.created_at,
    )


@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ApiKeyConfig).where(ApiKeyConfig.user_id == user.id).order_by(ApiKeyConfig.model_type, ApiKeyConfig.priority.desc())
    )
    configs = result.scalars().all()
    chat_keys = [_to_response(c) for c in configs if c.model_type == "chat"]
    image_keys = [_to_response(c) for c in configs if c.model_type == "image"]
    return ApiKeyListResponse(chat_keys=chat_keys, image_keys=image_keys)


@router.post("", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(req: ApiKeyCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    cfg = ApiKeyConfig(
        user_id=user.id,
        model_type=req.model_type,
        provider=req.provider,
        base_url=req.base_url,
        api_key_encrypted=encrypt_api_key(req.api_key),
        model_name=req.model_name,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return _to_response(cfg)


@router.post("/{key_id}/verify", response_model=ApiKeyVerifyResponse)
async def verify_api_key(key_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ApiKeyConfig).where(ApiKeyConfig.id == key_id, ApiKeyConfig.user_id == user.id)
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="API Key配置不存在")

    from app.llm.client_factory import LLMClientFactory

    raw_key = decrypt_api_key(cfg.api_key_encrypted)
    verified = False
    error_msg = ""
    try:
        client = LLMClientFactory.create(
            provider=cfg.provider,
            api_key=raw_key,
            base_url=cfg.base_url,
            model=cfg.model_name or "",
        )
        verified = await client.health_check()
        if not verified:
            error_msg = "health_check 返回 False（API 连接失败或认证无效）"
    except Exception as e:
        error_msg = str(e)

    cfg.is_verified = verified
    cfg.last_verified_at = datetime.now(timezone.utc)
    cfg.last_error = error_msg if not verified else None
    await db.commit()

    return ApiKeyVerifyResponse(
        is_verified=verified,
        message="API Key验证通过" if verified else f"验证失败: {error_msg}",
    )


@router.put("/{key_id}", response_model=ApiKeyResponse)
async def update_api_key(key_id: int, req: ApiKeyUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ApiKeyConfig).where(ApiKeyConfig.id == key_id, ApiKeyConfig.user_id == user.id)
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="API Key配置不存在")

    if req.base_url is not None:
        cfg.base_url = req.base_url or None  # empty string -> None
    if req.api_key is not None:
        cfg.api_key_encrypted = encrypt_api_key(req.api_key)
        cfg.is_verified = False  # reset verification after key change
    if req.model_name is not None:
        cfg.model_name = req.model_name or None
    if req.priority is not None:
        cfg.priority = req.priority
    if req.is_enabled is not None:
        cfg.is_enabled = req.is_enabled

    await db.commit()
    await db.refresh(cfg)
    return _to_response(cfg)


@router.delete("/{key_id}")
async def delete_api_key(key_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ApiKeyConfig).where(ApiKeyConfig.id == key_id, ApiKeyConfig.user_id == user.id)
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="API Key配置不存在")

    await db.delete(cfg)
    await db.commit()
    return {"message": "已删除"}


# ── API Applications ──

app_router = APIRouter(prefix="/api-applications", tags=["系统API申请"])


@app_router.post("", response_model=ApiApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(req: ApiApplicationCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.system_api_approved:
        raise HTTPException(status_code=400, detail="您已获批系统API使用权限")

    # Check pending
    result = await db.execute(
        select(ApiApplication).where(ApiApplication.user_id == user.id, ApiApplication.status == "pending")
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="您已有待审核的申请")

    app_obj = ApiApplication(user_id=user.id, reason=req.reason)
    db.add(app_obj)
    await db.commit()
    await db.refresh(app_obj)
    return ApiApplicationResponse(
        id=app_obj.id,
        status=app_obj.status,
        reason=app_obj.reason,
        review_comment=app_obj.review_comment,
        created_at=app_obj.created_at,
        reviewed_at=app_obj.reviewed_at,
    )


@app_router.get("/my", response_model=list[ApiApplicationResponse])
async def my_applications(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ApiApplication).where(ApiApplication.user_id == user.id).order_by(ApiApplication.created_at.desc())
    )
    apps = result.scalars().all()
    return [
        ApiApplicationResponse(
            id=a.id, status=a.status, reason=a.reason,
            review_comment=a.review_comment, created_at=a.created_at, reviewed_at=a.reviewed_at,
        )
        for a in apps
    ]
