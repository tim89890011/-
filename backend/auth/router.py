"""
钢子出击 - 用户认证路由
注册、登录、获取用户信息、API Key 管理
"""

import time
import logging
import random
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from backend.database.db import get_db
from backend.database.models import User, AuthRateLimit, PasswordResetToken
from backend.auth.jwt_utils import (
    hash_password,
    verify_password,
    issue_token_pair,
    get_current_user,
    revoke_token,
    revoke_refresh_token,
    verify_refresh_token,
    generate_secure_token,
)
from backend.auth.models import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserInfo,
    UpdateAPIKeyRequest,
    APIKeyInfo,
    EncryptionStatus,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    PasswordResetConfigResponse,
    PasswordResetConfirm,
    PasswordResetWithToken,
)
from backend.config import settings
from backend.utils.crypto import (
    encrypt_api_key,
    decrypt_api_key,
    init_encryption,
    is_encryption_enabled,
    get_encryption_status,
)
from backend.utils.logger import mask_ip, mask_username

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["认证"])
security = HTTPBearer(auto_error=False)

# ============ 初始化加密模块 ============
# 应用启动时初始化加密（使用配置中的密钥）
_encryption_initialized = False


def _ensure_encryption_initialized():
    """确保加密模块已初始化"""
    global _encryption_initialized
    if not _encryption_initialized:
        init_encryption(
            key=settings.ENCRYPTION_KEY or None,
            key_file=settings.ENCRYPTION_KEY_FILE or None,
            allow_plaintext=not settings.FORCE_ENCRYPTION,
        )
        _encryption_initialized = True


def _get_client_ip(request: Request) -> str:
    """获取客户端 IP（仅信任可信代理的转发头，避免伪造 X-Forwarded-For 绕过限流）。"""
    client_ip = request.client.host if request.client else "unknown"
    trusted = set(
        ip.strip()
        for ip in str(getattr(settings, "TRUSTED_PROXY_IPS", "") or "").split(",")
        if ip.strip()
    )

    if client_ip in trusted:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
        xri = request.headers.get("x-real-ip", "")
        if xri:
            return xri.strip()
    return client_ip


# ===== #59 修复：速率限制 =====
REGISTER_LIMIT = 3  # 每 IP 每 10 分钟最多注册 3 个账号
REGISTER_WINDOW = 600  # 10 分钟窗口
LOGIN_LIMIT = 10  # 每 IP 每 5 分钟最多尝试登录 10 次
LOGIN_WINDOW = 300  # 5 分钟窗口
RESET_LIMIT = 3  # 每用户每天最多申请 3 次密码重置
RESET_WINDOW = 86400  # 24 小时窗口


_captcha_store: dict[str, dict] = {}
CAPTCHA_TTL = 180


async def _rate_check_db(
    db: AsyncSession, bucket: str, ip: str, limit: int, window: int
) -> bool:
    """持久化限流：跨重启保留，支持多实例共享数据库。"""
    now = time.time()
    cutoff = now - window
    rate_key = f"{bucket}:{ip}"

    # 周期性清理过期记录，避免表无限膨胀（概率触发，避免每次请求都写数据库）
    if random.randint(1, 20) == 1:
        await db.execute(delete(AuthRateLimit).where(AuthRateLimit.last_ts < cutoff))

    q = await db.execute(
        select(AuthRateLimit).where(AuthRateLimit.rate_key == rate_key)
    )
    row = q.scalar_one_or_none()
    if row is None:
        db.add(
            AuthRateLimit(
                rate_key=rate_key, bucket=bucket, first_ts=now, last_ts=now, count=1
            )
        )
        await db.commit()
        return True

    if row.first_ts < cutoff:
        row.first_ts = now
        row.last_ts = now
        row.count = 1
        await db.commit()
        return True

    row.last_ts = now
    row.count += 1
    await db.commit()
    return row.count <= limit


def _cleanup_captcha():
    now = time.time()
    expired_keys = [
        k for k, v in _captcha_store.items() if now - v.get("ts", 0) > CAPTCHA_TTL
    ]
    for key in expired_keys:
        _captcha_store.pop(key, None)


# ============ 路由 ============


@router.get("/captcha")
async def get_captcha():
    """返回轻量文本验证码（用于阻挡批量脚本注册）"""
    _cleanup_captcha()
    a = random.randint(1, 9)
    b = random.randint(1, 9)
    cid = f"{int(time.time() * 1000)}{random.randint(1000, 9999)}"
    _captcha_store[cid] = {"answer": str(a + b), "ts": time.time()}
    return {"captcha_id": cid, "question": f"{a}+{b}=?"}


@router.get("/register-status")
async def get_register_status():
    """前端读取注册开关状态，保持入口与配置一致。"""
    return {"enabled": settings.ENABLE_PUBLIC_REGISTER}


@router.post("/register", response_model=TokenResponse)
async def register(request: Request, db: AsyncSession = Depends(get_db)):
    """注册新用户（带速率限制）"""
    # 先检查开关，避免关闭注册时泄露 Pydantic 验证细节
    if not settings.ENABLE_PUBLIC_REGISTER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前环境已关闭公开注册",
        )

    # 手动解析并验证请求体
    try:
        body = await request.json()
        req = RegisterRequest(**body)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请求参数格式错误",
        )

    # #59 修复：注册速率限制
    client_ip = _get_client_ip(request)
    if not await _rate_check_db(
        db, "register", client_ip, REGISTER_LIMIT, REGISTER_WINDOW
    ):
        logger.warning(f"[认证] 注册速率超限 IP={mask_ip(client_ip)}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="注册过于频繁，请 10 分钟后再试",
        )

    _cleanup_captcha()
    item = _captcha_store.get(req.captcha_id)
    if not item or str(item.get("answer")) != req.captcha_answer.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误或已过期",
        )
    _captcha_store.pop(req.captcha_id, None)

    # 检查用户名是否已存在
    result = await db.execute(select(User).where(User.username == req.username))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )

    # 创建用户
    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # 生成 Token
    access_token, refresh_token = await issue_token_pair(user.username)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        username=user.username,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    """用户登录（带速率限制）"""
    # 登录速率限制
    client_ip = _get_client_ip(request)
    if not await _rate_check_db(db, "login", client_ip, LOGIN_LIMIT, LOGIN_WINDOW):
        logger.warning(f"[认证] 登录速率超限 IP={mask_ip(client_ip)}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试过于频繁，请 5 分钟后再试",
        )

    # 查找用户
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用",
        )

    # 生成 Token
    access_token, refresh_token = await issue_token_pair(user.username)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        username=user.username,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="请求体格式错误"
        )
    refresh_token = str(body.get("refresh_token", "")).strip()
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="缺少 refresh_token"
        )

    username = await verify_refresh_token(refresh_token)
    await revoke_refresh_token(refresh_token)
    access_token, new_refresh_token = await issue_token_pair(username)
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        username=username,
    )


@router.post("/logout")
async def logout(
    request: Request,
    username: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    """主动登出：吊销当前 token。"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供认证凭据"
        )
    await revoke_token(credentials.credentials, username)
    try:
        body = await request.json()
        refresh_token = str(body.get("refresh_token", "")).strip()
        if refresh_token:
            await revoke_refresh_token(refresh_token)
    except Exception as e:
        logger.warning("[Auth] refresh token 注销失败（不影响登出）: %s", e)
    return {"message": "已安全退出"}


@router.get("/me", response_model=UserInfo)
async def get_me(
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户信息（需要 Token）"""
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    return UserInfo(
        id=user.id,
        username=user.username,
        exchange=user.exchange or "binance",
        is_active=user.is_active,
    )


# ============ API Key 管理路由 ============


@router.post("/api-key", response_model=UserInfo)
async def update_api_key(
    req: UpdateAPIKeyRequest,
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    更新当前用户的 API Key（加密存储）

    - api_key 和 api_secret 将被自动加密后存储
    - 留空表示不更新该字段
    """
    _ensure_encryption_initialized()

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # 更新交易所
    if req.exchange:
        user.exchange = req.exchange

    # 加密并更新 API Key
    if req.api_key:
        user.api_key_encrypted = encrypt_api_key(req.api_key)
        logger.info(f"[认证] 用户 {mask_username(username)} 更新了 API Key")

    if req.api_secret:
        user.api_secret_encrypted = encrypt_api_key(req.api_secret)
        logger.info(f"[认证] 用户 {mask_username(username)} 更新了 API Secret")

    await db.commit()
    await db.refresh(user)

    return UserInfo(
        id=user.id,
        username=user.username,
        exchange=user.exchange or "binance",
        is_active=user.is_active,
    )


@router.get("/api-key", response_model=APIKeyInfo)
async def get_api_key(
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前用户的 API Key（解密后）

    注意：仅返回当前登录用户的 API Key，管理员需使用 /admin/users/{id}/api-key
    """
    _ensure_encryption_initialized()

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    return APIKeyInfo(
        exchange=user.exchange or "binance",
        api_key=decrypt_api_key(user.api_key_encrypted),
        api_secret=decrypt_api_key(user.api_secret_encrypted),
        is_encrypted=is_encryption_enabled(),
    )


@router.get("/api-key/status", response_model=EncryptionStatus)
async def get_encryption_status_endpoint():
    """获取 API Key 加密状态（无需认证，用于前端显示）"""
    _ensure_encryption_initialized()

    status_info = get_encryption_status()
    message = ""

    if status_info["enabled"]:
        message = "API Key 加密已启用，您的凭证安全存储"
    else:
        message = "⚠️ API Key 加密未启用，凭证将以明文存储，建议联系管理员配置"

    return EncryptionStatus(
        enabled=status_info["enabled"],
        key_source=status_info["key_source"],
        message=message,
    )


# ============ 管理员专用路由 ============


async def _require_admin(
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> str:
    """验证当前用户是否为管理员"""
    if username != settings.ADMIN_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return username


@router.get("/admin/users/{user_id}/api-key", response_model=APIKeyInfo)
async def admin_get_user_api_key(
    user_id: int,
    _: str = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员获取指定用户的 API Key（解密后）"""
    _ensure_encryption_initialized()

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    return APIKeyInfo(
        exchange=user.exchange or "binance",
        api_key=decrypt_api_key(user.api_key_encrypted),
        api_secret=decrypt_api_key(user.api_secret_encrypted),
        is_encrypted=user.api_key_encrypted.startswith("enc:")
        if user.api_key_encrypted
        else False,
    )


@router.post("/admin/users/{user_id}/api-key", response_model=UserInfo)
async def admin_update_user_api_key(
    user_id: int,
    req: UpdateAPIKeyRequest,
    admin_username: str = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员更新指定用户的 API Key"""
    _ensure_encryption_initialized()

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # 更新交易所
    if req.exchange:
        user.exchange = req.exchange

    # 加密并更新 API Key
    if req.api_key:
        user.api_key_encrypted = encrypt_api_key(req.api_key)
        logger.info(
            f"[认证] 管理员 {mask_username(admin_username)} 更新了用户 {mask_username(user.username)} 的 API Key"
        )

    if req.api_secret:
        user.api_secret_encrypted = encrypt_api_key(req.api_secret)
        logger.info(
            f"[认证] 管理员 {mask_username(admin_username)} 更新了用户 {mask_username(user.username)} 的 API Secret"
        )

    await db.commit()
    await db.refresh(user)

    return UserInfo(
        id=user.id,
        username=user.username,
        exchange=user.exchange or "binance",
        is_active=user.is_active,
    )


# ============ 系统初始化 ============


async def ensure_admin_exists(db: AsyncSession):
    """确保管理员账号存在（首次启动时调用）。不覆盖已有管理员密码。"""
    from backend.config import settings

    result = await db.execute(
        select(User).where(User.username == settings.ADMIN_USERNAME)
    )
    admin = result.scalar_one_or_none()

    if not admin:
        admin = User(
            username=settings.ADMIN_USERNAME,
            password_hash=hash_password(settings.ADMIN_PASSWORD),
        )
        db.add(admin)
        await db.commit()
        logger.info(f"[认证] 管理员账号 '{settings.ADMIN_USERNAME}' 已创建")
    else:
        logger.info(f"[认证] 管理员账号 '{settings.ADMIN_USERNAME}' 已存在（不会同步覆盖密码）")


# ============ 密码重置路由 ============


@router.post("/reset-password-request", response_model=PasswordResetRequestResponse)
async def request_password_reset(
    req: PasswordResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    申请密码重置

    - 生成临时重置令牌（24小时有效）
    - 每用户每天最多申请 3 次
    - 无论用户是否存在，都返回相同的响应（防止用户名枚举）
    """
    client_ip = _get_client_ip(request)
    rate_key = f"reset:{req.username}"

    # 检查速率限制
    if not await _rate_check_db(
        db, "reset", f"{req.username}:{client_ip}", RESET_LIMIT, RESET_WINDOW
    ):
        logger.warning(
            f"[认证] 密码重置请求过于频繁: username={mask_username(req.username)}, ip={mask_ip(client_ip)}"
        )
        # 不泄露限流信息，返回标准响应
        return PasswordResetRequestResponse(
            message="如果该用户名存在，重置请求已提交。请联系管理员审批并获取重置令牌。",
            requires_admin_approval=settings.RESET_REQUIRE_ADMIN_APPROVAL,
        )

    # 检查用户是否存在
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()

    if not user:
        # 用户不存在，但返回相同的响应（防止用户名枚举攻击）
        logger.info(
            f"[认证] 密码重置申请：用户不存在 username={mask_username(req.username)}"
        )
        return PasswordResetRequestResponse(
            message="如果该用户名存在，重置请求已提交。请联系管理员审批并获取重置令牌。",
            requires_admin_approval=settings.RESET_REQUIRE_ADMIN_APPROVAL,
        )

    # 检查该用户是否已有未使用的有效令牌
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.username == req.username,
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > now,
        )
    )
    existing_token = result.scalar_one_or_none()

    if existing_token:
        # 返回已有的有效令牌
        logger.info(
            f"[认证] 密码重置申请：返回已有令牌 username={mask_username(req.username)}"
        )
        return PasswordResetRequestResponse(
            message="如果该用户名存在，重置请求已提交。请联系管理员审批并获取重置令牌。",
            requires_admin_approval=settings.RESET_REQUIRE_ADMIN_APPROVAL,
        )

    # 生成新令牌
    token = generate_secure_token(32)
    expires_at = now + timedelta(hours=24)

    reset_token = PasswordResetToken(
        token=token,
        username=req.username,
        expires_at=expires_at,
        used=False,
        admin_approved=False,
    )
    db.add(reset_token)
    await db.commit()

    logger.info(
        f"[认证] 密码重置申请：生成新令牌 username={mask_username(req.username)}"
    )

    # 安全策略：不在 API 响应中返回重置令牌，避免被滥用导致接管账号。
    return PasswordResetRequestResponse(
        message="如果该用户名存在，重置请求已提交。请联系管理员审批并获取重置令牌。",
        requires_admin_approval=True,
    )


@router.get("/reset-config", response_model=PasswordResetConfigResponse)
async def get_reset_config():
    return PasswordResetConfigResponse(
        requires_admin_approval=settings.RESET_REQUIRE_ADMIN_APPROVAL,
    )


@router.post("/reset-password-confirm")
async def confirm_password_reset(
    req: PasswordResetConfirm,
    admin_username: str = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    管理员确认密码重置请求（需要管理员权限）

    - 管理员验证令牌有效性并批准重置
    - 批准后用户才能使用令牌设置新密码
    """
    # 查找有效令牌
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token == req.token,
            PasswordResetToken.username == req.username,
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > now,
        )
    )
    reset_token = result.scalar_one_or_none()

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的令牌或令牌已过期",
        )

    if not req.approve:
        # 拒绝重置，标记令牌为已使用（实际为作废）
        reset_token.used = True
        reset_token.used_at = now
        await db.commit()
        logger.info(
            f"[认证] 管理员 {mask_username(admin_username)} 拒绝了密码重置请求: username={mask_username(req.username)}"
        )
        return {"message": "密码重置请求已拒绝"}

    # 批准重置
    reset_token.admin_approved = True
    await db.commit()

    logger.info(
        f"[认证] 管理员 {mask_username(admin_username)} 批准了密码重置请求: username={mask_username(req.username)}"
    )

    return {
        "message": "密码重置已批准，用户现在可以使用令牌设置新密码",
        "username": req.username,
        "approved_at": now.isoformat(),
    }


@router.post("/reset-password-with-token")
async def reset_password_with_token(
    req: PasswordResetWithToken,
    db: AsyncSession = Depends(get_db),
):
    """
    用户使用令牌设置新密码

    - 需要管理员已批准该令牌
    - 令牌只能使用一次
    - 重置成功后，旧密码失效
    """
    now = datetime.now(timezone.utc)

    # 查找有效且已批准的令牌
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token == req.token,
            PasswordResetToken.username == req.username,
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > now,
        )
    )
    reset_token = result.scalar_one_or_none()

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的令牌或令牌已过期",
        )

    if settings.RESET_REQUIRE_ADMIN_APPROVAL and not reset_token.admin_approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="管理员尚未批准重置请求",
        )

    # 查找用户
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # 更新密码
    user.password_hash = hash_password(req.new_password)

    # 标记令牌为已使用
    reset_token.used = True
    reset_token.used_at = now

    await db.commit()

    logger.info(f"[认证] 用户 {mask_username(req.username)} 成功重置密码")

    return {"message": "密码重置成功，请使用新密码登录", "username": req.username}


@router.get("/reset-pending", response_model=list[dict])
async def list_pending_resets(
    _: str = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    管理员查看待处理的密码重置请求（需要管理员权限）

    返回所有未使用且未过期的令牌列表
    """
    from sqlalchemy import desc

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(PasswordResetToken)
        .where(PasswordResetToken.used == False, PasswordResetToken.expires_at > now)
        .order_by(desc(PasswordResetToken.created_at))
    )
    tokens = result.scalars().all()

    return [
        {
            "id": t.id,
            "username": t.username,
            "token": t.token,
            "created_at": t.created_at.isoformat(),
            "expires_at": t.expires_at.isoformat(),
            "admin_approved": t.admin_approved,
        }
        for t in tokens
    ]
