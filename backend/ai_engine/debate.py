"""
钢子出击 - AI 辩论引擎
核心流程：采集数据 -> 算指标 -> 5 角色并发分析 -> R1 裁决 -> 存库
集成配额检查和指标采集
"""

import asyncio
import json
import time
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.market.data_collector import fetch_all_market_data
from backend.market.indicators import (
    calculate_indicators,
    calculate_short_term_indicators,
    calculate_price_trend_context,
    calculate_4h_trend,
    format_indicators_for_ai,
)
from backend.ai_engine.roles import analyze_all_roles, ROLES
from backend.notification.telegram_bot import send_telegram_message
from backend.ai_engine.deepseek_client import deepseek_client
from backend.ai_engine.prompts import build_final_judgment_prompt
from backend.database.models import AISignal, SignalResult
from backend.signal_engine.pre_filter import pre_filter
from backend.notification.voice import generate_voice_text
from backend.monitoring.metrics import metrics_collector
from backend.risk.gate import apply_risk_gate
from backend.trading.data_service import (
    fetch_recent_trade_pnl,
    fetch_loss_streak,
    fetch_trade_frequency,
    fetch_global_positions,
    fetch_position_age,
    fetch_winning_patterns,
    build_position_text,
)
from backend.ai_engine.json_parser import parse_json_from_text as _parse_json_from_text
from backend.market.regime import classify_market_regime

logger = logging.getLogger(__name__)

# 信号广播回调（由 main.py 注入，避免循环导入）
_signal_broadcast_callback = None
# 自动交易回调（由 main.py 注入）
_trade_executor_callback = None

# 市场状态惯性：{symbol: {"confirmed": "震荡行情", "pending": "趋势行情(上涨)", "count": 2}}
_regime_history: dict[str, dict] = {}
_REGIME_INERTIA = 3

# 后台任务引用集合，防止被 GC 回收
_background_tasks: set = set()

# 信号翻转过滤：{symbol: {"signal": "BUY", "time": 1708300000, "consecutive": 2}}
_signal_history: dict[str, dict] = {}
_FLIP_PENALTY = 15       # 翻转时置信度惩罚
_STABLE_BONUS = 5        # 连续同向时置信度奖励
_FLIP_WINDOW = 300       # 翻转检测时间窗口（秒）


def set_signal_broadcast_callback(callback):
    """设置信号广播回调函数（由 main.py 启动时调用）"""
    global _signal_broadcast_callback
    _signal_broadcast_callback = callback


def set_trade_executor_callback(callback):
    """设置自动交易回调函数（由 main.py 启动时调用）"""
    global _trade_executor_callback
    _trade_executor_callback = callback


def _build_market_data_text(market_data: dict) -> str:
    """将市场数据格式化为 AI 可读文本"""
    lines = [
        f"=== {market_data['symbol']} 市场数据 ===",
        f"最新价格: {market_data.get('latest_price', 'N/A')} USDT",
        f"资金费率: {market_data.get('funding_rate', 'N/A')}",
    ]

    oi = market_data.get("open_interest", {})
    lines.append(f"持仓量: {oi.get('open_interest', 'N/A')}")

    ls = market_data.get("long_short_ratio", {})
    lines.extend(
        [
            f"多头比例: {ls.get('long_ratio', 'N/A')}",
            f"空头比例: {ls.get('short_ratio', 'N/A')}",
            f"多空比: {ls.get('long_short_ratio', 'N/A')}",
        ]
    )

    return "\n".join(lines)


def _build_v3_retry_prompt(symbol: str, price: float, role_results: list) -> list:
    """构建 V3 二次裁决 prompt（R1 失败后的兜底）"""
    votes_summary = "\n".join(
        f"- {r['name']}({r['title']}): {r['signal']} 置信度{r['confidence']}%"
        for r in role_results
    )
    return [
        {
            "role": "system",
            "content": (
                "你是加密货币交易裁决者。根据分析师投票结果做最终决策。"
                "只输出纯 JSON，不要任何解释文字。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"币种: {symbol}，当前价格: {price} USDT\n"
                f"5位分析师投票结果:\n{votes_summary}\n\n"
                "综合以上投票，输出你的最终裁决（纯 JSON，无 markdown 包裹）:\n"
                '{"signal":"BUY/SELL/SHORT/COVER/HOLD",'
                '"confidence":0-100,'
                '"reason":"一句话理由",'
                '"risk_level":"低/中/高",'
                '"risk_assessment":"风险说明",'
                '"daily_quote":"一句鼓励语"}'
            ),
        },
    ]


async def _fetch_recent_accuracy(symbol: str, db: Optional[AsyncSession]) -> str:
    """查询该币种最近 10 个非 HOLD 信号的方向准确率，生成 prompt 注入文本"""
    if not db:
        return ""
    try:
        stmt = (
            select(AISignal.id, AISignal.signal, SignalResult.direction_result)
            .join(SignalResult, SignalResult.signal_id == AISignal.id)
            .where(
                AISignal.symbol == symbol,
                AISignal.signal.notin_(["HOLD"]),
                SignalResult.direction_result.in_(["CORRECT", "INCORRECT"]),
            )
            .order_by(AISignal.created_at.desc())
            .limit(10)
        )
        result = await db.execute(stmt)
        rows = result.all()
        if not rows:
            return ""

        correct = sum(1 for r in rows if r.direction_result == "CORRECT")
        incorrect = sum(1 for r in rows if r.direction_result == "INCORRECT")
        total = correct + incorrect
        if total == 0:
            return ""

        accuracy_pct = correct / total * 100
        text = f"\n【近期信号表现反馈】你最近 {total} 个 {symbol} 信号中，方向正确 {correct} 个，错误 {incorrect} 个（准确率 {accuracy_pct:.0f}%）。"
        if accuracy_pct < 40:
            text += f"\n⚠️ 你最近该币种的判断准确率偏低（{accuracy_pct:.0f}%），请更谨慎，降低置信度或给出 HOLD。"
        return text
    except Exception as e:
        logger.warning(f"[辩论] 查询 {symbol} 近期准确率失败: {e}")
        return ""


def _classify_market_regime(indicators: dict, symbol: str = "BTCUSDT") -> str:
    """用布林带宽度+ATR+均线排列判断市场状态，加惯性：连续N轮一致才切换"""
    try:
        raw_regime = classify_market_regime(indicators)

        # 惯性机制：连续 _REGIME_INERTIA 轮判定一致才正式切换
        hist = _regime_history.get(symbol, {"confirmed": raw_regime, "pending": raw_regime, "count": _REGIME_INERTIA})
        if raw_regime == hist["confirmed"]:
            hist["pending"] = raw_regime
            hist["count"] = _REGIME_INERTIA
            regime = raw_regime
            status_tag = ""
        elif raw_regime == hist["pending"]:
            hist["count"] += 1
            if hist["count"] >= _REGIME_INERTIA:
                hist["confirmed"] = raw_regime
                regime = raw_regime
                status_tag = "（刚确认切换）"
            else:
                regime = hist["confirmed"]
                status_tag = f"（检测到{raw_regime}，待确认 {hist['count']}/{_REGIME_INERTIA}）"
        else:
            hist["pending"] = raw_regime
            hist["count"] = 1
            regime = hist["confirmed"]
            status_tag = f"（检测到{raw_regime}，待确认 1/{_REGIME_INERTIA}）"
        _regime_history[symbol] = hist

        advice_map = {
            "剧烈波动": "市场波动剧烈，缩小仓位，拉宽止损，避免追涨杀跌",
            "震荡行情": "市场横盘震荡，适合高抛低吸，不追涨杀跌，触及支撑/阻力位再操作",
        }
        if regime.startswith("趋势行情"):
            d = "上涨" if "上涨" in regime else "下跌"
            advice = f"当前处于{d}趋势，应顺势持有，不要频繁反向操作"
        else:
            advice = advice_map.get(regime, "")

        return f"\n【市场状态】{regime}{status_tag}\n策略建议: {advice}"
    except Exception as e:
        logger.warning(f"[辩论] 判断市场状态失败: {e}")
        return ""


async def _fetch_btc_context(current_symbol: str) -> str:
    """查询比特币最近走势，为山寨币分析提供大哥方向参考"""
    if "BTC" in current_symbol.upper():
        return ""
    try:
        btc_data = await fetch_all_market_data("BTCUSDT")
        btc_price = btc_data.get("latest_price", 0)
        klines = btc_data.get("klines")
        if klines is None or klines.empty or btc_price <= 0:
            return ""

        close_1h_ago = float(klines["close"].iloc[-2]) if len(klines) >= 2 else btc_price
        close_4h_ago = float(klines["close"].iloc[-4]) if len(klines) >= 4 else btc_price
        change_1h = (btc_price - close_1h_ago) / close_1h_ago * 100
        change_4h = (btc_price - close_4h_ago) / close_4h_ago * 100

        direction = "上涨" if change_1h > 0.1 else ("下跌" if change_1h < -0.1 else "横盘")
        text = f"\n【大哥信号(BTC)】当前${btc_price:.0f}, 1h变化{change_1h:+.2f}%, 4h变化{change_4h:+.2f}%, 方向: {direction}"
        if abs(change_1h) > 1.0:
            text += f"\n⚠️ BTC 1小时{direction}{abs(change_1h):.1f}%，山寨币交易需考虑BTC联动"
        return text
    except Exception as e:
        logger.warning(f"[辩论] 查询BTC走势失败: {e}")
        return ""


def _build_timeframe_filter(indicators: dict) -> str:
    """多时间框架过滤器：15分钟给方向，1h/4h做否决权"""
    try:
        st = indicators.get("short_term", {})
        t4h = indicators.get("trend_4h", {})
        rsi_1h = indicators.get("rsi", 50)

        rsi_15m = st.get("rsi_15m", 50)
        macd_h_15m = st.get("macd_histogram_15m", 0)

        if rsi_15m > 55 and macd_h_15m > 0:
            short_dir = "看多"
        elif rsi_15m < 45 and macd_h_15m < 0:
            short_dir = "看空"
        else:
            short_dir = "中性"

        if rsi_1h > 55:
            mid_dir = "偏多"
        elif rsi_1h < 45:
            mid_dir = "偏空"
        else:
            mid_dir = "中性"

        trend_4h_str = t4h.get("trend_4h", "中性")
        if "多头" in trend_4h_str:
            long_dir = "多头"
        elif "空头" in trend_4h_str:
            long_dir = "空头"
        else:
            long_dir = "中性"

        lines = [f"\n【多周期信号】15分钟: {short_dir} | 1小时: {mid_dir} | 4小时: {long_dir}"]

        veto = ""
        if short_dir == "看多" and long_dir == "空头":
            veto = "⚠️ 15分钟看多但4小时空头趋势，做多需谨慎，大周期否决短线做多"
        elif short_dir == "看空" and long_dir == "多头":
            veto = "⚠️ 15分钟看空但4小时多头趋势，做空需谨慎，大周期否决短线做空"
        elif short_dir == "看多" and mid_dir == "偏空" and long_dir != "多头":
            veto = "⚠️ 15分钟看多但1小时偏空，短线反弹可能有限"
        elif short_dir == "看空" and mid_dir == "偏多" and long_dir != "空头":
            veto = "⚠️ 15分钟看空但1小时偏多，短线回调可能有限"

        if short_dir != "中性" and long_dir != "中性" and mid_dir != "中性":
            if (short_dir == "看多" and mid_dir == "偏多" and long_dir == "多头"):
                lines.append("✅ 三周期共振看多，做多信号强")
            elif (short_dir == "看空" and mid_dir == "偏空" and long_dir == "空头"):
                lines.append("✅ 三周期共振看空，做空信号强")

        if veto:
            lines.append(veto)

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[辩论] 多时间框架过滤失败: {e}")
        return ""


def _get_trading_session() -> str:
    """判断当前交易时段（北京时间）"""
    try:
        beijing_hour = (datetime.now(timezone.utc).hour + 8) % 24

        if 8 <= beijing_hour < 16:
            session = "亚洲盘"
            desc = "波动相对温和，适合稳健操作"
        elif 16 <= beijing_hour < 21:
            session = "欧洲盘"
            desc = "波动开始加大，注意趋势启动"
        else:
            session = "美国盘"
            desc = "波动最大、流动性最好，趋势行情多发"

        return f"\n【交易时段】当前{session}（北京时间{beijing_hour}点），{desc}"
    except Exception as e:
        logger.debug("[辩论] 交易时段检测失败: %s", e)
        return ""


async def _find_prev_same_symbol_id(symbol: str, db: AsyncSession) -> Optional[int]:
    """查找同币种最近一条信号的 ID"""
    try:
        stmt = (
            select(AISignal.id)
            .where(AISignal.symbol == symbol)
            .order_by(AISignal.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        return row
    except Exception as e:
        logger.debug("[辩论] 查询最近信号ID失败: %s", e)
        return None


async def run_debate(symbol: str, db: Optional[AsyncSession] = None) -> dict:
    """
    执行完整的 AI 辩论流程
    返回信号对象
    """
    logger.info(f"[辩论] 开始 {symbol} 辩论...")
    debate_start_time = time.time()
    stage_ts: dict[str, float] = {}

    # 1. 采集市场数据
    t0 = time.time()
    market_data = await fetch_all_market_data(symbol)
    latest_price = market_data.get("latest_price", 0)
    logger.info(f"[辩论] {symbol} 当前价格: {latest_price}")

    # 2. 计算技术指标
    klines_df = market_data.get("klines")
    indicators = {}
    indicators_text = f"[{symbol}] 指标数据暂不可用"

    if klines_df is not None and not klines_df.empty:
        indicators = calculate_indicators(klines_df)

        # 15 分钟短期指标
        klines_15m = market_data.get("klines_15m")
        if klines_15m is not None and not klines_15m.empty:
            indicators["short_term"] = calculate_short_term_indicators(klines_15m)

        # 价格走势上下文
        indicators["price_trend"] = calculate_price_trend_context(klines_df)

        # 4h 大周期趋势
        klines_4h = market_data.get("klines_4h")
        if klines_4h is not None and not klines_4h.empty:
            indicators["trend_4h"] = calculate_4h_trend(klines_4h)

        indicators_text = format_indicators_for_ai(indicators, symbol)

    stage_ts["fetch"] = round(time.time() - t0, 3)
    market_data_text = _build_market_data_text(market_data)

    # 2.5 注入持仓信息（让 AI 知道当前持仓，以便给出卖出信号）
    position_text = await build_position_text(symbol, latest_price)
    if position_text:
        market_data_text += "\n\n" + position_text

    # 2.6 代码预筛（影子模式）：只作为 prompt 参考 + 入库字段，不直接替代 AI 决策
    try:
        indicators_for_pf = dict(indicators or {})
        indicators_for_pf["price"] = latest_price
        pf_result = pre_filter(indicators_for_pf, position=None)
        pf_context = pf_result.to_prompt_text()
    except Exception as e:
        logger.warning(f"[预筛] {symbol} pre_filter 失败（不影响主流程）: {e}")
        pf_result = None
        pf_context = None

    # 3. 5 角色并发分析
    t_roles = time.time()
    role_results = await analyze_all_roles(
        symbol, latest_price, indicators_text, market_data_text, pre_filter_context=pf_context
    )

    stage_ts["roles"] = round(time.time() - t_roles, 3)

    all_role_failed = all((r.get("confidence", 0) <= 0) for r in role_results)
    if all_role_failed:
        logger.error(f"[辩论] {symbol} 所有角色分析失败")
        debate_duration = (time.time() - debate_start_time) * 1000
        stage_ts["total"] = round(debate_duration / 1000, 3)
        await metrics_collector.record_debate_analysis(
            symbol=symbol,
            num_roles=len(ROLES),
            duration_ms=debate_duration,
            success=False,
        )
        fail_obj = {
            "symbol": symbol,
            "signal": "HOLD",
            "confidence": 0,
            "price_at_signal": latest_price,
            "role_opinions": role_results,
            "debate_log": "角色分析全部失败",
            "final_reason": "分析服务暂时不可用，请稍后重试",
            "risk_level": "高",
            "risk_assessment": "分析引擎异常，当前结果不可作为交易依据。",
            "daily_quote": "耐心等待，比盲目出手更重要。",
            "voice_text": f"{symbol} 分析暂不可用",
        }
        if db:
            try:
                prev_id = await _find_prev_same_symbol_id(symbol, db)
                db_signal = AISignal(
                    symbol=symbol, signal="HOLD", confidence=0,
                    price_at_signal=latest_price,
                    role_opinions=json.dumps(role_results, ensure_ascii=False),
                    debate_log="角色分析全部失败",
                    final_reason=fail_obj["final_reason"],
                    risk_level="高",
                    risk_assessment=fail_obj["risk_assessment"],
                    daily_quote=fail_obj["daily_quote"],
                    voice_text=fail_obj["voice_text"],
                    error_text="all_roles_failed",
                    stage_timestamps=json.dumps(stage_ts, ensure_ascii=False),
                    prev_same_symbol_id=prev_id,
                )
                db.add(db_signal)
                await db.commit()
                await db.refresh(db_signal)
                fail_obj["id"] = db_signal.id
            except Exception as e:
                logger.error(f"[辩论] 保存失败信号失败: {e}")
                await db.rollback()
        return fail_obj

    # 检查是否所有角色都因配额不足而失败
    quota_failed = sum(1 for r in role_results if "配额不足" in r.get("analysis", ""))
    if quota_failed == len(ROLES):
        logger.error(f"[辩论] {symbol} 所有角色因配额不足失败")
        debate_duration = (time.time() - debate_start_time) * 1000
        stage_ts["total"] = round(debate_duration / 1000, 3)
        await metrics_collector.record_debate_analysis(
            symbol=symbol,
            num_roles=len(ROLES),
            duration_ms=debate_duration,
            success=False,
        )
        quota_obj = {
            "symbol": symbol,
            "signal": "HOLD",
            "confidence": 0,
            "price_at_signal": latest_price,
            "role_opinions": role_results,
            "debate_log": "配额不足，无法进行分析",
            "final_reason": "API 配额已耗尽，请明日再试或联系管理员",
            "risk_level": "高",
            "risk_assessment": "系统配额不足，无法完成分析。",
            "daily_quote": "休息是为了更好的出发。",
            "voice_text": f"{symbol} 分析因配额不足暂停",
        }
        if db:
            try:
                prev_id = await _find_prev_same_symbol_id(symbol, db)
                db_signal = AISignal(
                    symbol=symbol, signal="HOLD", confidence=0,
                    price_at_signal=latest_price,
                    role_opinions=json.dumps(role_results, ensure_ascii=False),
                    debate_log="配额不足，无法进行分析",
                    final_reason=quota_obj["final_reason"],
                    risk_level="高",
                    risk_assessment=quota_obj["risk_assessment"],
                    daily_quote=quota_obj["daily_quote"],
                    voice_text=quota_obj["voice_text"],
                    error_text="quota_exhausted",
                    stage_timestamps=json.dumps(stage_ts, ensure_ascii=False),
                    prev_same_symbol_id=prev_id,
                )
                db.add(db_signal)
                await db.commit()
                await db.refresh(db_signal)
                quota_obj["id"] = db_signal.id
            except Exception as e:
                logger.error(f"[辩论] 保存配额不足信号失败: {e}")
                await db.rollback()
        return quota_obj

    # 4. 注入近期信号准确率反馈
    accuracy_text = await _fetch_recent_accuracy(symbol, db)
    pf_context_with_feedback = (pf_context or "") + accuracy_text

    # 4.1 最强大脑：注入多维认知上下文
    pnl_text = await fetch_recent_trade_pnl(symbol, db)
    loss_text, loss_streak, loss_dir = await fetch_loss_streak(symbol, db)
    freq_text = await fetch_trade_frequency(symbol, db)
    global_pos_text = await fetch_global_positions(symbol)
    regime_text = _classify_market_regime(indicators or {}, symbol)
    btc_text = await _fetch_btc_context(symbol)
    session_text = _get_trading_session()
    win_text = await fetch_winning_patterns(symbol, db)
    pos_age_text = await fetch_position_age(symbol)

    tf_filter_text = _build_timeframe_filter(indicators or {})

    superbrain_context = pnl_text + loss_text + freq_text + global_pos_text + regime_text + tf_filter_text + btc_text + session_text + win_text + pos_age_text
    if superbrain_context.strip():
        pf_context_with_feedback += "\n\n=== 最强大脑认知上下文 ===" + superbrain_context

    # 查询上一次该币种的 AI 决策（非 HOLD），用于决策连贯性参考
    last_decision_text = ""
    try:
        if db:
            last_stmt = (
                select(AISignal)
                .where(AISignal.symbol == symbol, AISignal.signal != "HOLD")
                .order_by(AISignal.created_at.desc())
                .limit(1)
            )
            last_result = await db.execute(last_stmt)
            last_sig = last_result.scalar_one_or_none()
            if last_sig:
                last_decision_text = (
                    f"上一次决策: {last_sig.signal}(置信度{last_sig.confidence}%)，"
                    f"理由: {(last_sig.final_reason or '')[:200]}"
                )
    except Exception as e:
        logger.warning(f"[辩论] 查询 {symbol} 历史决策失败: {e}")

    # R1 裁决（传入 symbol 用于配额追踪）
    t_r1 = time.time()
    final_messages = build_final_judgment_prompt(
        symbol, latest_price, role_results,
        pre_filter_context=pf_context_with_feedback or None,
        last_decision=last_decision_text,
    )
    try:
        raw_judgment = await asyncio.wait_for(
            deepseek_client.reason(final_messages, symbol=symbol),
            timeout=300,  # 5 分钟超时
        )
    except asyncio.TimeoutError:
        logger.warning(f"[辩论] {symbol} R1 裁决超时（300秒），跳过 R1 阶段")
        raw_judgment = None

    stage_ts["r1"] = round(time.time() - t_r1, 3)

    # 5. 解析裁决 JSON
    judgment = _parse_json_from_text(raw_judgment)

    # 降级逻辑：R1 失败 → V3 二次裁决 → 加权投票
    if not judgment:
        logger.warning(f"[辩论] R1 JSON 解析失败，尝试 V3 二次裁决（原始回复前100字: {(raw_judgment or '')[:100]}）")
        # V3 二次裁决：用短 prompt 要求纯 JSON 输出
        v3_retry_prompt = _build_v3_retry_prompt(symbol, latest_price, role_results)
        try:
            v3_raw = await deepseek_client.chat_v3(v3_retry_prompt, temperature=0.3, symbol=symbol)
            judgment = _parse_json_from_text(v3_raw)
            if judgment:
                logger.info(f"[辩论] V3 二次裁决成功: {judgment.get('signal')} / {judgment.get('confidence')}%")
        except Exception as e:
            logger.warning(f"[辩论] V3 二次裁决异常: {e}")

    # 终极降级：V3 也失败时用置信度加权投票
    if not judgment:
        logger.warning("[辩论] V3 二次裁决也失败，使用置信度加权投票")
        sell_count = sum(1 for r in role_results if r["signal"] == "SELL")
        cover_count = sum(1 for r in role_results if r["signal"] == "COVER")
        hold_count = sum(1 for r in role_results if r["signal"] == "HOLD")
        buy_score = sum(r["confidence"] for r in role_results if r["signal"] == "BUY")
        short_score = sum(r["confidence"] for r in role_results if r["signal"] == "SHORT")
        sell_score = sum(r["confidence"] for r in role_results if r["signal"] == "SELL")
        cover_score = sum(r["confidence"] for r in role_results if r["signal"] == "COVER")
        avg_confidence = sum(r["confidence"] for r in role_results) / max(len(role_results), 1)

        risk_chen = next((r for r in role_results if r.get("name") == "风控老陈"), None)
        risk_veto = False  # 方案C：移除风控硬否决

        if hold_count >= 5:
            signal = "HOLD"
        elif sell_count >= 2 or sell_score >= 130:
            signal = "SELL"
        elif cover_count >= 2 or cover_score >= 130:
            signal = "COVER"
        elif buy_score > short_score and (buy_score - short_score) > 30:
            signal = "BUY"
        elif short_score > buy_score and (short_score - buy_score) > 30:
            signal = "SHORT"
        else:
            signal = "HOLD"

        reason_parts = [f"加权得分: BUY={buy_score} SHORT={short_score} SELL={sell_score} COVER={cover_score}"]
        if risk_veto:
            reason_parts.append("风控老陈一票否决")
        reason_parts.append("（R1+V3 均解析失败，降级为加权投票）")

        judgment = {
            "signal": signal,
            "confidence": int(avg_confidence),
            "reason": "，".join(reason_parts),
            "risk_level": "中",
            "risk_assessment": "AI裁决器出现技术问题，已降级为置信度加权投票。请注意加密货币市场本身具有较高波动性，投资有风险，入市需谨慎。",
            "daily_quote": "市场永远是对的，但判断需要时间验证。",
            "_degraded": True,
            "_degraded_reason": "R1+V3均解析失败，降级为加权投票",
        }

    # 构建辩论日志
    debate_log = ""
    for r in role_results:
        debate_log += f"【{r['emoji']} {r['name']}】信号: {r['signal']} | 置信度: {r['confidence']}%\n"
        debate_log += f"{r['analysis'][:200]}...\n\n"

    # 生成语音播报文本（移除具体交易参数）
    voice_text = generate_voice_text(
        {
            "symbol": symbol,
            "signal": judgment.get("signal", "HOLD"),
            "confidence": judgment.get("confidence", 50),
            "risk_level": judgment.get("risk_level", "中"),
        }
    )

    # 构建信号对象
    signal_obj = {
        "symbol": symbol,
        "signal": judgment.get("signal", "HOLD"),
        "confidence": judgment.get("confidence", 50),
        "price_at_signal": latest_price,
        "role_opinions": role_results,
        "debate_log": debate_log,
        "final_reason": judgment.get("reason", ""),
        "risk_level": judgment.get("risk_level", "中"),
        "risk_assessment": judgment.get("risk_assessment", ""),
        "daily_quote": judgment.get("daily_quote", ""),
        "voice_text": voice_text,
        "indicators": indicators,
    }

    # 附加 ATR 百分比供交易执行器动态止盈止损使用
    atr_val = (indicators or {}).get("atr", 0)
    sig_price = latest_price or 1
    signal_obj["atr_pct"] = round((atr_val / sig_price * 100), 4) if sig_price > 0 and atr_val > 0 else 0

    # 影子字段附加到返回对象（便于前端/归因）
    if pf_result:
        signal_obj.update(pf_result.to_db_fields())
        signal_obj["pf_agreed_with_ai"] = pf_result.direction == signal_obj["signal"]

    # --- 方案2：信号翻转过滤 ---
    cur_signal = signal_obj["signal"]
    if cur_signal != "HOLD":
        _bullish = {"BUY", "COVER"}
        _bearish = {"SELL", "SHORT"}
        cur_side = "bull" if cur_signal in _bullish else "bear"
        hist = _signal_history.get(symbol)
        now_ts = time.time()

        if hist and (now_ts - hist["time"]) < _FLIP_WINDOW:
            prev_side = "bull" if hist["signal"] in _bullish else "bear"
            if cur_side != prev_side:
                old_conf = signal_obj["confidence"]
                signal_obj["confidence"] = max(0, old_conf - _FLIP_PENALTY)
                logger.info(f"[翻转过滤] {symbol} {hist['signal']}->{cur_signal} 方向翻转，置信度 {old_conf}->{signal_obj['confidence']}（-{_FLIP_PENALTY}）")
                _signal_history[symbol] = {"signal": cur_signal, "time": now_ts, "consecutive": 1}
            else:
                consec = hist.get("consecutive", 1) + 1
                if consec >= 2:
                    old_conf = signal_obj["confidence"]
                    signal_obj["confidence"] = min(100, old_conf + _STABLE_BONUS)
                    logger.info(f"[信号稳定] {symbol} 连续{consec}轮{cur_signal}，置信度 {old_conf}->{signal_obj['confidence']}（+{_STABLE_BONUS}）")
                _signal_history[symbol] = {"signal": cur_signal, "time": now_ts, "consecutive": consec}
        else:
            _signal_history[symbol] = {"signal": cur_signal, "time": now_ts, "consecutive": 1}

    # --- 方案6：预筛选分歧利用 ---
    if cur_signal != "HOLD" and pf_result:
        pf_agreed = signal_obj.get("pf_agreed_with_ai", False)
        pf_level = pf_result.level if pf_result else "WEAK"
        old_conf = signal_obj["confidence"]
        if pf_agreed and pf_level == "STRONG":
            signal_obj["confidence"] = min(100, old_conf + 10)
            logger.info(f"[预筛加分] {symbol} 预筛STRONG且一致，置信度 {old_conf}->{signal_obj['confidence']}（+10）")
        elif pf_agreed:
            signal_obj["confidence"] = min(100, old_conf + 5)
            logger.info(f"[预筛加分] {symbol} 预筛一致，置信度 {old_conf}->{signal_obj['confidence']}（+5）")
        else:
            signal_obj["confidence"] = max(0, old_conf - 5)
            logger.info(f"[预筛减分] {symbol} 预筛与AI分歧，置信度 {old_conf}->{signal_obj['confidence']}（-5）")

    # RiskGate：必要时把交易信号降级为 HOLD（仍会入库，便于复盘）
    if db:
        try:
            signal_obj = await apply_risk_gate(signal_obj, db)
            # C-04：标记该信号已经过 RiskGate 检查，executor 凭此标记才允许执行
            signal_obj = dict(signal_obj)
            signal_obj["_risk_gate_passed"] = True
        except Exception as e:
            logger.error(f"[RiskGate] {symbol} 检查异常，强制降级为 HOLD 以保护资金安全: {e}")
            signal_obj = dict(signal_obj)
            signal_obj["signal"] = "HOLD"
            signal_obj["confidence"] = 0
            signal_obj["_risk_gate_passed"] = False
            signal_obj["final_reason"] = (
                (signal_obj.get("final_reason", "") or "")
                + f"\n[RiskGate:ERROR] 风控检查异常，强制HOLD: {e}"
            )
            signal_obj["risk_level"] = "高"

    # BUY/SELL/SHORT/COVER 才推送 WebSocket、触发交易、发 Telegram；HOLD 只存库不推送
    emit_signal = signal_obj.get("signal") in ("BUY", "SELL", "SHORT", "COVER")

    # 6. 存数据库（所有信号都保存，包括 HOLD，方便追踪 AI 活跃度）
    stage_ts["total"] = round((time.time() - debate_start_time), 3)
    if db:
        try:
            role_inputs_for_db = [
                {
                    "role_id": r.get("role_id"),
                    "name": r.get("name"),
                    "messages": r.get("input_messages", []),
                }
                for r in role_results
            ]
            prev_id = await _find_prev_same_symbol_id(symbol, db)
            degraded_reason = judgment.get("_degraded_reason") if judgment.get("_degraded") else None
            db_signal = AISignal(
                symbol=symbol,
                signal=signal_obj["signal"],
                confidence=signal_obj["confidence"],
                price_at_signal=latest_price,
                role_opinions=json.dumps(role_results, ensure_ascii=False),
                role_input_messages=json.dumps(role_inputs_for_db, ensure_ascii=False),
                final_input_messages=json.dumps(final_messages, ensure_ascii=False),
                final_raw_output=raw_judgment or "",
                debate_log=debate_log,
                final_reason=signal_obj["final_reason"],
                risk_level=signal_obj["risk_level"],
                risk_assessment=signal_obj["risk_assessment"],
                daily_quote=signal_obj["daily_quote"],
                voice_text=voice_text,
                pf_direction=signal_obj.get("pf_direction"),
                pf_score=signal_obj.get("pf_score"),
                pf_level=signal_obj.get("pf_level"),
                pf_reasons=signal_obj.get("pf_reasons"),
                pf_agreed_with_ai=signal_obj.get("pf_agreed_with_ai"),
                prev_same_symbol_id=prev_id,
                error_text=degraded_reason,
                stage_timestamps=json.dumps(stage_ts, ensure_ascii=False),
            )
            db.add(db_signal)
            await db.commit()
            await db.refresh(db_signal)
            signal_obj["id"] = db_signal.id
            signal_obj["created_at"] = db_signal.created_at.isoformat() + "Z"
            logger.info(f"[辩论] 信号已保存到数据库，ID: {db_signal.id}")
        except Exception as e:
            logger.error(f"[辩论] 保存信号失败: {e}")
            await db.rollback()

    # 记录辩论指标
    debate_duration = (time.time() - debate_start_time) * 1000
    await metrics_collector.record_debate_analysis(
        symbol=symbol,
        num_roles=len(ROLES),
        duration_ms=debate_duration,
        success=True,
    )

    # 记录信号生成指标
    await metrics_collector.record_signal(
        symbol=symbol,
        signal=signal_obj["signal"],
        confidence=signal_obj["confidence"],
        duration_ms=debate_duration,
        success=True,
    )

    logger.info(
        f"[辩论] {symbol} 辩论完成 -> {signal_obj['signal']} (置信度: {signal_obj['confidence']}%), 耗时: {debate_duration:.0f}ms"
    )

    # #80 修复：广播信号到 WebSocket 客户端（用 create_task + 异常回调）
    callback = _signal_broadcast_callback
    if emit_signal and callback:
        try:

            async def _safe_broadcast():
                try:
                    assert callback is not None
                    await callback(signal_obj)
                    logger.info("[辩论] 信号已推送到 WebSocket 客户端")
                except Exception as exc:
                    logger.warning(f"[辩论] 信号推送失败: {exc}")

            task = asyncio.create_task(_safe_broadcast())
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
        except Exception as e:
            logger.warning(f"[辩论] 创建推送任务失败: {e}")

    # 自动交易：信号为 BUY/SELL 时触发交易执行
    trade_cb = _trade_executor_callback
    if emit_signal and trade_cb:
        try:

            async def _safe_trade():
                try:
                    assert trade_cb is not None
                    await trade_cb(signal_obj)
                    logger.info("[辩论] 自动交易回调已执行")
                except Exception as exc:
                    logger.warning(f"[辩论] 自动交易回调失败（不影响主流程）: {exc}")

            task = asyncio.create_task(_safe_trade())
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
        except Exception as e:
            logger.warning(f"[辩论] 创建交易任务失败: {e}")

    # #77 修复：Telegram 推送独立 try/except，不影响主流程返回
    if emit_signal:
        try:
            sig_cn = {"BUY": "🟢 开多", "SELL": "🔴 平多", "SHORT": "🔻 开空", "COVER": "🔺 平空"}.get(signal_obj["signal"], "")
            reason_preview = (signal_obj.get("final_reason", "") or "")[:100]
            tg_text = (
                f"<b>⚡ 钢子出击 - 新信号</b>\n\n"
                f"币种: <b>{symbol}</b>\n"
                f"信号: {sig_cn}\n"
                f"置信度: <b>{signal_obj['confidence']}%</b>\n"
                f"价格: ${latest_price}\n"
                f"风险: {signal_obj['risk_level']}\n\n"
                f"💡 {reason_preview}\n\n"
                f"<i>⚠️ 免责声明：本分析仅供参考，不构成投资建议。加密货币投资有风险，入市需谨慎。</i>"
            )
            await send_telegram_message(tg_text)
        except Exception as e:
            logger.warning(f"[辩论] Telegram 推送失败（不影响信号结果）: {e}")
    else:
        logger.info(f"[辩论] {symbol} 信号为 HOLD，已跳过推送（Telegram/WS）")

    return signal_obj
