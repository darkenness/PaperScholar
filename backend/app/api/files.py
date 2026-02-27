"""File upload and reference image management API."""

import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.models.generation import UploadedReference
from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter(prefix="/references", tags=["参考图管理"])

ALLOWED_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
MAX_SIZE = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024  # bytes


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_reference(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file.content_type}，仅支持 PNG/JPG/WebP")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail=f"文件太大，最大 {settings.MAX_UPLOAD_SIZE_MB}MB")

    # Save file
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "png"
    filename = f"{uuid.uuid4().hex}.{ext}"
    rel_path = os.path.join("references", str(user.id), filename)
    abs_path = os.path.join(settings.UPLOAD_DIR, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    with open(abs_path, "wb") as f:
        f.write(content)

    # DB record with 24h TTL
    ref = UploadedReference(
        user_id=user.id,
        file_path=rel_path,
        file_name=file.filename,
        file_size=len(content),
        mime_type=file.content_type,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(ref)
    await db.commit()
    await db.refresh(ref)

    return {
        "id": ref.id,
        "file_name": ref.file_name,
        "file_size": ref.file_size,
        "url": f"/uploads/{rel_path}",
        "expires_at": ref.expires_at.isoformat(),
    }


@router.get("/my")
async def list_my_references(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UploadedReference)
        .where(UploadedReference.user_id == user.id, UploadedReference.is_deleted == False)
        .order_by(UploadedReference.created_at.desc())
    )
    refs = result.scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "file_name": r.file_name,
                "file_size": r.file_size,
                "url": f"/uploads/{r.file_path}",
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in refs
        ]
    }


@router.delete("/{ref_id}")
async def delete_reference(
    ref_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UploadedReference).where(UploadedReference.id == ref_id, UploadedReference.user_id == user.id)
    )
    ref = result.scalar_one_or_none()
    if not ref:
        raise HTTPException(status_code=404, detail="参考图不存在")

    # Delete physical file
    abs_path = os.path.join(settings.UPLOAD_DIR, ref.file_path)
    if os.path.exists(abs_path):
        os.remove(abs_path)

    ref.is_deleted = True
    await db.commit()
    return {"message": "已删除"}
