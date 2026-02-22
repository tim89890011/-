from datetime import datetime, timedelta, timezone
import logging
import uuid

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import select

from backend.config import settings
from backend.database.db import async_session
from backend.database.models import User, RevokedToken, RefreshToken

security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError) as exc:
        logger.warning(f"[认证] 密码校验异常: {exc}")
        return False


def _encode_token(data: dict, expires_delta: timedelta, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        **data,
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(data: dict) -> str:
    return _encode_token(
        data=data,
        expires_delta=timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES),
        token_type="access",
    )


def create_refresh_token(username: str) -> str:
    return _encode_token(
        data={"sub": username},
        expires_delta=timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
        token_type="refresh",
    )


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
        ) from exc


def verify_token(token: str) -> dict:
    payload = _decode_token(token)
    username = payload.get("sub")
    jti = payload.get("jti")
    token_type = payload.get("type")
    if username is None or not jti or token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效：缺少必要信息",
        )
    return payload


async def _save_refresh_token(token: str, username: str):
    payload = _decode_token(token)
    jti = str(payload.get("jti") or "")
    exp = payload.get("exp")
    if not jti or not exp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh Token 无效"
        )

    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    async with async_session() as db:
        db.add(
            RefreshToken(
                jti=jti, username=username, expires_at=expires_at, revoked=False
            )
        )
        await db.commit()


async def issue_token_pair(username: str) -> tuple[str, str]:
    access_token = create_access_token({"sub": username})
    refresh_token = create_refresh_token(username)
    await _save_refresh_token(refresh_token, username)
    return access_token, refresh_token


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据，请先登录",
        )
    token = credentials.credentials
    username = await verify_token_active(token)
    return username


async def verify_token_active(token: str) -> str:
    payload = verify_token(token)
    username = payload.get("sub")
    token_jti = payload.get("jti")

    async with async_session() as db:
        user_result = await db.execute(select(User).where(User.username == username))
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在"
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用"
            )

        revoked_result = await db.execute(
            select(RevokedToken).where(RevokedToken.jti == token_jti)
        )
        if revoked_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 已失效，请重新登录",
            )
    return str(username)


async def verify_refresh_token(refresh_token: str) -> str:
    payload = _decode_token(refresh_token)
    username = payload.get("sub")
    token_type = payload.get("type")
    jti = payload.get("jti")
    if not username or token_type != "refresh" or not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh Token 无效"
        )

    async with async_session() as db:
        rt_result = await db.execute(
            select(RefreshToken).where(RefreshToken.jti == jti)
        )
        rt = rt_result.scalar_one_or_none()
        if rt is None or rt.revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh Token 已失效"
            )

        if rt.expires_at.tzinfo is None:
            expires_at = rt.expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = rt.expires_at
        if expires_at <= datetime.now(timezone.utc):
            rt.revoked = True
            rt.revoked_at = datetime.now(timezone.utc)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh Token 已过期"
            )

    return str(username)


async def revoke_token(token: str, username: str) -> None:
    payload = verify_token(token)
    token_jti = payload.get("jti")
    exp = payload.get("exp")
    if not token_jti or not exp:
        return

    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    async with async_session() as db:
        exists = await db.execute(
            select(RevokedToken).where(RevokedToken.jti == token_jti)
        )
        if exists.scalar_one_or_none() is None:
            db.add(
                RevokedToken(jti=token_jti, username=username, expires_at=expires_at)
            )
            await db.commit()


async def revoke_refresh_token(refresh_token: str) -> None:
    payload = _decode_token(refresh_token)
    jti = payload.get("jti")
    if not jti:
        return
    async with async_session() as db:
        result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
        rt = result.scalar_one_or_none()
        if rt and not rt.revoked:
            rt.revoked = True
            rt.revoked_at = datetime.now(timezone.utc)
            await db.commit()


def generate_secure_token(length: int = 32) -> str:
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))
