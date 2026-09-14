from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.invitation import InvitationCode
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    SendCodeRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["认证"])


def _normalize_invite_code(code: str) -> str:
    return code.strip()


@router.post("/send-code", response_model=MessageResponse)
async def send_verification_code(req: SendCodeRequest):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="当前已改为邀请码注册，无需邮箱验证码",
    )


async def _lock_invite_code(invite_code: str, db: AsyncSession) -> InvitationCode:
    configured_code = _normalize_invite_code(settings.INVITE_CODE)
    submitted_code = _normalize_invite_code(invite_code)

    if not configured_code:
        raise HTTPException(status_code=500, detail="服务器未配置邀请码")
    if submitted_code != configured_code:
        raise HTTPException(status_code=400, detail="邀请码错误")

    await db.execute(
        pg_insert(InvitationCode)
        .values(
            code=configured_code,
            max_uses=settings.INVITE_CODE_MAX_USES,
            used_count=0,
        )
        .on_conflict_do_nothing(index_elements=[InvitationCode.code])
    )
    result = await db.execute(
        select(InvitationCode)
        .where(InvitationCode.code == configured_code)
        .with_for_update()
    )
    invite = result.scalar_one()
    invite.max_uses = settings.INVITE_CODE_MAX_USES
    if invite.used_count >= invite.max_uses:
        raise HTTPException(status_code=400, detail="邀请码使用次数已达上限")

    return invite


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    invite = await _lock_invite_code(req.invite_code, db)

    # Check existing
    result = await db.execute(
        select(User).where((User.username == req.username) | (User.email == req.email))
    )
    existing = result.scalar_one_or_none()
    if existing:
        if existing.username == req.username:
            raise HTTPException(status_code=409, detail="用户名已被使用")
        raise HTTPException(status_code=409, detail="邮箱已被注册")

    # Create user
    user = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="用户名或邮箱已被使用")

    invite.used_count += 1
    await db.commit()
    await db.refresh(user)

    # First user becomes admin
    result = await db.execute(select(User).limit(2))
    all_users = result.scalars().all()
    if len(all_users) == 1:
        user.role = "admin"
        user.system_api_approved = True
        await db.commit()
        await db.refresh(user)

    token = create_access_token(data={"sub": str(user.id), "role": user.role})

    return AuthResponse(
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            system_api_approved=user.system_api_approved,
            created_at=user.created_at.isoformat(),
        ),
        access_token=token,
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")

    token = create_access_token(data={"sub": str(user.id), "role": user.role})

    return AuthResponse(
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            system_api_approved=user.system_api_approved,
            created_at=user.created_at.isoformat(),
        ),
        access_token=token,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        system_api_approved=user.system_api_approved,
        created_at=user.created_at.isoformat(),
    )


@router.put("/me", response_model=UserResponse)
async def update_me(
    req: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.username is not None:
        existing = await db.execute(
            select(User).where(User.username == req.username, User.id != user.id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="用户名已被使用")
        user.username = req.username

    if req.password is not None:
        user.password_hash = hash_password(req.password)

    await db.commit()
    await db.refresh(user)
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        system_api_approved=user.system_api_approved,
        created_at=user.created_at.isoformat(),
    )
