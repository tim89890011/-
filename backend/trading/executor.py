"""
钢子出击 - 自动交易执行器（v5 双向USDT永续合约版）
基于 AI 信号在币安合约模拟盘（Testnet）执行 USDT 永续合约双向波段交易

交易模式：逐仓 + 3x杠杆（可配置）
信号逻辑（双向交易）：
  BUY   → 开多仓（Long）
  SELL  → 有多仓则平多，无仓位则不操作
  SHORT → 开空仓（Short）
  COVER → 有空仓则平空，无仓位则不操作
  HOLD  → 不操作

安全机制：
- 总开关控制（TRADE_ENABLED）
- 置信度阈值过滤
- 余额检查
- 单币种最大持仓上限（多/空分别计算）
- BUY/SHORT 冷却 / SELL/COVER 冷却
- 自动止盈止损（多仓 + 空仓，方向分别处理）
- 交易成交后 Telegram 通知
- 异常隔离（不影响主流程）
- 全量日志记录
"""

import logging
import asyncio
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional

import ccxt.async_support as ccxt
from sqlalchemy import select

from backend.config import settings
from backend.database.db import async_session
from backend.database.models import User, UserSettings, CooldownRecord
from backend.utils.symbol import to_ccxt
from backend.core.execution.state_manager import StateManager

# Re-export module-level utilities for backward compatibility
from backend.trading._utils import (  # noqa: F401
    _clamp_conf,
    _parse_symbols_csv,
    _update_atr_cache,
    _get_symbol_accuracy,
    _CLOSE_COOLDOWN_SECONDS,
    _ACCURACY_CACHE_TTL,
)

# Mixin imports
from backend.trading._trading_ops import TradingOpsMixin
from backend.trading._exchange_orders import ExchangeOrdersMixin
from backend.trading._signal_execution import SignalExecutionMixin
from backend.trading._tpsl_monitor import TpSlMonitorMixin

logger = logging.getLogger(__name__)

# 统一状态管理（取代模块级全局字典）
state = StateManager()

# 模块级兼容别名（供 router.py 等外部 import 平滑过渡）
_cooldown_map = state.cooldown_map
_sell_tighten_map = state.sell_tighten_map
_symbol_atr = state.symbol_atr
_symbol_sl_tracker = state.sl_tracker
_symbol_accuracy_cache = state.accuracy_cache


class AutoTrader(
    TradingOpsMixin,
    ExchangeOrdersMixin,
    SignalExecutionMixin,
    TpSlMonitorMixin,
):
    """自动交易执行器（v5 双向USDT永续合约版）"""

    def __init__(self):
        self._exchange: Optional[ccxt.binance] = None
        self._enabled: bool = False
        self._runtime_enabled: bool = True
        self._shutting_down: bool = False
        self._last_exchange_error: str = ""
        self._in_flight_tasks: set[asyncio.Task] = set()
        self._position_cache: list[dict] = []
        self._position_cache_ts: float = 0.0
        self._position_cache_ttl: float = 3.0
        self._trade_status_broadcast_cb = None
        # 交易所条件单跟踪 key: "BTCUSDT_long" → {"tp_id": str, "sl_id": str, "trailing_id": str, ...}
        self._exchange_tp_sl: dict[str, dict] = {}
        # 系统已处理的 order_id（保序，防止 ORDER_TRADE_UPDATE 重复写入记录）
        self._processed_order_ids: OrderedDict[str, None] = OrderedDict()

    def _mark_order_processed(self, oid: str) -> None:
        oid = str(oid)
        if not oid:
            return
        self._processed_order_ids[oid] = None
        if len(self._processed_order_ids) > 500:
            while len(self._processed_order_ids) > 200:
                self._processed_order_ids.popitem(last=False)

    def _invalidate_position_cache(self) -> None:
        self._position_cache_ts = 0.0

    async def initialize(self):
        """初始化合约交易所连接，设置杠杆和保证金模式"""
        if not settings.TRADE_ENABLED:
            logger.info("[交易] 自动交易未启用（TRADE_ENABLED=false）")
            return

        api_key = settings.BINANCE_TESTNET_API_KEY
        api_secret = settings.BINANCE_TESTNET_API_SECRET

        if not api_key or not api_secret:
            logger.warning("[交易] 币安模拟盘 API Key 未配置，自动交易不可用")
            return

        try:
            # 使用 binanceusdm + 手动 URL patch（ccxt 已屏蔽 sandbox 模式）
            self._exchange = ccxt.binanceusdm({
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                # 避免网络抖动导致无限等待
                "timeout": int(getattr(settings, "CCXT_TIMEOUT_MS", 30000) or 30000),
                "options": {
                    "adjustForTimeDifference": True,
                },
            })

            # 手动将所有 API URL 替换为合约测试网（ccxt 已屏蔽 sandbox 模式）
            # 用通用正则替换，避免 ccxt 新增 URL 类型时漏掉
            import re
            testnet_url = "https://testnet.binancefuture.com"
            api_urls = self._exchange.urls.get("api", {})
            for k in list(api_urls.keys()):
                v = api_urls[k]
                if isinstance(v, str) and "binance.com" in v and "testnet" not in v:
                    api_urls[k] = re.sub(r"https://[a-z]+\.binance\.com", testnet_url, v)
            # 安全验证：确保所有 URL 都指向测试网
            for k, v in api_urls.items():
                if isinstance(v, str) and "binance" in v and "testnet" not in v:
                    raise RuntimeError(
                        f"安全检查失败：API URL '{k}' 仍指向主网 ({v})。"
                        "禁止在非测试网环境执行交易。"
                    )
            logger.info("[交易] 已切换到币安合约测试网 (testnet.binancefuture.com)")

            # 加载市场信息
            await self._exchange.load_markets()

            # 确保账户为双向持仓模式（Hedge Mode）
            try:
                await self._exchange.set_position_mode(True)
                logger.info("[交易] 已设置双向持仓模式（Hedge Mode）")
            except Exception as e:
                if "No need to change" in str(e):
                    logger.info("[交易] 已处于双向持仓模式")
                else:
                    logger.warning(f"[交易] 设置双向持仓模式失败（可能已是该模式）: {e}")

            balance = await self._exchange.fetch_balance()
            usdt_free = float(balance.get("USDT", {}).get("free", 0))
            logger.info("[交易] 币安合约模拟盘连接成功，余额已获取")

            # 设置每个交易币种的杠杆和保证金模式
            await self._setup_leverage_and_margin()

            # 从数据库恢复冷却记录到内存
            await self._restore_cooldowns()

            self._enabled = True
            self._last_exchange_error = ""

        except Exception as e:
            logger.error(f"[交易] 币安合约模拟盘连接失败: {e}")
            self._enabled = False
            self._last_exchange_error = str(e)

    async def _setup_leverage_and_margin(self):
        """为所有交易币种设置杠杆和逐仓/全仓模式（优先读 DB，fallback config.py）"""
        user_settings = await self._load_user_settings_by_username(settings.ADMIN_USERNAME)

        leverage = (
            int(user_settings.leverage)
            if user_settings and user_settings.leverage is not None
            else int(settings.TRADE_LEVERAGE)
        )
        margin_mode = (
            str(user_settings.margin_mode)
            if user_settings and user_settings.margin_mode
            else str(settings.TRADE_MARGIN_MODE)
        )  # "isolated" or "cross"

        symbols_raw = (
            user_settings.symbols
            if user_settings and user_settings.symbols
            else settings.TRADE_SYMBOLS
        )
        symbols = [s.strip().upper() for s in str(symbols_raw).split(",") if s.strip()]
        for symbol in symbols:
            ccxt_symbol = to_ccxt(symbol)
            try:
                # 设置保证金模式
                try:
                    await self._exchange.set_margin_mode(margin_mode, ccxt_symbol)
                    logger.info(f"[交易] {symbol} 保证金模式设置为 {margin_mode}")
                except Exception as e:
                    # 可能已经是该模式，忽略 "No need to change margin type" 错误
                    if "No need to change" not in str(e) and "already" not in str(e).lower():
                        logger.warning(f"[交易] {symbol} 设置保证金模式失败（可能已是 {margin_mode}）: {e}")

                # 设置杠杆
                await self._exchange.set_leverage(leverage, ccxt_symbol)
                logger.info(f"[交易] {symbol} 杠杆设置为 {leverage}x")

            except Exception as e:
                logger.warning(f"[交易] {symbol} 设置杠杆/保证金失败: {e}")

    async def _restore_cooldowns(self):
        """启动时从数据库恢复冷却记录到内存"""
        try:
            async with async_session() as db:
                result = await db.execute(select(CooldownRecord))
                rows = result.scalars().all()
                for row in rows:
                    key = f"{row.symbol}_{row.side}"
                    _cooldown_map[key] = float(row.last_trade_ts)
                if rows:
                    logger.info(f"[冷却] 从数据库恢复 {len(rows)} 条冷却记录")
        except Exception as e:
            logger.warning(f"[冷却] 恢复冷却记录失败（不影响功能）: {e}")

    async def get_positions(self) -> dict:
        """获取当前持仓数据（公开方法）"""
        return await self._calc_positions()

    async def close(self):
        """关闭交易所连接"""
        self._shutting_down = True
        # 等待正在执行的交易任务（避免重启过程中出现半完成的下单/平仓）
        if self._in_flight_tasks:
            tasks = [t for t in self._in_flight_tasks if not t.done()]
            if tasks:
                try:
                    await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=30)
                except Exception as e:
                    logger.warning(f"[交易] 等待进行中任务完成超时: {e}")
        if self._exchange:
            try:
                await self._exchange.close()
            except Exception as e:
                logger.warning(f"[交易] 关闭交易所连接失败: {e}")
            self._exchange = None
            self._enabled = False

    @property
    def is_active(self) -> bool:
        return self._enabled and self._runtime_enabled

    @property
    def exchange_connected(self) -> bool:
        return self._enabled

    @property
    def exchange_error(self) -> str:
        return self._last_exchange_error

    def toggle(self, enabled: bool):
        self._runtime_enabled = enabled
        logger.info(f"[交易] 运行时开关已{'开启' if enabled else '关闭'}")

    async def _load_user_settings(self, user_id: int) -> Optional[UserSettings]:
        """从数据库读取用户交易参数（不存在则返回 None）。"""
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(UserSettings).where(UserSettings.user_id == int(user_id))
                )
                return result.scalar_one_or_none()
        except Exception as e:
            logger.warning(f"[交易] 读取 UserSettings 失败 user_id={user_id}: {e}")
            return None

    async def _load_user_settings_by_username(self, username: str) -> Optional[UserSettings]:
        """通过用户名获取 settings（用于默认管理员配置）。"""
        if not username:
            return None
        try:
            async with async_session() as db:
                u = await db.execute(select(User).where(User.username == username))
                user = u.scalar_one_or_none()
                if not user:
                    return None
                s = await db.execute(
                    select(UserSettings).where(UserSettings.user_id == int(user.id))
                )
                return s.scalar_one_or_none()
        except Exception as e:
            logger.warning(f"[交易] 通过用户名读取 UserSettings 失败 username={username}: {e}")
            return None

    async def _get_cooldown_ts(self, symbol: str, side: str) -> float:
        """跨重启冷却读取：db + 内存热缓存"""
        key = f"{symbol}_{side}"
        mem_ts = float(_cooldown_map.get(key, 0) or 0)
        try:
            async with async_session() as db:
                r = await db.execute(
                    select(CooldownRecord).where(
                        CooldownRecord.symbol == symbol, CooldownRecord.side == side
                    )
                )
                row = r.scalar_one_or_none()
                db_ts = float(row.last_trade_ts or 0) if row else 0.0
                return max(mem_ts, db_ts)
        except Exception as e:
            logger.debug("[冷却] DB查询冷却记录失败，使用内存值: %s", e)
            return mem_ts

    async def _set_cooldown_ts(self, symbol: str, side: str, ts: float) -> None:
        """写入冷却记录（失败不影响主流程）。"""
        key = f"{symbol}_{side}"
        _cooldown_map[key] = float(ts)
        try:
            async with async_session() as db:
                r = await db.execute(
                    select(CooldownRecord).where(
                        CooldownRecord.symbol == symbol, CooldownRecord.side == side
                    )
                )
                row = r.scalar_one_or_none()
                if row is None:
                    row = CooldownRecord(symbol=symbol, side=side, last_trade_ts=float(ts))
                    db.add(row)
                else:
                    row.last_trade_ts = float(ts)
                    row.updated_at = datetime.now(timezone.utc)
                await db.commit()
        except Exception as e:
            logger.warning(f"[冷却] 持久化冷却时间失败 {symbol}_{side}: {e}")


# 全局单例
auto_trader = AutoTrader()
