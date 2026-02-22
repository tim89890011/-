"""
Trading data query service — AI エンジン向けの公開 API。

debate.py から交易データ照会ロジックを抽出し、
ai_engine → trading の直接依存（private メソッド呼出・モデル直接参照）を解消。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.trading.executor import auto_trader
from backend.trading.pnl import calc_pnl_pct, pair_trades
from backend.utils.symbol import to_base

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────
# Trade PnL Queries
# ────────────────────────────────────────────

async def fetch_recent_trade_pnl(symbol: str, db: Optional[AsyncSession]) -> str:
    """Query recent closed trade pairs with real PnL, split by long/short."""
    if not db:
        return ""
    try:
        from backend.trading.models import TradeRecord
        stmt = (
            select(TradeRecord.side, TradeRecord.quote_amount, TradeRecord.price, TradeRecord.created_at)
            .where(TradeRecord.symbol == symbol, TradeRecord.status == "filled")
            .order_by(TradeRecord.created_at.desc())
            .limit(20)
        )
        result = await db.execute(stmt)
        rows = result.all()
        if not rows:
            return ""

        pairs = pair_trades(rows, sort_order="desc")
        if not pairs:
            return ""

        lines = [f"\n【{symbol} 最近真实交易盈亏】"]
        short_pairs = [p for p in pairs if p["direction"] == "空"]
        long_pairs = [p for p in pairs if p["direction"] == "多"]

        if short_pairs:
            wins = sum(1 for p in short_pairs if p["pnl"] > 0)
            total_pnl = sum(p["pnl"] for p in short_pairs)
            lines.append(f"做空近{len(short_pairs)}笔: 赢{wins}笔/亏{len(short_pairs)-wins}笔, 净损益{total_pnl:+.2f}U")

        if long_pairs:
            wins = sum(1 for p in long_pairs if p["pnl"] > 0)
            total_pnl = sum(p["pnl"] for p in long_pairs)
            lines.append(f"做多近{len(long_pairs)}笔: 赢{wins}笔/亏{len(long_pairs)-wins}笔, 净损益{total_pnl:+.2f}U")

        return "\n".join(lines) if len(lines) > 1 else ""
    except Exception as e:
        logger.warning(f"[data_service] 查询 {symbol} 近期盈亏失败: {e}")
        return ""


async def fetch_loss_streak(symbol: str, db: Optional[AsyncSession]) -> tuple[str, int, str]:
    """Query consecutive loss summary. Returns (text, streak_count, streak_direction)."""
    if not db:
        return "", 0, ""
    try:
        from backend.trading.models import TradeRecord
        stmt = (
            select(TradeRecord.side, TradeRecord.quote_amount, TradeRecord.price, TradeRecord.created_at)
            .where(TradeRecord.symbol == symbol, TradeRecord.status == "filled")
            .order_by(TradeRecord.created_at.desc())
            .limit(30)
        )
        result = await db.execute(stmt)
        rows = list(result.all())
        if len(rows) < 2:
            return "", 0, ""

        paired = pair_trades(rows, sort_order="desc")
        if not paired:
            return "", 0, ""

        streak = 0
        streak_dir = ""
        for p in paired:
            direction = p["direction"]
            pnl = p["pnl"]
            if pnl < 0:
                if streak == 0:
                    streak_dir = direction
                if direction == streak_dir or streak == 0:
                    streak += 1
                    streak_dir = direction
                else:
                    break
            else:
                break

        from backend.config import settings as _s
        caution_threshold = int(getattr(_s, "RISK_RECENT_LOSS_STREAK_CAUTION", 5))
        halt_threshold = int(getattr(_s, "RISK_RECENT_LOSS_STREAK_HALT", 10))

        if streak >= halt_threshold:
            text = f"\n🛑【硬停警告】{symbol} 做{streak_dir}方向连续亏损{streak}次，已触发硬停！该方向应暂停交易。"
        elif streak >= caution_threshold:
            text = f"\n⚠️【警戒模式】{symbol} 做{streak_dir}方向连续亏损{streak}次，已进入警戒！建议：减仓/更高门槛/考虑反向。"
        elif streak >= 2:
            text = f"\n📊【连亏提醒】{symbol} 做{streak_dir}方向连续亏损{streak}次，请注意风险。"
        else:
            text = ""

        return text, streak, streak_dir
    except Exception as e:
        logger.warning(f"[data_service] 查询 {symbol} 连亏摘要失败: {e}")
        return "", 0, ""


async def fetch_trade_frequency(symbol: str, db: Optional[AsyncSession]) -> str:
    """Query trade frequency and last signal info."""
    if not db:
        return ""
    try:
        from backend.trading.models import TradeRecord
        from backend.database.models import AISignal

        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        stmt_count = (
            select(func.count())
            .select_from(TradeRecord)
            .where(TradeRecord.symbol == symbol, TradeRecord.status == "filled",
                   TradeRecord.created_at >= one_hour_ago)
        )
        result = await db.execute(stmt_count)
        count_1h = result.scalar() or 0

        stmt_last = (
            select(AISignal.signal, AISignal.price_at_signal, AISignal.created_at)
            .where(AISignal.symbol == symbol, AISignal.signal.notin_(["HOLD"]))
            .order_by(AISignal.created_at.desc())
            .limit(1)
        )
        result2 = await db.execute(stmt_last)
        last_row = result2.first()

        lines = [f"\n【{symbol} 交易频率】"]
        lines.append(f"最近1小时已成交{count_1h}次")
        if count_1h >= 8:
            lines.append("⚠️ 交易过于频繁，考虑降低操作频率或HOLD")

        if last_row:
            ago = datetime.now(timezone.utc) - last_row.created_at.replace(tzinfo=timezone.utc) if last_row.created_at.tzinfo is None else datetime.now(timezone.utc) - last_row.created_at
            mins = int(ago.total_seconds() / 60)
            lines.append(f"上一次信号: {last_row.signal}, {mins}分钟前, 当时价格{last_row.price_at_signal:.2f}")

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[data_service] 查询 {symbol} 交易频率失败: {e}")
        return ""


# ────────────────────────────────────────────
# Position Queries
# ────────────────────────────────────────────

async def fetch_global_positions(current_symbol: str) -> str:
    """Query global position summary (cross-symbol)."""
    try:
        positions = await auto_trader._calc_positions()
        if not positions:
            return ""

        long_total, short_total = 0.0, 0.0
        details = []
        for key, pos in positions.items():
            if pos.get("qty", 0) < 0.000001:
                continue
            notional = abs(pos.get("notional", 0))
            sym = key.replace("_long", "").replace("_short", "")
            side_cn = "多" if "long" in key else "空"
            details.append(f"{sym}{side_cn}${notional:.0f}")
            if "long" in key:
                long_total += notional
            else:
                short_total += notional

        if not details:
            return ""

        text = f"\n【全局持仓】{', '.join(details)}"
        text += f"\n总多仓${long_total:.0f}, 总空仓${short_total:.0f}"
        if long_total + short_total > 0:
            ratio = abs(long_total - short_total) / (long_total + short_total) * 100
            dominant = "偏多" if long_total > short_total else "偏空"
            text += f", {dominant}({ratio:.0f}%倾斜)"
            if ratio > 70:
                text += " ⚠️ 方向过度集中，新开仓需谨慎"
        return text
    except Exception as e:
        logger.warning(f"[data_service] 查询全局持仓失败: {e}")
        return ""


async def fetch_position_age(symbol: str) -> str:
    """Query current position duration."""
    try:
        positions = await auto_trader._calc_positions()
        texts = []
        for side_key, side_cn in [("long", "多"), ("short", "空")]:
            pos = positions.get(f"{symbol}_{side_key}")
            if pos and pos.get("qty", 0) > 0.000001:
                entry_time = pos.get("update_time")
                if entry_time:
                    if isinstance(entry_time, (int, float)):
                        entry_dt = datetime.fromtimestamp(entry_time / 1000, tz=timezone.utc)
                    else:
                        entry_dt = entry_time
                    age = datetime.now(timezone.utc) - entry_dt
                    hours = age.total_seconds() / 3600
                    if hours >= 6:
                        texts.append(f"{side_cn}仓已持有{hours:.1f}小时 ⚠️ 持仓时间较长，若未盈利可能方向有误")
                    elif hours >= 2:
                        texts.append(f"{side_cn}仓已持有{hours:.1f}小时，可评估止盈/止损")
                    else:
                        texts.append(f"{side_cn}仓已持有{hours*60:.0f}分钟，仍在观察期")
        if not texts:
            return ""
        return "\n【持仓时长】" + "；".join(texts)
    except Exception as e:
        logger.warning(f"[data_service] 查询 {symbol} 持仓时长失败: {e}")
        return ""


async def fetch_winning_patterns(symbol: str, db: Optional[AsyncSession]) -> str:
    """Query recent winning trade conditions/patterns."""
    if not db:
        return ""
    try:
        from backend.trading.models import TradeRecord
        stmt = (
            select(TradeRecord.side, TradeRecord.quote_amount, TradeRecord.price, TradeRecord.created_at)
            .where(TradeRecord.symbol == symbol, TradeRecord.status == "filled")
            .order_by(TradeRecord.created_at.desc())
            .limit(20)
        )
        result = await db.execute(stmt)
        rows = list(result.all())

        paired = pair_trades(rows, sort_order="desc")
        wins = []
        for p in paired:
            if p["pnl"] > 0:
                open_time = p["open_time"]
                beijing_hour = (open_time.hour + 8) % 24 if open_time else 0
                wins.append(f"做{p['direction']}赚{p['pnl']:.1f}U(开仓{beijing_hour}点)")

        if not wins:
            return ""
        return f"\n【赢钱模式】最近盈利交易: {'; '.join(wins[:5])}"
    except Exception as e:
        logger.warning(f"[data_service] 查询 {symbol} 赢钱模式失败: {e}")
        return ""


# ────────────────────────────────────────────
# Position Text Formatting
# ────────────────────────────────────────────

async def build_position_text(symbol: str, current_price: float) -> str:
    """Build contract position info text (long + short) for AI analysts."""
    try:
        positions = await auto_trader._calc_positions()
        texts = []

        long_pos = positions.get(f"{symbol}_long")
        if long_pos and long_pos["qty"] > 0.000001:
            texts.append(format_position_text(symbol, long_pos, "long", current_price))

        short_pos = positions.get(f"{symbol}_short")
        if short_pos and short_pos["qty"] > 0.000001:
            texts.append(format_position_text(symbol, short_pos, "short", current_price))

        if not texts:
            return ""

        return "\n\n".join(texts)
    except Exception as e:
        logger.warning(f"[data_service] 获取 {symbol} 合约持仓信息失败: {e}")
        return ""


def format_position_text(symbol: str, pos: dict, side: str, current_price: float) -> str:
    """Format a single position info text."""
    qty = pos["qty"]
    entry_price = pos.get("entry_price", 0)
    mark_price = pos.get("mark_price", current_price)
    leverage = pos.get("leverage", 3)
    liq_price = pos.get("liquidation_price", 0)
    notional = pos.get("notional", 0)

    base = to_base(symbol)
    side_cn = "多" if side == "long" else "空"

    pnl_pct = calc_pnl_pct(entry_price, mark_price, side)
    margin_pnl_pct = calc_pnl_pct(entry_price, mark_price, side, leverage)
    sign = "+" if pnl_pct >= 0 else ""
    margin_sign = "+" if margin_pnl_pct >= 0 else ""
    liq_text = f"强平价: ${liq_price:.2f}" if liq_price > 0 else "强平价: N/A"

    close_signal = "SELL" if side == "long" else "COVER"
    open_signal = "BUY" if side == "long" else "SHORT"
    opposite_open = "SHORT" if side == "long" else "BUY"

    if pnl_pct >= 2.5:
        profit_hint = (
            f"⚠️ 当前浮盈 {pnl_pct:.2f}%（保证金收益 {margin_pnl_pct:.1f}%），已接近止盈线（4%）！\n"
            f"- 强烈建议 {close_signal} 止盈平仓，锁定利润！不要贪心\n"
            f"- 利润已有安全垫，绝对不应该继续加仓"
        )
    elif pnl_pct >= 1.5:
        profit_hint = (
            f"✅ 当前浮盈 {pnl_pct:.2f}%（保证金收益 {margin_pnl_pct:.1f}%），利润尚可\n"
            f"- 如果出现反转信号，应倾向 {close_signal} 止盈\n"
            f"- 不要盲目加仓，保护已有利润优先"
        )
    elif pnl_pct <= -1.5:
        profit_hint = (
            f"🛑 当前浮亏 {pnl_pct:.2f}%（保证金亏损 {margin_pnl_pct:.1f}%），接近止损线（-2%）！\n"
            f"- 如果技术面没有明确反转迹象，应果断 {close_signal} 止损\n"
            f"- {leverage}x 杠杆下不要扛单，纪律止损比盲目持有更重要"
        )
    else:
        profit_hint = (
            f"- 如果{side_cn}仓盈利超过 2.5%（保证金 +7.5%），应倾向 {close_signal} 止盈\n"
            f"- 如果{side_cn}仓亏损超过 1.5%（保证金 -4.5%），应倾向 {close_signal} 止损"
        )

    return (
        f"=== 当前{side_cn}仓持仓（重要！请纳入分析） ===\n"
        f"模式: USDT永续合约 | {leverage}x杠杆 | 逐仓\n"
        f"持有 {base} {side_cn}仓: {qty:.6f} 个\n"
        f"开仓均价: ${entry_price:.2f}\n"
        f"标记价格: ${mark_price:.2f}\n"
        f"名义价值: ${abs(notional):.2f}\n"
        f"浮动盈亏（价格维度）: {sign}{pnl_pct:.2f}%\n"
        f"浮动盈亏（保证金维度）: {margin_sign}{margin_pnl_pct:.1f}%（⚠️ {leverage}x 杠杆放大）\n"
        f"{liq_text}\n"
        f"\n"
        f"【{side_cn}仓决策指引（{leverage}x 杠杆）】\n"
        f"{profit_hint}\n"
        f"- 已持有{side_cn}仓时，不要给 {opposite_open}（需先 {close_signal} 平仓再反向开仓）\n"
        f"- {open_signal} = 加{side_cn}仓，{close_signal} = 平{side_cn}仓，HOLD = 继续持仓等待"
    )
