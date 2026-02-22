"""
钢子出击 - 技术指标计算
使用 pandas-ta 计算常用技术指标
"""
import math
import logging
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


def _safe_float(val, default=0, decimals=2):
    """#8 修复：安全提取 float，NaN/Inf 替换为 default"""
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return round(f, decimals)
    except (TypeError, ValueError):
        return default


def calculate_indicators(df: pd.DataFrame) -> dict:
    """
    计算技术指标
    输入：K 线 DataFrame（需含 open/high/low/close/volume 列）
    返回：指标字典
    """
    if df.empty or len(df) < 30:
        return {"error": "K 线数据不足，无法计算指标"}

    result = {}

    try:
        # RSI(14)
        rsi = ta.rsi(df["close"], length=14)
        result["rsi"] = _safe_float(rsi.iloc[-1], 50) if rsi is not None and not rsi.empty else 50

        # MACD(12, 26, 9)
        # #53 修复：用列名取值，不依赖列索引顺序
        macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            # pandas-ta MACD 列名: MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
            cols = macd.columns
            macd_col = [c for c in cols if c.startswith("MACD_")]
            macdh_col = [c for c in cols if c.startswith("MACDh_")]
            macds_col = [c for c in cols if c.startswith("MACDs_")]
            result["macd"] = {
                "dif": _safe_float(macd[macd_col[0]].iloc[-1], 0, 4) if macd_col else 0,
                "dea": _safe_float(macd[macds_col[0]].iloc[-1], 0, 4) if macds_col else 0,
                "histogram": _safe_float(macd[macdh_col[0]].iloc[-1], 0, 4) if macdh_col else 0,
            }
        else:
            result["macd"] = {"dif": 0, "dea": 0, "histogram": 0}

        # 布林带(20, 2)
        # #53 修复：用列名前缀取值
        bbands = ta.bbands(df["close"], length=20, std=2)
        if bbands is not None and not bbands.empty:
            cols = bbands.columns
            bbl_col = [c for c in cols if c.startswith("BBL_")]
            bbm_col = [c for c in cols if c.startswith("BBM_")]
            bbu_col = [c for c in cols if c.startswith("BBU_")]
            result["bollinger"] = {
                "upper": _safe_float(bbands[bbu_col[0]].iloc[-1], 0) if bbu_col else 0,
                "middle": _safe_float(bbands[bbm_col[0]].iloc[-1], 0) if bbm_col else 0,
                "lower": _safe_float(bbands[bbl_col[0]].iloc[-1], 0) if bbl_col else 0,
            }
        else:
            result["bollinger"] = {"upper": 0, "middle": 0, "lower": 0}

        # KDJ
        # #54 修复：用列名取值
        stoch = ta.stoch(df["high"], df["low"], df["close"])
        if stoch is not None and not stoch.empty:
            cols = stoch.columns
            k_col = [c for c in cols if c.startswith("STOCHk_")]
            d_col = [c for c in cols if c.startswith("STOCHd_")]
            k_val = _safe_float(stoch[k_col[0]].iloc[-1], 50) if k_col else 50
            d_val = _safe_float(stoch[d_col[0]].iloc[-1], 50) if d_col else 50
            result["kdj"] = {
                "k": k_val,
                "d": d_val,
                "j": round(3 * k_val - 2 * d_val, 2),
            }
        else:
            result["kdj"] = {"k": 50, "d": 50, "j": 50}

        # ATR(14)
        atr = ta.atr(df["high"], df["low"], df["close"], length=14)
        result["atr"] = _safe_float(atr.iloc[-1], 0, 4) if atr is not None and not atr.empty else 0

        # 均线
        ma7 = ta.sma(df["close"], length=7)
        ma25 = ta.sma(df["close"], length=25)
        ma99 = ta.sma(df["close"], length=99) if len(df) >= 99 else None
        result["ma"] = {
            "ma7": _safe_float(ma7.iloc[-1], 0) if ma7 is not None and not ma7.empty else 0,
            "ma25": _safe_float(ma25.iloc[-1], 0) if ma25 is not None and not ma25.empty else 0,
            "ma99": _safe_float(ma99.iloc[-1], 0) if ma99 is not None and not ma99.empty else 0,
        }

        # 成交量变化率
        vol = df["volume"]
        if len(vol) >= 5:
            recent_avg = vol.iloc[-5:].mean()
            prev_avg = vol.iloc[-10:-5].mean() if len(vol) >= 10 else vol.mean()
            if prev_avg > 0:
                result["volume_change_rate"] = _safe_float((recent_avg - prev_avg) / prev_avg * 100, 0)
            else:
                result["volume_change_rate"] = 0
        else:
            result["volume_change_rate"] = 0

        # 当前价格
        result["current_price"] = _safe_float(df.iloc[-1]["close"], 0)

    except Exception as e:
        logger.error(f"[指标] 计算指标异常: {e}")
        result["error"] = str(e)

    return result


def calculate_short_term_indicators(df_15m: pd.DataFrame) -> dict:
    """
    从 15 分钟 K 线计算短期指标，用于波段交易精确入场/出场。
    """
    if df_15m.empty or len(df_15m) < 20:
        return {}

    result = {}
    try:
        # 15m RSI
        rsi_15m = ta.rsi(df_15m["close"], length=14)
        result["rsi_15m"] = _safe_float(rsi_15m.iloc[-1], 50) if rsi_15m is not None and not rsi_15m.empty else 50

        # 15m MACD
        macd_15m = ta.macd(df_15m["close"], fast=12, slow=26, signal=9)
        if macd_15m is not None and not macd_15m.empty:
            cols = macd_15m.columns
            macdh_col = [c for c in cols if c.startswith("MACDh_")]
            result["macd_histogram_15m"] = _safe_float(macd_15m[macdh_col[0]].iloc[-1], 0, 4) if macdh_col else 0
        else:
            result["macd_histogram_15m"] = 0

        # 15m 布林带位置
        bbands_15m = ta.bbands(df_15m["close"], length=20, std=2)
        if bbands_15m is not None and not bbands_15m.empty:
            cols = bbands_15m.columns
            bbl = [c for c in cols if c.startswith("BBL_")]
            bbu = [c for c in cols if c.startswith("BBU_")]
            if bbl and bbu:
                lower = _safe_float(bbands_15m[bbl[0]].iloc[-1], 0)
                upper = _safe_float(bbands_15m[bbu[0]].iloc[-1], 0)
                price = _safe_float(df_15m.iloc[-1]["close"], 0)
                if upper > lower > 0:
                    result["bb_position_15m"] = _safe_float((price - lower) / (upper - lower) * 100, 50)
                else:
                    result["bb_position_15m"] = 50
    except Exception as e:
        logger.error(f"[指标] 15m 短期指标计算异常: {e}")

    return result


def calculate_price_trend_context(df_1h: pd.DataFrame) -> dict:
    """
    计算近期价格走势上下文，让 AI 知道趋势方向和强度。
    """
    if df_1h.empty or len(df_1h) < 25:
        return {}

    result = {}
    try:
        current = float(df_1h.iloc[-1]["close"])

        # 4h 变化（最近 4 根 1h K线）
        if len(df_1h) >= 5:
            price_4h_ago = float(df_1h.iloc[-5]["close"])
            result["change_4h_pct"] = _safe_float((current - price_4h_ago) / price_4h_ago * 100, 0)

        # 24h 变化
        if len(df_1h) >= 25:
            price_24h_ago = float(df_1h.iloc[-25]["close"])
            result["change_24h_pct"] = _safe_float((current - price_24h_ago) / price_24h_ago * 100, 0)

        # 近 24h 最高/最低
        recent_24 = df_1h.iloc[-24:] if len(df_1h) >= 24 else df_1h
        high_24h = float(recent_24["high"].max())
        low_24h = float(recent_24["low"].min())
        result["high_24h"] = _safe_float(high_24h, 0)
        result["low_24h"] = _safe_float(low_24h, 0)

        # 距 24h 高点/低点的百分比
        if high_24h > 0:
            result["from_high_pct"] = _safe_float((current - high_24h) / high_24h * 100, 0)
        if low_24h > 0:
            result["from_low_pct"] = _safe_float((current - low_24h) / low_24h * 100, 0)

    except Exception as e:
        logger.error(f"[指标] 价格趋势上下文计算异常: {e}")

    return result


def calculate_4h_trend(df_4h: pd.DataFrame) -> dict:
    """
    从 4h K 线计算大周期趋势方向，让 AI 知道当前处于多头还是空头趋势。
    """
    if df_4h.empty or len(df_4h) < 10:
        return {}

    result = {}
    try:
        ma7 = ta.sma(df_4h["close"], length=7)
        ma25_data = ta.sma(df_4h["close"], length=min(25, len(df_4h) - 1)) if len(df_4h) >= 8 else None

        ma7_val = _safe_float(ma7.iloc[-1], 0) if ma7 is not None and not ma7.empty else 0
        ma25_val = _safe_float(ma25_data.iloc[-1], 0) if ma25_data is not None and not ma25_data.empty else 0

        result["ma7_4h"] = ma7_val
        result["ma25_4h"] = ma25_val

        rsi_4h = ta.rsi(df_4h["close"], length=14) if len(df_4h) >= 15 else None
        result["rsi_4h"] = _safe_float(rsi_4h.iloc[-1], 50) if rsi_4h is not None and not rsi_4h.empty else 50

        if ma7_val > 0 and ma25_val > 0:
            if ma7_val > ma25_val and result["rsi_4h"] > 50:
                result["trend_4h"] = "多头趋势"
            elif ma7_val < ma25_val and result["rsi_4h"] < 50:
                result["trend_4h"] = "空头趋势"
            else:
                result["trend_4h"] = "震荡/中性"
        else:
            result["trend_4h"] = "数据不足"

    except Exception as e:
        logger.error(f"[指标] 4h 趋势计算异常: {e}")

    return result


def format_indicators_for_ai(indicators: dict, symbol: str) -> str:
    """
    将指标格式化为 AI 可读的文本
    """
    if "error" in indicators:
        return f"[{symbol}] 指标计算失败: {indicators['error']}"

    lines = [
        f"=== {symbol} 技术指标（1h 时间框架） ===",
        f"当前价格: {indicators.get('current_price', 'N/A')}",
        "",
        f"RSI(14): {indicators.get('rsi', 'N/A')}",
    ]

    macd = indicators.get("macd", {})
    lines.extend([
        f"MACD - DIF: {macd.get('dif', 0)}, DEA: {macd.get('dea', 0)}, 柱状图: {macd.get('histogram', 0)}",
    ])

    bb = indicators.get("bollinger", {})
    lines.extend([
        f"布林带 - 上轨: {bb.get('upper', 0)}, 中轨: {bb.get('middle', 0)}, 下轨: {bb.get('lower', 0)}",
    ])

    kdj = indicators.get("kdj", {})
    lines.extend([
        f"KDJ - K: {kdj.get('k', 0)}, D: {kdj.get('d', 0)}, J: {kdj.get('j', 0)}",
    ])

    lines.append(f"ATR(14): {indicators.get('atr', 'N/A')}")

    ma = indicators.get("ma", {})
    lines.extend([
        f"均线 - MA7: {ma.get('ma7', 0)}, MA25: {ma.get('ma25', 0)}, MA99: {ma.get('ma99', 0)}",
    ])

    lines.append(f"成交量变化率(近5根vs前5根): {indicators.get('volume_change_rate', 0)}%")

    # 15 分钟短期指标
    short = indicators.get("short_term", {})
    if short:
        lines.append("")
        lines.append(f"=== {symbol} 短期指标（15m 时间框架） ===")
        lines.append(f"15m RSI(14): {short.get('rsi_15m', 'N/A')}")
        lines.append(f"15m MACD 柱状图: {short.get('macd_histogram_15m', 0)}")
        bb_pos = short.get("bb_position_15m", 50)
        pos_label = "接近下轨(超卖)" if bb_pos < 20 else "接近上轨(超买)" if bb_pos > 80 else "中间区域"
        lines.append(f"15m 布林带位置: {bb_pos:.0f}% ({pos_label})")

    # 4h 大周期趋势
    trend_4h = indicators.get("trend_4h", {})
    if trend_4h:
        lines.append("")
        lines.append(f"=== {symbol} 大周期趋势（4h 时间框架） ===")
        lines.append(f"4h MA7: {trend_4h.get('ma7_4h', 'N/A')} | 4h MA25: {trend_4h.get('ma25_4h', 'N/A')}")
        lines.append(f"4h RSI(14): {trend_4h.get('rsi_4h', 'N/A')}")
        trend_dir = trend_4h.get("trend_4h", "未知")
        lines.append(f"4h 趋势判断: {trend_dir}")
        if trend_dir == "多头趋势":
            lines.append("⚠️ 4h 级别处于多头趋势，逆势做空需极高确信度")
        elif trend_dir == "空头趋势":
            lines.append("⚠️ 4h 级别处于空头趋势，逆势做多需极高确信度")

    # 价格走势上下文
    trend = indicators.get("price_trend", {})
    if trend:
        lines.append("")
        lines.append(f"=== {symbol} 近期走势 ===")
        c4h = trend.get("change_4h_pct", 0)
        c24h = trend.get("change_24h_pct", 0)
        sign4h = "+" if c4h >= 0 else ""
        sign24h = "+" if c24h >= 0 else ""
        lines.append(f"4h 价格变化: {sign4h}{c4h}%")
        lines.append(f"24h 价格变化: {sign24h}{c24h}%")
        lines.append(f"24h 最高: {trend.get('high_24h', 'N/A')} | 24h 最低: {trend.get('low_24h', 'N/A')}")
        fh = trend.get("from_high_pct", 0)
        fl = trend.get("from_low_pct", 0)
        lines.append(f"距24h高点: {fh}% | 距24h低点: +{fl}%")

    return "\n".join(lines)
