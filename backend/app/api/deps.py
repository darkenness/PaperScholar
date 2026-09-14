from fastapi import Depends, HTTPException, Header, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效或过期的访问令牌")

    try:
        user_id=int(payload.get("sub",0))
    except (TypeError,ValueError):
        user_id=0
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的Token")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")

    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


async def get_stream_user(authorization: str | None = Header(None), token: str | None = Query(None), db: AsyncSession = Depends(get_db)) -> User:
    raw=authorization[7:] if authorization and authorization.lower().startswith("bearer ") else token
    payload=decode_access_token(raw) if raw else None
    try:
        uid=int(payload["sub"]) if payload else 0
    except (KeyError,TypeError,ValueError):
        uid=0
    user=await db.scalar(select(User).where(User.id==uid)) if uid else None
    if user is None or not user.is_active:
        raise HTTPException(401,"无效或过期的访问令牌")
    return user
