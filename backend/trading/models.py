"""
钢子出击 - 交易记录数据模型
记录每笔自动交易的详细信息
"""

from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Boolean, Index
from datetime import datetime, timezone
from backend.database.models import Base


class TradeRecord(Base):
    """自动交易记录表"""

    __tablename__ = "trade_records"
    __table_args__ = (
        Index("ix_trade_records_created_at", "created_at"),
        Index("ix_trade_records_symbol", "symbol"),
        Index("ix_trade_records_idempotency_key", "idempotency_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(Integer, nullable=True, comment="关联的 AI 信号 ID")
    symbol = Column(String(20), nullable=False, comment="交易对，如 BTCUSDT")
    side = Column(String(10), nullable=False, comment="方向: BUY / SELL")
    order_type = Column(String(20), default="MARKET", comment="订单类型: MARKET / LIMIT")

    # 订单信息
    quantity = Column(Float, default=0, comment="成交数量（币）")
    price = Column(Float, default=0, comment="成交均价")
    quote_amount = Column(Float, default=0, comment="成交金额（USDT）")
    commission = Column(Float, default=0, comment="手续费")

    # 触发条件
    signal_confidence = Column(Float, default=0, comment="触发时信号置信度")
    signal_price = Column(Float, default=0, comment="信号产生时的价格")

    # 状态
    status = Column(
        String(20), default="pending",
        comment="状态: pending / filled / failed / skipped"
    )
    exchange_order_id = Column(String(100), default="", comment="交易所返回的订单 ID")
    error_msg = Column(Text, default="", comment="失败时的错误信息")


    # ============ v1.1 增补字段 ============
    horizon = Column(String(10), nullable=True, comment="信号周期: 15m/1h/4h")
    position_side = Column(String(10), nullable=True, comment="持仓方向: long/short")
    idempotency_key = Column(String(200), nullable=True, comment="幂等键")
    mid_price = Column(Float, default=0, comment="下单时中间价")
    spread = Column(Float, default=0, comment="买卖价差")
    slippage_bps = Column(Float, default=0, comment="滑点基点")
    realized_pnl_usdt = Column(Float, nullable=True, comment="交易所返回的已实现盈亏(USDT)")
    source = Column(String(20), default="ai", comment="来源: ai / exchange")

    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间"
    )


class PositionMeta(Base):
    """持仓元数据 — 记录开仓时的 TP/SL 参数和交易所条件单 ID，跨重启持久化"""

    __tablename__ = "position_meta"
    __table_args__ = (
        Index("ix_position_meta_symbol_side", "symbol", "pos_side", unique=True),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, comment="交易对，如 BTCUSDT")
    pos_side = Column(String(10), nullable=False, comment="持仓方向: long/short")

    entry_price = Column(Float, nullable=False, comment="开仓均价")
    quantity = Column(Float, default=0, comment="开仓数量")
    leverage = Column(Integer, default=1, comment="杠杆倍数")

    tp_pct = Column(Float, nullable=False, comment="止盈百分比（开仓时计算）")
    sl_pct = Column(Float, nullable=False, comment="止损百分比（开仓时计算）")

    tp_order_id = Column(String(100), default="", comment="交易所止盈条件单 ID")
    sl_order_id = Column(String(100), default="", comment="交易所止损条件单 ID")
    trailing_order_id = Column(String(100), default="", comment="交易所移动止盈条件单 ID")

    is_active = Column(Boolean, default=True, nullable=False, comment="仓位是否仍活跃")

    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间"
    )
    closed_at = Column(DateTime, nullable=True, comment="平仓时间")
