"""
钢子出击 - 信号方向预测一致性检查

重要说明：
本模块统计的是"价格方向预测一致性"，而非实际交易盈亏。
- BUY 信号 -> 价格上涨即为方向正确（不考虑涨幅大小）
- SELL 信号 -> 价格下跌即为方向正确（不考虑跌幅大小）
- HOLD 信号 -> 价格波动小于阈值即为方向正确

此统计仅反映 AI 对价格走势方向的判断能力，不构成投资收益保证。
实际交易效果还受滑点、手续费、流动性、止损执行等多种因素影响。
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.database.models import AISignal, SignalResult
from backend.market.binance_ws import get_price

logger = logging.getLogger(__name__)


# ============== 波动率配置 ==============
# 基于币种历史波动率动态计算的阈值配置
# 阈值表示：HOLD 信号允许的价格波动范围（百分比）
VOLATILITY_THRESHOLDS = {
    # 主流币 - 相对稳定的阈值
    "BTCUSDT": 0.8,
    "ETHUSDT": 1.0,
    # 中型市值币 - 中等波动
    "BNBUSDT": 1.5,
    "SOLUSDT": 2.0,
    "ADAUSDT": 2.0,
    "DOTUSDT": 2.0,
    "LINKUSDT": 2.5,
    "POLUSDT": 2.5,
    # 高波动币种
    "AVAXUSDT": 3.0,
    "ATOMUSDT": 3.0,
    "UNIUSDT": 3.0,
    "LTCUSDT": 2.5,
    # 默认阈值（新币种使用）
    "DEFAULT": 2.0,
}

# 时间衰减权重配置（近期信号权重更高）
# 格式：(天数, 权重倍数)
TIME_DECAY_WEIGHTS = [
    (7, 1.5),  # 7天内：1.5倍权重
    (30, 1.2),  # 30天内：1.2倍权重
    (90, 1.0),  # 90天内：1.0倍权重
    (180, 0.8),  # 180天内：0.8倍权重
]
DEFAULT_TIME_WEIGHT = 0.6  # 超过180天的默认权重


@dataclass
class DirectionCheckResult:
    """方向一致性检查结果"""

    signal_id: int
    symbol: str
    signal_type: str
    price_at_signal: float
    check_price: float
    price_change_pct: float
    result: str  # "CORRECT", "INCORRECT", "NEUTRAL"
    threshold: float
    checked_at: datetime
    time_weight: float


def get_volatility_threshold(symbol: str) -> float:
    """
    获取币种的波动率阈值

    阈值用于判断 HOLD 信号是否正确：
    - 如果价格变化绝对值 < 阈值，则认为 HOLD 判断正确
    - 不同币种波动率不同，阈值也不同
    """
    return VOLATILITY_THRESHOLDS.get(symbol.upper(), VOLATILITY_THRESHOLDS["DEFAULT"])


def calculate_time_weight(signal_time: datetime) -> float:
    """
    计算信号的时间衰减权重

    近期信号权重更高，因为：
    1. 市场条件更接近当前
    2. AI 模型表现更稳定
    3. 长期信号可能受市场环境变化影响
    """
    now = datetime.now(timezone.utc)
    if signal_time.tzinfo is None:
        signal_time = signal_time.replace(tzinfo=timezone.utc)

    days_ago = (now - signal_time).days

    for max_days, weight in TIME_DECAY_WEIGHTS:
        if days_ago <= max_days:
            return weight

    return DEFAULT_TIME_WEIGHT


def check_direction_accuracy(
    signal_type: str,
    symbol: str,
    price_at_signal: float,
    current_price: float,
) -> Tuple[str, float]:
    """
    检查方向预测是否一致，而非简单的盈亏

    Args:
        signal_type: 信号类型 (BUY, SELL, HOLD)
        symbol: 交易对符号
        price_at_signal: 信号发出时的价格
        current_price: 当前检查时的价格

    Returns:
        Tuple[str, float]: (结果, 价格变化百分比)
        结果值："CORRECT" - 方向预测正确
               "INCORRECT" - 方向预测错误
               "NEUTRAL" - 中性（仅用于 HOLD 信号且波动在阈值内）
    """
    if price_at_signal <= 0 or current_price <= 0:
        return "INCORRECT", 0.0

    price_change_pct = ((current_price - price_at_signal) / price_at_signal) * 100

    if signal_type == "BUY" or signal_type == "COVER":
        # BUY/COVER 信号：价格上涨即为方向正确
        result = "CORRECT" if price_change_pct > 0 else "INCORRECT"
    elif signal_type == "SELL" or signal_type == "SHORT":
        # SELL/SHORT 信号：价格下跌即为方向正确
        result = "CORRECT" if price_change_pct < 0 else "INCORRECT"
    elif signal_type == "HOLD":
        # HOLD 信号：价格波动小于阈值即为方向正确
        threshold = get_volatility_threshold(symbol)
        if abs(price_change_pct) < threshold:
            result = "NEUTRAL"
        elif price_change_pct > 0:
            result = "INCORRECT"
        else:
            result = "INCORRECT"
    else:
        result = "INCORRECT"

    return result, price_change_pct


def calculate_weighted_accuracy(results: List[DirectionCheckResult]) -> Dict:
    """
    计算加权准确率

    使用时间衰减权重，近期信号权重更高
    """
    if not results:
        return {
            "weighted_accuracy": 0.0,
            "unweighted_accuracy": 0.0,
            "total_signals": 0,
            "correct_count": 0,
            "incorrect_count": 0,
            "neutral_count": 0,
            "total_weight": 0.0,
            "weighted_correct": 0.0,
        }

    total_weight = sum(r.time_weight for r in results)
    weighted_correct = sum(r.time_weight for r in results if r.result == "CORRECT")
    weighted_neutral = sum(r.time_weight for r in results if r.result == "NEUTRAL")

    correct_count = sum(1 for r in results if r.result == "CORRECT")
    incorrect_count = sum(1 for r in results if r.result == "INCORRECT")
    neutral_count = sum(1 for r in results if r.result == "NEUTRAL")

    # 加权准确率（中性不计入）
    decided_weight = total_weight - weighted_neutral
    weighted_accuracy = (
        (weighted_correct / decided_weight * 100) if decided_weight > 0 else 0.0
    )

    # 非加权准确率
    decided_count = correct_count + incorrect_count
    unweighted_accuracy = (
        (correct_count / decided_count * 100) if decided_count > 0 else 0.0
    )

    return {
        "weighted_accuracy": round(weighted_accuracy, 2),
        "unweighted_accuracy": round(unweighted_accuracy, 2),
        "total_signals": len(results),
        "correct_count": correct_count,
        "incorrect_count": incorrect_count,
        "neutral_count": neutral_count,
        "total_weight": round(total_weight, 2),
        "weighted_correct": round(weighted_correct, 2),
    }


async def check_signal_direction_consistency(
    db: AsyncSession,
    hours: int = 1,
) -> int:
    """
    检查 N 小时前信号的方向预测一致性

    返回检查了多少条信号
    """
    now = datetime.now(timezone.utc)
    target_time = now - timedelta(hours=hours)
    # 扩大窗口到 ±30 分钟，确保不遗漏因定时器漂移产生的信号
    window_start = target_time - timedelta(minutes=30)
    window_end = target_time + timedelta(minutes=30)

    # SQLite 存储 naive datetime，需去掉时区信息以确保比较正确
    window_start = window_start.replace(tzinfo=None)
    window_end = window_end.replace(tzinfo=None)

    # 查找该时间窗口内的信号（包含 BUY, SELL, HOLD）
    result = await db.execute(
        select(AISignal).where(
            and_(
                AISignal.created_at >= window_start,
                AISignal.created_at <= window_end,
            )
        )
    )
    signals = result.scalars().all()
    if not signals:
        return 0

    # 预加载已有结果，避免 N+1 查询
    signal_ids = [s.id for s in signals]
    existing_rows = await db.execute(
        select(SignalResult).where(SignalResult.signal_id.in_(signal_ids))
    )
    existing_map = {row.signal_id: row for row in existing_rows.scalars().all()}

    checked = 0
    for signal in signals:
        existing_result = existing_map.get(signal.id)

        # 获取当前价格
        price_info = get_price(signal.symbol)
        if not price_info:
            continue

        current_price = price_info.get("price", 0)
        if current_price <= 0 or signal.price_at_signal <= 0:
            continue

        # 检查方向一致性
        direction_result, price_change = check_direction_accuracy(
            signal_type=signal.signal,
            symbol=signal.symbol,
            price_at_signal=signal.price_at_signal,
            current_price=current_price,
        )

        if existing_result:
            # 只更新对应时间段的价格字段，不覆盖其他时间段的判断
            if hours == 1:
                existing_result.price_after_1h = current_price
            elif hours == 4:
                existing_result.price_after_4h = current_price
            elif hours == 24:
                existing_result.price_after_24h = current_price

            # 更新方向一致性结果
            existing_result.direction_result = direction_result
            existing_result.pnl_percent = round(price_change, 4)
            existing_result.checked_at = now
        else:
            # 创建新记录
            sr = SignalResult(
                signal_id=signal.id,
                price_after_1h=current_price if hours == 1 else 0,
                price_after_4h=current_price if hours == 4 else 0,
                price_after_24h=current_price if hours == 24 else 0,
                direction_result=direction_result,
                pnl_percent=round(price_change, 4),
                checked_at=now,
            )
            db.add(sr)
            existing_map[signal.id] = sr

        checked += 1

    if checked > 0:
        await db.commit()
        logger.info(f"[方向一致性检查] 检查了 {checked} 条 {hours}h 前的信号")

    return checked


async def get_direction_consistency_stats(db: AsyncSession, days: int = 0) -> dict:
    """
    获取信号方向预测一致性统计

    返回详细的统计数据，包括：
    - 总体方向一致性率（加权/非加权）
    - 按币种统计
    - 按信号类型统计
    - 时间衰减权重说明
    - 统计方法免责声明

    参数:
        days: 0=全部, 1=今日(北京时间0点起), 7=最近7天, 30=最近30天
    """
    # 构建查询
    stmt = select(SignalResult, AISignal).join(
        AISignal, SignalResult.signal_id == AISignal.id
    )

    # 按天数过滤（基于信号创建时间）
    if days == 1:
        # "今日" = 北京时间当天 00:00 起（UTC+8）
        now_utc = datetime.now(timezone.utc)
        today_bj = (now_utc + timedelta(hours=8)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        cutoff = today_bj - timedelta(hours=8)  # 转回 UTC
        stmt = stmt.where(AISignal.created_at >= cutoff)
    elif days > 1:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = stmt.where(AISignal.created_at >= cutoff)

    result = await db.execute(stmt)
    rows = result.all()

    # 统计方法说明
    methodology_note = {
        "title": "统计方法说明",
        "description": "本统计测量的是 AI 对价格走势方向的预测一致性，而非实际交易盈亏",
        "rules": [
            "BUY 信号：N小时后价格上涨 → 方向正确",
            "SELL 信号：N小时后价格下跌 → 方向正确",
            "HOLD 信号：N小时后价格波动小于阈值 → 方向正确",
        ],
        "thresholds": {
            "description": "HOLD 信号阈值（基于币种波动率）",
            "values": {
                k: f"{v}%" for k, v in VOLATILITY_THRESHOLDS.items() if k != "DEFAULT"
            },
            "default": f"{VOLATILITY_THRESHOLDS['DEFAULT']}%",
        },
        "time_decay": {
            "description": "时间衰减权重（近期信号权重更高）",
            "weights": [
                {"period": "7天内", "weight": "1.5x"},
                {"period": "30天内", "weight": "1.2x"},
                {"period": "90天内", "weight": "1.0x"},
                {"period": "180天内", "weight": "0.8x"},
                {"period": "超过180天", "weight": "0.6x"},
            ],
        },
    }

    # 免责声明
    disclaimer = {
        "title": "重要免责声明",
        "content": (
            "本统计仅为价格方向预测一致性参考，不构成投资效果保证。"
            "实际交易效果受滑点、手续费、流动性、止损执行、市场极端行情等多种因素影响。"
            "历史方向预测一致性不代表未来表现。投资有风险，决策需谨慎。"
        ),
        "risk_warning": "加密货币市场波动剧烈，请根据自身风险承受能力谨慎投资",
    }

    if not rows:
        trend_window_days = 90 if days == 0 else days
        return {
            "total_signals": 0,
            "direction_accuracy": 0,
            "weighted_accuracy": 0,
            "correct_count": 0,
            "incorrect_count": 0,
            "neutral_count": 0,
            "by_day": [],
            "trend_window_days": trend_window_days,
            "by_symbol": {},
            "by_signal_type": {},
            "avg_price_change": 0,
            "methodology": methodology_note,
            "disclaimer": disclaimer,
        }

    # 构建结果列表用于加权计算
    check_results: List[DirectionCheckResult] = []
    for sr, sig in rows:
        if sr.direction_result is None:
            continue
        time_weight = calculate_time_weight(sig.created_at)
        check_price = (
            sr.price_after_1h
            or sr.price_after_4h
            or sr.price_after_24h
            or sig.price_at_signal
        )
        check_results.append(
            DirectionCheckResult(
                signal_id=sig.id,
                symbol=sig.symbol,
                signal_type=sig.signal,
                price_at_signal=sig.price_at_signal,
                check_price=check_price,
                price_change_pct=sr.pnl_percent or 0,
                result=sr.direction_result,
                threshold=get_volatility_threshold(sig.symbol),
                checked_at=sr.checked_at or sig.created_at,
                time_weight=time_weight,
            )
        )

    # 计算加权准确率
    accuracy_stats = calculate_weighted_accuracy(check_results)

    # 按天趋势（用于前端展示每日准确率变化）
    def _to_bj_date_key(dt: datetime) -> str:
        # SQLite 里 created_at 往往是 naive；约定其代表 UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        bj = dt + timedelta(hours=8)
        return bj.strftime("%Y-%m-%d")

    by_day_map: Dict[str, Dict[str, float]] = {}
    for sr, sig in rows:
        if sr.direction_result is None:
            continue
        day_key = _to_bj_date_key(sig.created_at)
        if day_key not in by_day_map:
            by_day_map[day_key] = {"total": 0, "correct": 0, "incorrect": 0, "neutral": 0}
        by_day_map[day_key]["total"] += 1
        if sr.direction_result == "CORRECT":
            by_day_map[day_key]["correct"] += 1
        elif sr.direction_result == "INCORRECT":
            by_day_map[day_key]["incorrect"] += 1
        else:
            by_day_map[day_key]["neutral"] += 1

    by_day = []
    for day_key in sorted(by_day_map.keys()):
        d = by_day_map[day_key]
        decided = d["correct"] + d["incorrect"]
        acc = (d["correct"] / decided * 100.0) if decided > 0 else 0.0
        by_day.append(
            {
                "date": day_key,
                "total": int(d["total"]),
                "correct": int(d["correct"]),
                "incorrect": int(d["incorrect"]),
                "neutral": int(d["neutral"]),
                "accuracy": round(acc, 1),
            }
        )

    # “全部”场景：趋势默认只展示最近 90 天，避免点过多导致前端卡顿
    trend_window_days = 90 if days == 0 else days
    if trend_window_days > 0 and len(by_day) > trend_window_days:
        by_day = by_day[-trend_window_days:]

    # 按币种统计
    by_symbol: Dict[str, Dict] = {}
    for cr in check_results:
        sym = cr.symbol
        if sym not in by_symbol:
            by_symbol[sym] = {
                "total": 0,
                "correct": 0,
                "incorrect": 0,
                "neutral": 0,
                "threshold": f"{get_volatility_threshold(sym)}%",
            }
        by_symbol[sym]["total"] += 1
        if cr.result == "CORRECT":
            by_symbol[sym]["correct"] += 1
        elif cr.result == "INCORRECT":
            by_symbol[sym]["incorrect"] += 1
        else:
            by_symbol[sym]["neutral"] += 1

    # 添加各币种准确率
    for sym, data in by_symbol.items():
        decided = data["correct"] + data["incorrect"]
        data["accuracy"] = round(
            (data["correct"] / decided * 100) if decided > 0 else 0, 1
        )

    # 按信号类型统计
    by_type = {
        "BUY": {"total": 0, "correct": 0, "incorrect": 0},
        "SELL": {"total": 0, "correct": 0, "incorrect": 0},
        "SHORT": {"total": 0, "correct": 0, "incorrect": 0},
        "COVER": {"total": 0, "correct": 0, "incorrect": 0},
        "HOLD": {"total": 0, "correct": 0, "incorrect": 0, "neutral": 0},
    }
    for cr in check_results:
        sig_type = cr.signal_type
        if sig_type in by_type:
            by_type[sig_type]["total"] += 1
            if cr.result == "CORRECT":
                by_type[sig_type]["correct"] += 1
            elif cr.result == "INCORRECT":
                by_type[sig_type]["incorrect"] += 1
            elif cr.result == "NEUTRAL":
                by_type[sig_type]["neutral"] = by_type[sig_type].get("neutral", 0) + 1

    # 添加各类型准确率
    for sig_type, data in by_type.items():
        if data["total"] > 0:
            if sig_type == "HOLD":
                decided = data["correct"] + data["incorrect"]
            else:
                decided = data["correct"] + data["incorrect"]
            data["accuracy"] = round(
                (data["correct"] / decided * 100) if decided > 0 else 0, 1
            )

    avg_price_change = (
        sum(cr.price_change_pct for cr in check_results) / len(check_results)
        if check_results
        else 0
    )

    return {
        "total_signals": accuracy_stats["total_signals"],
        "direction_accuracy": accuracy_stats["unweighted_accuracy"],
        "weighted_accuracy": accuracy_stats["weighted_accuracy"],
        "correct_count": accuracy_stats["correct_count"],
        "incorrect_count": accuracy_stats["incorrect_count"],
        "neutral_count": accuracy_stats["neutral_count"],
        "by_day": by_day,
        "trend_window_days": trend_window_days,
        "by_symbol": by_symbol,
        "by_signal_type": by_type,
        "avg_price_change": round(avg_price_change, 4),
        "methodology": methodology_note,
        "disclaimer": disclaimer,
    }


# 保持向后兼容的别名
async def check_signal_accuracy(
    db: AsyncSession,
    hours: int = 1,
) -> int:
    """向后兼容的别名"""
    return await check_signal_direction_consistency(db, hours)


async def get_accuracy_stats(db: AsyncSession) -> dict:
    """向后兼容的别名"""
    return await get_direction_consistency_stats(db)
