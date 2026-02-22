"""
市场状态分类（布林带宽度 + ATR + 均线排列）

从 debate.py 和 pre_filter.py 中提取的共享逻辑，
消除阈值重复，统一分类标准。
"""

# 分类阈值（统一管理，修 bug 只改一处）
ATR_VOLATILE_THRESHOLD = 3.0    # ATR% > 此值 → 剧烈波动
BB_VOLATILE_THRESHOLD = 8.0     # BB宽度% > 此值 → 剧烈波动
BB_SQUEEZE_THRESHOLD = 2.0      # BB宽度% < 此值 → 极度缩量
ATR_SQUEEZE_THRESHOLD = 0.5     # ATR% < 此值 → 极度缩量


def classify_market_regime(indicators: dict) -> str:
    """
    纯函数：根据指标判断市场状态（无惯性，无副作用）

    返回: "剧烈波动" | "趋势行情(上涨)" | "趋势行情(下跌)" | "震荡行情"
    """
    bb = indicators.get("bollinger", {})
    bb_upper = bb.get("upper", 0)
    bb_lower = bb.get("lower", 0)
    bb_mid = bb.get("middle", 1)
    bb_width = (bb_upper - bb_lower) / bb_mid * 100 if bb_mid > 0 else 0

    atr = indicators.get("atr", 0)
    price = indicators.get("price", bb_mid)
    atr_pct = (atr / price * 100) if price > 0 else 0

    ma7 = indicators.get("ma", {}).get("ma7", 0)
    ma25 = indicators.get("ma", {}).get("ma25", 0)
    ma99 = indicators.get("ma", {}).get("ma99", 0)
    ma_aligned = (
        (ma7 > ma25 > ma99) or (ma7 < ma25 < ma99)
        if ma7 > 0 and ma25 > 0 and ma99 > 0
        else False
    )

    if atr_pct > ATR_VOLATILE_THRESHOLD or bb_width > BB_VOLATILE_THRESHOLD:
        return "剧烈波动"
    elif ma_aligned and bb_width > 3.0:
        direction = "上涨" if ma7 > ma99 else "下跌"
        return f"趋势行情({direction})"
    else:
        return "震荡行情"


def is_volatile(indicators: dict) -> bool:
    """快捷判断：当前是否处于剧烈波动"""
    return classify_market_regime(indicators) == "剧烈波动"


def is_squeeze(indicators: dict) -> bool:
    """快捷判断：当前是否处于极度缩量震荡"""
    bb = indicators.get("bollinger", {})
    bb_upper = bb.get("upper", 0)
    bb_lower = bb.get("lower", 0)
    bb_mid = bb.get("middle", 1)
    bb_width = (bb_upper - bb_lower) / bb_mid * 100 if bb_mid > 0 else 0

    atr = indicators.get("atr", 0)
    price = indicators.get("price", bb_mid)
    atr_pct = (atr / price * 100) if price > 0 else 0

    return bb_width < BB_SQUEEZE_THRESHOLD and atr_pct < ATR_SQUEEZE_THRESHOLD
