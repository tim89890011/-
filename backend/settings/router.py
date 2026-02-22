"""
用户设置 API - 策略配置、修改密码
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from typing import Literal
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.jwt_utils import (
    get_current_user,
    hash_password,
    verify_password,
)
from backend.database.db import get_db
from backend.database.models import User, UserSettings
from backend.utils.logger import mask_username

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["用户设置"])

# ── 策略预设 ──────────────────────────────────────────
STRATEGY_PRESETS = {
    "steady": {
        "amount_usdt": 50.0,
        "amount_pct": 3.0,
        "max_position_usdt": 500.0,
        "max_position_pct": 20.0,
        "daily_limit_usdt": 500.0,
        "min_confidence": 65,
        "cooldown_seconds": 600,
        "close_cooldown_seconds": 30,
        "leverage": 2,
        "margin_mode": "isolated",
        "take_profit_pct": 3.0,
        "stop_loss_pct": 1.5,
        "trailing_stop_enabled": True,
        "position_timeout_hours": 24,
    },
    "aggressive": {
        "amount_usdt": 200.0,
        "amount_pct": 8.0,
        "max_position_usdt": 1000.0,
        "max_position_pct": 40.0,
        "daily_limit_usdt": 2000.0,
        "min_confidence": 40,
        "cooldown_seconds": 180,
        "close_cooldown_seconds": 15,
        "leverage": 5,
        "margin_mode": "isolated",
        "take_profit_pct": 6.0,
        "stop_loss_pct": 3.0,
        "trailing_stop_enabled": True,
        "position_timeout_hours": 48,
    },
}


# ── 请求/响应模型 ─────────────────────────────────────
class SettingsResponse(BaseModel):
    strategy_mode: str
    amount_usdt: float
    amount_pct: float
    max_position_usdt: float
    max_position_pct: float
    daily_limit_usdt: float
    min_confidence: int
    cooldown_seconds: int
    close_cooldown_seconds: int
    leverage: int
    margin_mode: str
    take_profit_pct: float
    stop_loss_pct: float
    trailing_stop_enabled: bool
    position_timeout_hours: int
    symbols: str
    tg_enabled: bool
    tg_chat_id: str


class UpdateSettingsRequest(BaseModel):
    strategy_mode: Literal["steady", "aggressive", "custom"] | None = None
    amount_usdt: float | None = Field(None, ge=10, le=5000)
    amount_pct: float | None = Field(None, ge=1, le=50)
    max_position_usdt: float | None = Field(None, ge=50, le=10000)
    max_position_pct: float | None = Field(None, ge=5, le=80)
    daily_limit_usdt: float | None = Field(None, ge=100, le=50000)
    min_confidence: int | None = Field(None, ge=20, le=100)
    cooldown_seconds: int | None = Field(None, ge=30, le=3600)
    close_cooldown_seconds: int | None = Field(None, ge=5, le=300)
    leverage: int | None = Field(None, ge=1, le=20)
    margin_mode: Literal["isolated", "cross"] | None = None
    take_profit_pct: float | None = Field(None, ge=0.5, le=20)
    stop_loss_pct: float | None = Field(None, ge=0.5, le=10)
    trailing_stop_enabled: bool | None = None
    position_timeout_hours: int | None = Field(None, ge=0, le=168)
    symbols: str | None = None
    tg_enabled: bool | None = None
    tg_chat_id: str | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, description="当前密码")
    new_password: str = Field(..., min_length=6, max_length=128, description="新密码")


# ── 获取用户设置 ──────────────────────────────────────
@router.get("", response_model=SettingsResponse)
async def get_settings(
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的策略设置"""
    user = await _get_user(db, username)
    settings_obj = await _get_or_create_settings(db, user.id)

    return SettingsResponse(
        strategy_mode=settings_obj.strategy_mode,
        amount_usdt=settings_obj.amount_usdt,
        amount_pct=settings_obj.amount_pct,
        max_position_usdt=settings_obj.max_position_usdt,
        max_position_pct=settings_obj.max_position_pct,
        daily_limit_usdt=settings_obj.daily_limit_usdt,
        min_confidence=settings_obj.min_confidence,
        cooldown_seconds=settings_obj.cooldown_seconds,
        close_cooldown_seconds=getattr(settings_obj, "close_cooldown_seconds", None) or 30,
        leverage=settings_obj.leverage,
        margin_mode=settings_obj.margin_mode,
        take_profit_pct=settings_obj.take_profit_pct,
        stop_loss_pct=settings_obj.stop_loss_pct,
        trailing_stop_enabled=settings_obj.trailing_stop_enabled,
        position_timeout_hours=settings_obj.position_timeout_hours,
        symbols=settings_obj.symbols,
        tg_enabled=settings_obj.tg_enabled,
        tg_chat_id=settings_obj.tg_chat_id,
    )


# ── 更新用户设置 ──────────────────────────────────────
@router.put("")
async def update_settings(
    req: UpdateSettingsRequest,
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新当前用户的策略设置"""
    user = await _get_user(db, username)
    settings_obj = await _get_or_create_settings(db, user.id)

    # 如果切换了策略模式，先应用预设
    if req.strategy_mode and req.strategy_mode in STRATEGY_PRESETS:
        preset = STRATEGY_PRESETS[req.strategy_mode]
        for k, v in preset.items():
            setattr(settings_obj, k, v)
        settings_obj.strategy_mode = req.strategy_mode
    elif req.strategy_mode == "custom":
        settings_obj.strategy_mode = "custom"

    # 逐字段更新（非 None 的字段）
    update_fields = req.model_dump(exclude_unset=True, exclude={"strategy_mode"})
    for k, v in update_fields.items():
        if v is not None:
            setattr(settings_obj, k, v)
            # 任何自定义修改自动切为 custom 模式（除非是切换预设）
            if req.strategy_mode not in ("steady", "aggressive"):
                settings_obj.strategy_mode = "custom"

    settings_obj.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(settings_obj)

    logger.info(f"[设置] 用户 {mask_username(username)} 更新策略: mode={settings_obj.strategy_mode}")

    return {"success": True, "message": "设置已保存", "strategy_mode": settings_obj.strategy_mode}


# ── 获取策略预设列表 ──────────────────────────────────
@router.get("/presets")
async def get_presets():
    """获取策略预设参数"""
    return {
        "presets": STRATEGY_PRESETS,
        "modes": [
            {"id": "steady", "name": "稳健模式", "desc": "低杠杆、严格风控、适合长期稳定收益"},
            {"id": "aggressive", "name": "激进模式", "desc": "高杠杆、宽松阈值、追求高收益高风险"},
            {"id": "custom", "name": "自定义", "desc": "自由调整所有参数"},
        ],
    }


# ── 修改密码 ──────────────────────────────────────────
@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改当前用户密码"""
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if not verify_password(req.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码错误")

    user.password_hash = hash_password(req.new_password)
    await db.commit()

    logger.info(f"[设置] 用户 {mask_username(username)} 修改了密码")
    return {"success": True, "message": "密码修改成功，请重新登录"}


# ── 辅助函数 ──────────────────────────────────────────
async def _get_user(db: AsyncSession, username: str) -> User:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


async def _get_or_create_settings(db: AsyncSession, user_id: int) -> UserSettings:
    """获取用户设置，不存在则创建默认（稳健模式）"""
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    settings_obj = result.scalar_one_or_none()

    if not settings_obj:
        settings_obj = UserSettings(user_id=user_id, strategy_mode="steady")
        # 应用稳健预设
        preset = STRATEGY_PRESETS["steady"]
        for k, v in preset.items():
            setattr(settings_obj, k, v)
        db.add(settings_obj)
        await db.commit()
        await db.refresh(settings_obj)

    return settings_obj
