"""
tests/conftest.py - 测试基础设施

提供:
- 异步 SQLite in-memory 数据库 fixture（不触碰生产数据）
- AutoTrader mock fixture（不连接真实交易所）
- 常用测试数据 factory（TradeRecord, AISignal, SignalSnapshot 等）
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.database.models import (
    Base,
    User,
    AISignal,
    SignalResult,
    SignalSnapshot,
    UserSettings,
    DailyPnL,
)
from backend.trading.models import TradeRecord, PositionMeta


# ────────────────────────────────────────────
# 异步数据库 Fixtures
# ────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session")
async def async_engine():
    """Session 级别的 in-memory SQLite 异步引擎。

    所有测试共享同一个引擎，避免反复建表的开销。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def async_session_factory(async_engine):
    """Session 级别的会话工厂。"""
    return async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture
async def db_session(async_session_factory):
    """Function 级别的数据库会话。

    每个测试拿到一个独立的会话，测试结束后回滚，
    保证测试之间互不干扰。
    """
    async with async_session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest_asyncio.fixture
async def db_session_committed(async_session_factory):
    """Function 级别的数据库会话（允许 commit）。

    适用于需要真正写入后再读取的集成测试。
    测试结束后清理数据。
    """
    async with async_session_factory() as session:
        yield session
        # 清理：删除所有表数据
        async with session.begin():
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(table.delete())


# ────────────────────────────────────────────
# AutoTrader Mock Fixture
# ────────────────────────────────────────────


@pytest.fixture
def mock_auto_trader():
    """返回一个不连接真实交易所的 AutoTrader 实例。

    - _exchange 替换为 AsyncMock（模拟 ccxt 交易所）
    - _enabled 设为 True（方便测试交易逻辑）
    - 交易所常用方法已预配置返回值
    """
    from backend.trading.executor import AutoTrader

    trader = AutoTrader()
    trader._enabled = True
    trader._runtime_enabled = True

    # 模拟 ccxt 交易所对象
    mock_exchange = AsyncMock()
    mock_exchange.fetch_balance = AsyncMock(return_value={
        "total": {"USDT": 10000.0},
        "free": {"USDT": 8000.0},
        "used": {"USDT": 2000.0},
    })
    mock_exchange.fetch_positions = AsyncMock(return_value=[])
    mock_exchange.create_order = AsyncMock(return_value={
        "id": "mock_order_001",
        "filled": 0.01,
        "cost": 500.0,
        "fee": {"cost": 0.2, "currency": "USDT"},
        "status": "closed",
    })
    mock_exchange.cancel_order = AsyncMock(return_value={"id": "mock_order_001"})
    mock_exchange.set_leverage = AsyncMock()
    mock_exchange.set_margin_mode = AsyncMock()
    mock_exchange.fetch_ticker = AsyncMock(return_value={
        "last": 50000.0,
        "bid": 49999.0,
        "ask": 50001.0,
    })

    trader._exchange = mock_exchange
    return trader


# ────────────────────────────────────────────
# 测试数据 Factory 函数
# ────────────────────────────────────────────


def make_trade_record(**overrides) -> TradeRecord:
    """创建 TradeRecord 模型实例，提供合理默认值。

    用法:
        record = make_trade_record(symbol="ETHUSDT", side="BUY")
        session.add(record)
    """
    defaults = {
        "signal_id": 1,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": 0.01,
        "price": 50000.0,
        "quote_amount": 500.0,
        "commission": 0.2,
        "signal_confidence": 75.0,
        "signal_price": 49800.0,
        "status": "filled",
        "exchange_order_id": "test_order_001",
        "error_msg": "",
        "position_side": "long",
        "source": "ai",
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return TradeRecord(**defaults)


def make_ai_signal(**overrides) -> AISignal:
    """创建 AISignal 模型实例，提供合理默认值。

    用法:
        signal = make_ai_signal(signal="SELL", confidence=85)
        session.add(signal)
    """
    defaults = {
        "symbol": "BTCUSDT",
        "signal": "BUY",
        "confidence": 75.0,
        "price_at_signal": 50000.0,
        "role_opinions": "{}",
        "debate_log": "",
        "final_reason": "测试信号",
        "risk_level": "中",
        "risk_assessment": "",
        "daily_quote": "",
        "voice_text": "",
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return AISignal(**defaults)


def make_signal_snapshot(**overrides) -> SignalSnapshot:
    """创建 SignalSnapshot 模型实例，提供合理默认值。

    用法:
        snapshot = make_signal_snapshot(signal="SHORT", confidence=80)
        session.add(snapshot)
    """
    defaults = {
        "signal_id": 1,
        "symbol": "BTCUSDT",
        "signal": "BUY",
        "confidence": 75.0,
        "price_at_signal": 50000.0,
        "horizon": "1h",
        "regime": "震荡行情",
        "execution_intent": False,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return SignalSnapshot(**defaults)


def make_user(**overrides) -> User:
    """创建 User 模型实例，提供合理默认值。

    注意: password_hash 使用占位值，不是真实 bcrypt 哈希。
    """
    defaults = {
        "username": "testuser",
        "password_hash": "$2b$12$placeholder_hash_for_testing_only",
        "exchange": "binance",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return User(**defaults)


def make_signal_result(**overrides) -> SignalResult:
    """创建 SignalResult 模型实例。"""
    defaults = {
        "signal_id": 1,
        "price_after_1h": 50500.0,
        "price_after_4h": 51000.0,
        "price_after_24h": 52000.0,
        "direction_result": "CORRECT",
        "pnl_percent": 2.0,
        "checked_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return SignalResult(**defaults)


def make_position_meta(**overrides) -> PositionMeta:
    """创建 PositionMeta 模型实例。"""
    defaults = {
        "symbol": "BTCUSDT",
        "pos_side": "long",
        "entry_price": 50000.0,
        "quantity": 0.01,
        "leverage": 3,
        "tp_pct": 3.0,
        "sl_pct": 1.5,
        "tp_order_id": "",
        "sl_order_id": "",
        "trailing_order_id": "",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return PositionMeta(**defaults)


def make_daily_pnl(**overrides) -> DailyPnL:
    """创建 DailyPnL 模型实例。"""
    defaults = {
        "date": "2025-01-01",
        "total_equity": 10000.0,
        "realized_pnl": 50.0,
        "unrealized_pnl": 20.0,
        "total_trades": 5,
        "win_trades": 3,
        "loss_trades": 2,
        "max_drawdown_pct": 1.5,
        "api_cost": 0.5,
        "net_pnl": 49.5,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return DailyPnL(**defaults)


def make_user_settings(user_id: int = 1, **overrides) -> UserSettings:
    """创建 UserSettings 模型实例。"""
    defaults = {
        "user_id": user_id,
        "strategy_mode": "steady",
        "amount_usdt": 50.0,
        "amount_pct": 3.0,
        "min_confidence": 65,
        "cooldown_seconds": 600,
        "close_cooldown_seconds": 30,
        "leverage": 2,
        "margin_mode": "isolated",
        "take_profit_pct": 3.0,
        "stop_loss_pct": 1.5,
        "trailing_stop_enabled": True,
        "symbols": "BTCUSDT,ETHUSDT",
        "tg_enabled": False,
    }
    defaults.update(overrides)
    return UserSettings(**defaults)
