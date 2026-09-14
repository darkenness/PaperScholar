from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.core.database import get_db
from app.core.security import decrypt_api_key, encrypt_api_key, mask_api_key
from app.llm.provider_capabilities import validate_provider_for_model_type
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

router = APIRouter(prefix="/api-keys", tags=["API Key管理"])


from app.services.provider_service import serialize_config as _to_response, probe_config, update_config_fields, discover_models
from app.llm.endpoint_config import normalize_base_url


@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ApiKeyConfig).where(ApiKeyConfig.user_id == user.id, ApiKeyConfig.priority >= 0).order_by(ApiKeyConfig.model_type, ApiKeyConfig.priority.desc())
    )
    configs = result.scalars().all()
    chat_keys = [_to_response(c) for c in configs if c.model_type == "chat"]
    image_keys = [_to_response(c) for c in configs if c.model_type == "image"]
    return ApiKeyListResponse(chat_keys=chat_keys, image_keys=image_keys)


@router.post("", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(req: ApiKeyCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        validate_provider_for_model_type(req.model_type, req.provider)
        normalize_base_url(req.base_url, req.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    cfg = ApiKeyConfig(
        user_id=user.id,
        model_type=req.model_type,
        provider=req.provider,
        base_url=normalize_base_url(req.base_url, req.provider),
        display_name=req.display_name,
        api_options=req.api_options.model_dump(),
        api_key_encrypted=encrypt_api_key(req.api_key),
        model_name=req.model_name,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return _to_response(cfg)


@router.post("/{key_id}/verify", response_model=ApiKeyVerifyResponse)
async def verify_api_key(key_id: int, capability: str = Query("default", pattern="^(default|chat|vision|image_generation|image_edit)$"), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ApiKeyConfig).where(ApiKeyConfig.id == key_id, ApiKeyConfig.user_id == user.id, ApiKeyConfig.priority >= 0)
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="API Key配置不存在")

    result = await probe_config(cfg, capability)
    await db.commit()
    return ApiKeyVerifyResponse(**result)


@router.put("/{key_id}", response_model=ApiKeyResponse)
async def update_api_key(key_id: int, req: ApiKeyUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ApiKeyConfig).where(ApiKeyConfig.id == key_id, ApiKeyConfig.user_id == user.id, ApiKeyConfig.priority >= 0)
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="API Key配置不存在")

    try:
        update_config_fields(cfg, req)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    await db.refresh(cfg)
    return _to_response(cfg)


@router.delete("/{key_id}")
async def delete_api_key(key_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ApiKeyConfig).where(ApiKeyConfig.id == key_id, ApiKeyConfig.user_id == user.id, ApiKeyConfig.priority >= 0)
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


from app.schemas.api_key import ModelCloneRequest

@router.get("/{key_id}/models")
async def read_connection_models(key_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    source=await db.scalar(select(ApiKeyConfig).where(ApiKeyConfig.id == key_id, ApiKeyConfig.user_id == user.id, ApiKeyConfig.priority >= 0))
    if source is None:
        raise HTTPException(404, "连接不存在")
    try:
        return await discover_models(source)
    except Exception as exc:
        raise HTTPException(502, "读取失败；请检查地址或手动输入模型 ID") from exc

@router.post("/{key_id}/models", status_code=201)
async def add_connection_model(key_id: int, req: ModelCloneRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    source=await db.scalar(select(ApiKeyConfig).where(ApiKeyConfig.id == key_id, ApiKeyConfig.user_id == user.id, ApiKeyConfig.priority >= 0))
    if source is None:
        raise HTTPException(404, "连接不存在")
    try:
        validate_provider_for_model_type(req.model_type, req.provider)
        root=normalize_base_url(source.base_url, req.provider)
        if not req.model_name.strip():
            raise ValueError("模型 ID 不能为空")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    cfg=ApiKeyConfig(user_id=source.user_id, model_type=req.model_type, provider=req.provider,
        base_url=root, api_key_encrypted=source.api_key_encrypted, model_name=req.model_name.strip(),
        display_name=source.display_name, api_options=source.api_options, priority=source.priority, is_verified=False)
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return {"id":cfg.id,"message":"模型已添加，请测试所需能力"}
