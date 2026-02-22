"""
Phase B: pre-filter 影子引擎（只记录不决策）

目标：
- 用代码把“明显的指标共振/极值”结构化成一个可对比的建议
- 不直接替代 AI 结果，只作为 shadow 记录 + 注入 prompt 的参考
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from backend.config import settings
from backend.market.regime import (
    ATR_VOLATILE_THRESHOLD,
    BB_VOLATILE_THRESHOLD,
    BB_SQUEEZE_THRESHOLD,
    ATR_SQUEEZE_THRESHOLD,
)
from typing import Any


@dataclass(frozen=True)
class PreFilterResult:
    direction: str  # BUY / SHORT / HOLD / SELL / COVER
    score: int  # 0-10
    level: str  # STRONG / MODERATE / WEAK
    triggered_rules: list[str]
    reasons: str
    confidence_adjustment: int = 0

    def to_db_fields(self) -> dict[str, Any]:
        return {
            "pf_direction": self.direction,
            "pf_score": int(self.score),
            "pf_level": self.level,
            "pf_confidence_adj": self.confidence_adjustment,
            "pf_reasons": json.dumps(self.triggered_rules, ensure_ascii=False),
        }

    def to_prompt_text(self) -> str:
        rules = "、".join(self.triggered_rules) if self.triggered_rules else "无"
        return (
            f"[代码预筛参考]\n"
            f"- 建议方向: {self.direction}\n"
            f"- 得分: {self.score}/10 | 等级: {self.level}\n"
            f"- 触发规则: {rules}\n"
            f"- 理由: {self.reasons or '无'}\n"
            f"请你独立分析，你可以同意或反对预筛建议。"
        )


def _clamp_int(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        v_int = int(v)
    except Exception:
        return default
    return max(lo, min(hi, v_int))



def apply_assist_mode(pf_result, ai_signal: str, ai_confidence: int) -> tuple[int, int]:
    """
    assist 模式：根据 pre-filter 结果调整 AI 置信度
    返回 (调整后置信度, 调整量)
    """
    if settings.PREFILTER_MODE != "assist" or pf_result.score < 4:
        return ai_confidence, 0

    bullish = {"BUY", "COVER"}
    bearish = {"SELL", "SHORT"}
    pf_bull = pf_result.direction in bullish
    ai_bull = ai_signal in bullish
    pf_bear = pf_result.direction in bearish
    ai_bear = ai_signal in bearish

    adj = 0
    if (pf_bull and ai_bull) or (pf_bear and ai_bear):
        adj = 10 if pf_result.level == "STRONG" else 5
    elif (pf_bull and ai_bear) or (pf_bear and ai_bull):
        adj = -10 if pf_result.level == "STRONG" else -5

    new_conf = max(10, min(95, ai_confidence + adj))
    return new_conf, adj


def pre_filter(indicators: dict, position: dict | None = None) -> PreFilterResult:
    """
    输入：指标 dict（来自 calculate_indicators/short_term/price_trend 组合）
    输出：影子建议（不影响交易决策）
    """
    score = 0
    direction: str | None = None
    rules: list[str] = []

    rsi_raw = indicators.get("rsi")
    rsi = float(rsi_raw) if rsi_raw is not None else 50.0
    bb = indicators.get("bollinger", {}) or {}
    price = float(indicators.get("price", 0) or 0)
    bb_upper = float(bb.get("upper", 0) or 0)
    bb_lower = float(bb.get("lower", 0) or 0)

    macd = indicators.get("macd", {}) or {}
    macd_hist = float(macd.get("hist", 0) or 0)
    macd_signal = float(macd.get("signal", 0) or 0)

    kdj = indicators.get("kdj", {}) or {}
    k_raw = kdj.get("k")
    k = float(k_raw) if k_raw is not None else 50.0
    d_raw = kdj.get("d")
    d = float(d_raw) if d_raw is not None else 50.0

    atr = float(indicators.get("atr", 0) or 0)
    atr_pct = float(indicators.get("atr_percent", 0) or 0)

    # RSI 极值
    if rsi < 25:
        score += 3
        direction = "BUY"
        rules.append("RSI超卖(<25)")
    elif rsi > 75:
        score += 3
        direction = "SHORT"
        rules.append("RSI超买(>75)")
    elif rsi < 35:
        score += 1
        direction = direction or "BUY"
        rules.append("RSI偏低(<35)")
    elif rsi > 65:
        score += 1
        direction = direction or "SHORT"
        rules.append("RSI偏高(>65)")

    # 布林带触碰（依赖 upper/lower + 当前价格）
    if price > 0 and bb_lower > 0 and price <= bb_lower * 1.005:
        score += 2
        direction = direction or "BUY"
        rules.append("触及布林下轨")
    if price > 0 and bb_upper > 0 and price >= bb_upper * 0.995:
        score += 2
        direction = direction or "SHORT"
        rules.append("触及布林上轨")

    # MACD：粗略用 hist/signal 变化方向作为“动能”
    if macd_hist > 0 and macd_signal <= 0:
        score += 1
        direction = direction or "BUY"
        rules.append("MACD动能转正")
    elif macd_hist < 0 and macd_signal >= 0:
        score += 1
        direction = direction or "SHORT"
        rules.append("MACD动能转负")

    # KDJ
    if k < 20 and d < 20:
        score += 1
        direction = direction or "BUY"
        rules.append("KDJ超卖")
    elif k > 80 and d > 80:
        score += 1
        direction = direction or "SHORT"
        rules.append("KDJ超买")

    # ATR：高波动提醒（不直接给方向，只影响 level）
    if atr > 0 and atr_pct >= 1.5:
        score += 1
        rules.append("ATR高波动")

    # 持仓提示：仅做“可能该平”的建议（影子）— 不依赖交易所仓位细节
    if position:
        pnl_pct = float(position.get("pnl_pct", 0) or 0)
        side = (position.get("side") or "").lower()
        if side == "long" and pnl_pct >= 2.5:
            return PreFilterResult(
                direction="SELL",
                score=8,
                level="STRONG",
                triggered_rules=["持仓浮盈达标(多仓)"],
                reasons="当前多仓浮盈>=2.5%，影子建议止盈平仓",
            )
        if side == "short" and pnl_pct >= 2.5:
            return PreFilterResult(
                direction="COVER",
                score=8,
                level="STRONG",
                triggered_rules=["持仓浮盈达标(空仓)"],
                reasons="当前空仓浮盈>=2.5%，影子建议止盈平仓",
            )

    # 短期动量 / 单边行情检测（shadow提示）
    price_trend = indicators.get("price_trend", {}) or {}
    change_4h_pct = float(price_trend.get("change_4h_pct", 0) or 0)

    if change_4h_pct < -1.0 and rsi < 45:
        rules.append("4h跌幅超1%且RSI<45，市场单边下行中，频繁做空风险高")
    elif change_4h_pct > 1.0 and rsi > 55:
        rules.append("4h涨幅超1%且RSI>55，市场单边上行中，频繁做多风险高")

    # 短周期与大周期动量冲突
    short_term = indicators.get("short_term", {}) or {}
    st_rsi = float(short_term.get("rsi_15m", 50) or 50)
    trend_4h = indicators.get("trend_4h", {}) or {}
    trend_4h_dir = trend_4h.get("direction", "")

    if trend_4h_dir == "上涨" and st_rsi < 35:
        rules.append("15m动量向下但4h趋势向上，短期可能反弹")
    elif trend_4h_dir == "下跌" and st_rsi > 65:
        rules.append("15m动量向上但4h趋势向下，短期可能回落")

    # 市场状态分类（布林带宽度+ATR）
    bb_mid = float(bb.get("middle", 1) or 1)
    bb_width = ((bb_upper - bb_lower) / bb_mid * 100) if bb_mid > 0 else 0
    if atr_pct > ATR_VOLATILE_THRESHOLD or bb_width > BB_VOLATILE_THRESHOLD:
        rules.append("市场剧烈波动中，建议减少交易频率")
    elif bb_width < BB_SQUEEZE_THRESHOLD and atr_pct < ATR_SQUEEZE_THRESHOLD:
        rules.append("市场极度缩量震荡，等待方向突破再操作")

    score_i = _clamp_int(score, 0, 10, 0)
    level = "STRONG" if score_i >= 6 else "MODERATE" if score_i >= 3 else "WEAK"
    final_dir = direction or "HOLD"
    reasons = "；".join(rules)
    return PreFilterResult(direction=final_dir, score=score_i, level=level, triggered_rules=rules, reasons=reasons)

