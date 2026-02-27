import random
import string
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
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

# TODO [PRODUCTION]: Replace with Redis-backed store.
# In-memory store does NOT work with multiple uvicorn workers (codes are per-process).
# Also lost on server restart.
_verification_codes: dict[str, dict] = {}


def _generate_code() -> str:
    return "".join(random.choices(string.digits, k=6))


@router.post("/send-code", response_model=MessageResponse)
async def send_verification_code(req: SendCodeRequest):
    code = _generate_code()
    _verification_codes[req.email] = {
        "code": code,
        "expires": datetime.now(timezone.utc).timestamp() + 300,  # 5 minutes
    }
    # TODO: Send email via SMTP in production
    print(f"[DEV] Verification code for {req.email}: {code}")
    return MessageResponse(message="验证码已发送")


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Verify code (skip in dev mode if no code provided)
    from app.config import settings
    if req.verification_code:
        record = _verification_codes.get(req.email)
        if not record:
            raise HTTPException(status_code=400, detail="请先获取验证码")
        if datetime.now(timezone.utc).timestamp() > record["expires"]:
            _verification_codes.pop(req.email, None)
            raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")
        if record["code"] != req.verification_code:
            raise HTTPException(status_code=400, detail="验证码错误")
    elif settings.APP_ENV != "development":
        raise HTTPException(status_code=400, detail="请输入验证码")

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
    await db.commit()
    await db.refresh(user)

    _verification_codes.pop(req.email, None)

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
