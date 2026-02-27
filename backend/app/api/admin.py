from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.api_key import ApiApplication
from app.models.generation import GenerationTask
from app.models.system import Announcement, ApiUsageLog, SystemConfig
from app.models.user import User
from app.schemas.api_key import ApiApplicationResponse, ApiApplicationReview
from app.schemas.auth import UserResponse
from app.api.deps import get_current_admin

router = APIRouter(prefix="/admin", tags=["管理后台"])


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
