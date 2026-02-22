"""
钢子出击 - AI 分析路由
信号查询、辩论触发、方向一致性统计
"""
# pyright: reportMissingImports=false

import json
import time
import logging
from datetime import datetime, timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, text, func, Integer

from ..auth.jwt_utils import get_current_user
from ..database.db import get_db
from ..database.models import AISignal, SignalSnapshot
from backend.trading.models import TradeRecord
from backend.trading.pnl import pair_trades
from backend.signal_engine.engine import generate_signal
from .signal_history import get_direction_consistency_stats
from ..market.binance_ws import SYMBOLS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["AI 分析"])


def _ok(payload: dict[str, Any]) -> dict[str, Any]:
    """统一响应格式：兼容旧字段 + 新增 success/data 包装。"""
    return {"success": True, "data": payload, **payload}


def _safe_parse_opinions(raw: Any) -> list[Any]:
    """#2 修复：安全解析 role_opinions JSON，损坏数据不崩溃"""
    if not raw:
        return []
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _safe_parse_json(raw: Any, fallback: Any) -> Any:
    if raw is None or raw == "":
        return fallback
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return fallback


def _safe_iso_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat() + "Z"
    if isinstance(value, str):
        return value if value.endswith("Z") else value + "Z" if value else ""
    return ""


def _serialize_signal(signal: AISignal) -> dict[str, Any]:
    return {
        "id": signal.id,
        "symbol": signal.symbol,
        "signal": signal.signal,
        "confidence": signal.confidence,
        "price_at_signal": signal.price_at_signal,
        "role_opinions": _safe_parse_opinions(getattr(signal, "role_opinions", "")),
        "role_input_messages": _safe_parse_json(getattr(signal, "role_input_messages", None), []),
        "final_input_messages": _safe_parse_json(getattr(signal, "final_input_messages", None), []),
        "final_raw_output": getattr(signal, "final_raw_output", "") or "",
        "debate_log": getattr(signal, "debate_log", ""),
        "final_reason": getattr(signal, "final_reason", ""),
        "risk_assessment": getattr(signal, "risk_assessment", ""),
        "risk_level": getattr(signal, "risk_level", ""),
        # Phase B：双轨字段（pre-filter shadow）
        "pf_direction": getattr(signal, "pf_direction", None),
        "pf_score": getattr(signal, "pf_score", None),
        "pf_level": getattr(signal, "pf_level", None),
        "pf_reasons": getattr(signal, "pf_reasons", None),
        "pf_agreed_with_ai": getattr(signal, "pf_agreed_with_ai", None),
        "daily_quote": getattr(signal, "daily_quote", ""),
        "voice_text": getattr(signal, "voice_text", ""),
        # 批次/链路/错误/耗时
        "batch_id": getattr(signal, "batch_id", None),
        "prev_same_symbol_id": getattr(signal, "prev_same_symbol_id", None),
        "error_text": getattr(signal, "error_text", None),
        "stage_timestamps": _safe_parse_json(getattr(signal, "stage_timestamps", None), {}),
        "created_at": _safe_iso_datetime(getattr(signal, "created_at", None)),
    }


class AnalyzeRequest(BaseModel):
    """分析请求"""

    symbol: str = "BTCUSDT"


async def _check_is_initializing(db: AsyncSession, symbol: str) -> bool:
    """
    检查系统是否正在初始化分析中

    判断逻辑：
    1. 数据库中没有任何该币种的信号记录
    2. 且 analyze_cooldowns 表中有该币种的记录（表示分析正在进行）
    """
    try:
        # 检查是否有信号记录
        signal_result = await db.execute(
            select(AISignal).where(AISignal.symbol == symbol.upper()).limit(1)
        )
        has_signal = signal_result.scalar_one_or_none() is not None

        if has_signal:
            return False

        # 检查是否正在分析中（通过冷却表判断）
        cooldown_result = await db.execute(
            text(
                "SELECT last_analyze_ts FROM analyze_cooldowns WHERE symbol = :symbol"
            ),
            {"symbol": symbol.upper()},
        )
        cooldown = cooldown_result.scalar_one_or_none()

        if cooldown:
            # 如果冷却记录在60秒内，认为正在初始化
            last_time = float(cooldown) if isinstance(cooldown, (int, float)) else 0
            return (time.time() - last_time) < 60

        return False
    except Exception as e:
        logger.debug("[AI路由] 初始化状态检查失败: %s", e)
        return False


@router.get("/latest-signal")
async def get_latest_signal(
    symbol: str = "BTCUSDT",
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取某币种最新 AI 信号"""
    result = await db.execute(
        select(AISignal)
        .where(AISignal.symbol == symbol.upper())
        .order_by(desc(AISignal.created_at))
        .limit(1)
    )
    signal = result.scalar_one_or_none()

    if not signal:
        # 检查是否正在初始化中
        is_initializing = await _check_is_initializing(db, symbol)

        return _ok(
            {
                "message": "暂无信号",
                "signal": None,
                "is_initializing": is_initializing,
                "init_hint": "首次分析预计需要 30-60 秒" if is_initializing else None,
            }
        )

    return _ok({"signal": _serialize_signal(signal)})


@router.get("/latest-signals")
async def get_latest_signals(
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取所有币种的最新信号"""
    signals = {}
    for symbol in SYMBOLS:
        result = await db.execute(
            select(AISignal)
            .where(AISignal.symbol == symbol)
            .order_by(desc(AISignal.created_at))
            .limit(1)
        )
        sig = result.scalar_one_or_none()
        if sig:
            signals[symbol] = {
                "id": sig.id,
                "signal": sig.signal,
                "confidence": sig.confidence,
                "price_at_signal": sig.price_at_signal,
                "created_at": _safe_iso_datetime(getattr(sig, "created_at", None)),
            }

    return _ok({"signals": signals})


@router.get("/debate/{symbol}")
async def get_debate(
    symbol: str,
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取某币种最新辩论详情"""
    result = await db.execute(
        select(AISignal)
        .where(AISignal.symbol == symbol.upper())
        .order_by(desc(AISignal.created_at))
        .limit(1)
    )
    signal = result.scalar_one_or_none()

    if not signal:
        return _ok({"message": "暂无辩论记录", "debate": None})

    return _ok({"debate": _serialize_signal(signal)})


@router.get("/history")
async def get_history(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取信号历史（过滤 HOLD，只返回 BUY/SELL）"""
    offset = (page - 1) * limit
    # 只返回 BUY/SELL 信号给前端
    result = await db.execute(
        select(AISignal)
        .where(AISignal.signal.in_(["BUY", "SELL"]))
        .order_by(desc(AISignal.created_at))
        .offset(offset)
        .limit(limit)
    )
    signals = result.scalars().all()
    total_result = await db.execute(
        select(func.count()).select_from(AISignal).where(AISignal.signal.in_(["BUY", "SELL"]))
    )
    total = int(total_result.scalar() or 0)

    # 附带 AI 最后一次分析时间（包括 HOLD），让前端知道 AI 在工作
    last_any_result = await db.execute(
        select(AISignal.created_at).order_by(desc(AISignal.created_at)).limit(1)
    )
    last_any_at = last_any_result.scalar_one_or_none()
    last_analysis_at = _safe_iso_datetime(last_any_at) if last_any_at else None

    # #57 修复：role_opinions 统一返回 parsed JSON array，而非原始 string
    def _serialize_history_signal(s: AISignal) -> dict[str, Any]:
        return {
            "id": s.id,
            "symbol": s.symbol,
            "signal": s.signal,
            "confidence": s.confidence,
            "price_at_signal": s.price_at_signal,
            "risk_level": getattr(s, "risk_level", ""),
            "role_opinions": _safe_parse_opinions(getattr(s, "role_opinions", "")),
            "created_at": _safe_iso_datetime(getattr(s, "created_at", None)),
        }

    return _ok(
        {
            "history": [_serialize_history_signal(s) for s in signals],
            "last_analysis_at": last_analysis_at,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "has_next": offset + limit < total,
            },
        }
    )


@router.get("/history-all")
async def get_history_all(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    symbol: str | None = Query(default=None, description="可选：按币种过滤，如 BTCUSDT"),
    signal_filter: str | None = Query(default=None, alias="signal", description="可选：按信号过滤，如 BUY/SELL/HOLD"),
    keyword: str | None = Query(default=None, description="可选：全文搜索关键词"),
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取 AI 分析流水（不做信号过滤：包含 HOLD / BUY / SELL / SHORT / COVER ...）

    注意：这是给“AI 分析”页展示“完整信息”的接口，返回字段比 /history 更多（含 debate_log 等）。
    """
    offset = (page - 1) * limit
    q = select(AISignal)
    if symbol:
        q = q.where(AISignal.symbol == symbol.upper())
    if signal_filter:
        q = q.where(AISignal.signal == signal_filter.upper())
    if keyword:
        kw_pattern = f"%{keyword}%"
        q = q.where(
            AISignal.final_reason.ilike(kw_pattern)
            | AISignal.debate_log.ilike(kw_pattern)
            | AISignal.final_raw_output.ilike(kw_pattern)
        )

    result = await db.execute(
        q.order_by(desc(AISignal.created_at)).offset(offset).limit(limit)
    )
    signals = result.scalars().all()

    # v1.1: 批量关联 signal_snapshots 获取增补字段
    sig_ids = [s.id for s in signals]
    snapshot_map = {}
    if sig_ids:
        snap_result = await db.execute(
            select(SignalSnapshot.signal_id, SignalSnapshot.horizon, SignalSnapshot.final_decision)
            .where(SignalSnapshot.signal_id.in_(sig_ids))
        )
        for snap in snap_result.all():
            try:
                fd = json.loads(snap.final_decision) if snap.final_decision else {}
            except Exception as e:
                logger.debug("[AI路由] final_decision JSON 解析失败: %s", e)
                fd = {}
            snapshot_map[snap.signal_id] = {
                "horizon": snap.horizon or fd.get("horizon"),
                "reason_bullets": fd.get("reason_bullets", []),
                "key_levels": fd.get("key_levels", {}),
                "entry_plan": fd.get("entry_plan", {}),
                "invalidations": fd.get("invalidations", []),
                "rr_estimate": fd.get("rr_estimate"),
                "position_advice": fd.get("position_advice", {}),
                "evidence": fd.get("evidence", {}),
            }

    # 批量关联 trade_records：signal_id -> {status, error_msg}
    trade_map: dict[int, dict] = {}
    sig_ids = [s.id for s in signals if s.id]
    if sig_ids:
        tr_result = await db.execute(
            select(TradeRecord.signal_id, TradeRecord.status, TradeRecord.error_msg, TradeRecord.side, TradeRecord.created_at)
            .where(TradeRecord.signal_id.in_(sig_ids))
            .order_by(desc(TradeRecord.created_at))
        )
        for tr in tr_result.all():
            sid = tr.signal_id
            if sid is None:
                continue
            existing = trade_map.get(sid)
            _priority = {"filled": 3, "failed": 2, "skipped": 1, "pending": 0}
            if existing is None or _priority.get(tr.status, 0) > _priority.get(existing["status"], 0):
                trade_map[sid] = {
                    "status": tr.status,
                    "error_msg": tr.error_msg or "",
                    "side": tr.side or "",
                }

    total_q = select(func.count()).select_from(AISignal)
    if symbol:
        total_q = total_q.where(AISignal.symbol == symbol.upper())
    if signal_filter:
        total_q = total_q.where(AISignal.signal == signal_filter.upper())
    if keyword:
        kw_pattern = f"%{keyword}%"
        total_q = total_q.where(
            AISignal.final_reason.ilike(kw_pattern)
            | AISignal.debate_log.ilike(kw_pattern)
            | AISignal.final_raw_output.ilike(kw_pattern)
        )
    total_result = await db.execute(total_q)
    total = int(total_result.scalar() or 0)

    last_any_result = await db.execute(
        select(AISignal.created_at).order_by(desc(AISignal.created_at)).limit(1)
    )
    last_any_at = last_any_result.scalar_one_or_none()
    last_analysis_at = _safe_iso_datetime(last_any_at) if last_any_at else None

    def _enrich(s: AISignal) -> dict:
        d = _serialize_signal(s)
        ti = trade_map.get(s.id)
        if ti:
            d["trade_status"] = ti["status"]
            d["trade_skip_reason"] = ti["error_msg"]
        else:
            sig = str(s.signal or "").upper()
            if sig in ("BUY", "SELL", "SHORT", "COVER"):
                d["trade_status"] = "no_record"
                # v1.1: 推断具体未执行原因
                from backend.config import settings as _cfg
                _allowed = [x.strip() for x in _cfg.TRADE_SYMBOLS.split(",") if x.strip()]
                _conf = int(s.confidence or 0)
                if s.symbol and s.symbol not in _allowed:
                    d["trade_skip_reason"] = f"非交易币种 (仅允许 {','.join(_allowed)})"
                elif sig in ("BUY", "COVER") and _conf < _cfg.TRADE_MIN_CONF_BUY:
                    d["trade_skip_reason"] = f"置信度不足: {_conf}% < {_cfg.TRADE_MIN_CONF_BUY}%(BUY)"
                elif sig == "SHORT" and _conf < _cfg.TRADE_MIN_CONF_SHORT:
                    d["trade_skip_reason"] = f"置信度不足: {_conf}% < {_cfg.TRADE_MIN_CONF_SHORT}%(SHORT)"
                elif sig == "SELL" and _conf < _cfg.TRADE_MIN_CONF_SELL:
                    d["trade_skip_reason"] = f"置信度不足: {_conf}% < {_cfg.TRADE_MIN_CONF_SELL}%(SELL)"
                else:
                    d["trade_skip_reason"] = "未触发交易（冷却/限额/持仓限制等）"
            else:
                d["trade_status"] = None
                d["trade_skip_reason"] = ""
        # v1.1 增补字段（来自 signal_snapshots）
        v11 = snapshot_map.get(s.id, {})
        d["v11_horizon"] = v11.get("horizon")
        d["v11_reason_bullets"] = v11.get("reason_bullets", [])
        d["v11_key_levels"] = v11.get("key_levels", {})
        d["v11_entry_plan"] = v11.get("entry_plan", {})
        d["v11_invalidations"] = v11.get("invalidations", [])
        d["v11_rr_estimate"] = v11.get("rr_estimate")
        d["v11_position_advice"] = v11.get("position_advice", {})
        d["v11_evidence"] = v11.get("evidence", {})
        return d

    return _ok(
        {
            "history": [_enrich(s) for s in signals],
            "last_analysis_at": last_analysis_at,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "has_next": offset + limit < total,
            },
        }
    )


@router.get("/history-item/{signal_id}")
async def get_history_item(
    signal_id: int,
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单条 AI 分析详情（含完整输入输出字段）"""
    result = await db.execute(
        select(AISignal).where(AISignal.id == signal_id).limit(1)
    )
    signal = result.scalar_one_or_none()
    if not signal:
        raise HTTPException(status_code=404, detail="记录不存在")

    item = _serialize_signal(signal)

    tr_result = await db.execute(
        select(TradeRecord.status, TradeRecord.error_msg, TradeRecord.side, TradeRecord.created_at)
        .where(TradeRecord.signal_id == signal_id)
        .order_by(desc(TradeRecord.created_at))
    )
    trade_rows = tr_result.all()
    if trade_rows:
        _priority = {"filled": 3, "failed": 2, "skipped": 1, "pending": 0}
        best = max(trade_rows, key=lambda r: _priority.get(r.status, 0))
        item["trade_status"] = best.status
        item["trade_skip_reason"] = best.error_msg or ""
    else:
        sig = str(signal.signal or "").upper()
        if sig in ("BUY", "SELL", "SHORT", "COVER"):
            item["trade_status"] = "no_record"
            item["trade_skip_reason"] = "未触发交易（冷却/限额/持仓限制等）"
        else:
            item["trade_status"] = None
            item["trade_skip_reason"] = ""

    return _ok({"item": item})


@router.get("/accuracy")
async def get_accuracy(
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days: int = Query(default=0, ge=0, le=365, description="时间范围：0=全部, 1=今日, 7=最近7天, 30=最近30天"),
):
    """
    获取信号方向预测一致性统计

    重要说明：
    - 本接口统计的是"价格方向预测一致性"，而非实际交易盈亏
    - BUY 信号：价格上涨即为方向正确
    - SELL 信号：价格下跌即为方向正确
    - HOLD 信号：价格波动小于阈值即为方向正确

    此统计仅反映 AI 对价格走势方向的判断能力，不构成投资收益保证。
    """
    try:
        stats = await get_direction_consistency_stats(db, days=days)
    except Exception:
        logger.exception("accuracy 统计失败，返回降级结果")
        stats = {
            "total_signals": 0,
            "direction_accuracy": 0,
            "weighted_accuracy": 0,
            "correct_count": 0,
            "incorrect_count": 0,
            "neutral_count": 0,
            "by_symbol": {},
            "by_signal_type": {},
            "avg_price_change": 0,
            "methodology": {},
            "disclaimer": {},
        }

    # 添加响应元数据
    response = {
        **stats,
        "_meta": {
            "api_version": "2.0",
            "stat_type": "direction_consistency",
            "note": "统计的是价格方向预测一致性，非实际盈亏",
        },
    }

    return _ok(response)


@router.get("/superbrain")
async def get_superbrain(
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """最强大脑状态面板：市场状态/时段/BTC方向/全局持仓/连亏警戒"""
    from backend.market.data_collector import fetch_all_market_data
    from backend.market.indicators import calculate_indicators
    from backend.trading.executor import auto_trader
    from backend.trading.models import TradeRecord

    result: dict[str, Any] = {}
    btc_price = 0
    btc_klines = None

    # --- 1. 市场状态（用 BTC 指标判断） ---
    try:
        btc_data = await fetch_all_market_data("BTCUSDT")
        btc_klines = btc_data.get("klines")
        btc_price = btc_data.get("latest_price", 0)
        if btc_klines is not None and not btc_klines.empty:
            indicators = calculate_indicators(btc_klines)
            bb = indicators.get("bollinger", {})
            bb_upper, bb_lower, bb_mid = bb.get("upper", 0), bb.get("lower", 0), bb.get("middle", 1)
            bb_width = (bb_upper - bb_lower) / bb_mid * 100 if bb_mid > 0 else 0
            atr = indicators.get("atr", 0)
            price = indicators.get("price", bb_mid)
            atr_pct = (atr / price * 100) if price > 0 else 0
            ma7 = indicators.get("ma", {}).get("ma7", 0)
            ma25 = indicators.get("ma", {}).get("ma25", 0)
            ma99 = indicators.get("ma", {}).get("ma99", 0)
            ma_aligned = (ma7 > ma25 > ma99) or (ma7 < ma25 < ma99) if ma7 > 0 and ma25 > 0 and ma99 > 0 else False

            if atr_pct > 3.0 or bb_width > 8.0:
                result["market_regime"] = "剧烈波动"
                result["market_advice"] = "市场波动剧烈，减少交易频率，缩小仓位，避免追涨杀跌"
            elif ma_aligned and bb_width > 3.0:
                direction = "上涨" if ma7 > ma99 else "下跌"
                result["market_regime"] = f"趋势行情({direction})"
                result["market_advice"] = f"当前处于{direction}趋势，应顺势持有，不要频繁反向操作"
            else:
                result["market_regime"] = "震荡行情"
                result["market_advice"] = "市场横盘震荡，适合高抛低吸，不追涨杀跌"
        else:
            result["market_regime"] = "数据不足"
            result["market_advice"] = ""
    except Exception as e:
        logger.warning(f"[superbrain] 获取市场状态失败: {e}")
        result["market_regime"] = "获取失败"
        result["market_advice"] = ""

    # --- 2. 交易时段 ---
    try:
        from datetime import timezone as _tz
        beijing_hour = (datetime.now(_tz.utc).hour + 8) % 24
        if 8 <= beijing_hour < 16:
            session, session_desc = "亚洲盘", "波动相对温和，适合稳健操作"
        elif 16 <= beijing_hour < 21:
            session, session_desc = "欧洲盘", "波动开始加大，注意趋势启动"
        else:
            session, session_desc = "美国盘", "波动最大、流动性最好，趋势行情多发"
        result["trading_session"] = session
        result["session_hour"] = beijing_hour
        result["session_desc"] = session_desc
    except Exception as e:
        logger.debug("[AI路由] 交易时段检测失败: %s", e)
        result["trading_session"] = "未知"
        result["session_hour"] = 0
        result["session_desc"] = ""

    # --- 3. BTC方向 ---
    try:
        if btc_price == 0:
            btc_data = await fetch_all_market_data("BTCUSDT")
            btc_price = btc_data.get("latest_price", 0)
            btc_klines = btc_data.get("klines")

        result["btc_price"] = round(btc_price, 2) if btc_price else 0
        if btc_klines is not None and not btc_klines.empty:
            close_1h_ago = float(btc_klines["close"].iloc[-2]) if len(btc_klines) >= 2 else btc_price
            close_4h_ago = float(btc_klines["close"].iloc[-4]) if len(btc_klines) >= 4 else btc_price
            change_1h = (btc_price - close_1h_ago) / close_1h_ago * 100 if close_1h_ago else 0
            change_4h = (btc_price - close_4h_ago) / close_4h_ago * 100 if close_4h_ago else 0
            result["btc_change_1h"] = round(change_1h, 2)
            result["btc_change_4h"] = round(change_4h, 2)
            result["btc_direction"] = "上涨" if change_1h > 0.1 else ("下跌" if change_1h < -0.1 else "横盘")
        else:
            result["btc_change_1h"] = 0
            result["btc_change_4h"] = 0
            result["btc_direction"] = "数据不足"
    except Exception as e:
        logger.warning(f"[superbrain] 获取BTC方向失败: {e}")
        result["btc_price"] = 0
        result["btc_change_1h"] = 0
        result["btc_change_4h"] = 0
        result["btc_direction"] = "获取失败"

    # --- 4. 全局持仓 ---
    try:
        positions = await auto_trader._calc_positions()
        long_total, short_total = 0.0, 0.0
        details = []
        if positions:
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

        result["global_long_total"] = round(long_total, 2)
        result["global_short_total"] = round(short_total, 2)
        total = long_total + short_total
        if total > 0:
            bias_pct = abs(long_total - short_total) / total * 100
            result["global_bias"] = "偏多" if long_total > short_total else ("偏空" if short_total > long_total else "均衡")
            result["global_bias_pct"] = round(bias_pct, 1)
        else:
            result["global_bias"] = "无持仓"
            result["global_bias_pct"] = 0
        result["global_details"] = ", ".join(details) if details else "无"
    except Exception as e:
        logger.warning(f"[superbrain] 获取全局持仓失败: {e}")
        result["global_long_total"] = 0
        result["global_short_total"] = 0
        result["global_bias"] = "获取失败"
        result["global_bias_pct"] = 0
        result["global_details"] = ""

    # --- 5. 各币种连亏警戒 ---
    try:
        loss_streaks = []
        for symbol in SYMBOLS:
            streak_stmt = (
                select(TradeRecord.side, TradeRecord.quote_amount, TradeRecord.price, TradeRecord.created_at)
                .where(TradeRecord.symbol == symbol, TradeRecord.status == "filled")
                .order_by(TradeRecord.created_at.desc())
                .limit(30)
            )
            rows_result = await db.execute(streak_stmt)
            rows = list(rows_result.all())
            if len(rows) < 2:
                continue

            pairs = pair_trades(rows, sort_order="desc")
            if not pairs:
                continue

            streak = 0
            streak_dir = ""
            for p in pairs:
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

            if streak >= 2:
                from backend.config import settings as _cfg
                caution_n = int(getattr(_cfg, "RISK_RECENT_LOSS_STREAK_CAUTION", 5))
                halt_n = int(getattr(_cfg, "RISK_RECENT_LOSS_STREAK_HALT", 10))
                if streak >= halt_n:
                    level = "halt"
                elif streak >= caution_n:
                    level = "caution"
                else:
                    level = "normal"
                loss_streaks.append({
                    "symbol": symbol,
                    "direction": streak_dir,
                    "streak": streak,
                    "level": level,
                })

        result["loss_streaks"] = loss_streaks
    except Exception as e:
        logger.warning(f"[superbrain] 获取连亏数据失败: {e}")
        result["loss_streaks"] = []

    return _ok(result)


@router.post("/analyze-now")
async def analyze_now(
    req: AnalyzeRequest,
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """立即触发 AI 分析（测试阶段：不做冷却/限流）"""
    symbol = req.symbol.upper()
    if symbol not in SYMBOLS:
        raise HTTPException(status_code=400, detail=f"不支持的交易对: {symbol}")

    signal = await generate_signal(symbol, db)
    return _ok({"message": "分析完成", "signal": signal})


@router.get("/signal-stats")
async def get_signal_stats(
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """信号统计总览：信号分布、交易执行、按币种、近期趋势"""
    try:
        now = datetime.utcnow()

        # 1) 各信号类型计数
        breakdown_q = await db.execute(
            select(AISignal.signal, func.count()).group_by(AISignal.signal)
        )
        signal_breakdown = {}
        total_signals = 0
        for sig_type, cnt in breakdown_q.all():
            signal_breakdown[sig_type] = cnt
            total_signals += cnt

        # 2) 交易记录统计
        trade_total_q = await db.execute(select(func.count()).select_from(TradeRecord))
        total_traded = int(trade_total_q.scalar() or 0)

        trade_status_q = await db.execute(
            select(TradeRecord.status, func.count()).group_by(TradeRecord.status)
        )
        trade_status_map = {row[0]: row[1] for row in trade_status_q.all()}

        trade_stats = {
            "total_traded": total_traded,
            "filled": trade_status_map.get("filled", 0),
            "skipped": trade_status_map.get("skipped", 0),
            "failed": trade_status_map.get("failed", 0),
        }

        # 3) 按币种统计
        sym_q = await db.execute(
            select(
                AISignal.symbol,
                func.count().label("total"),
                func.sum(func.cast(AISignal.signal == "BUY", Integer)).label("buy_count"),
                func.sum(func.cast(AISignal.signal == "SELL", Integer)).label("sell_count"),
                func.sum(func.cast(AISignal.signal == "SHORT", Integer)).label("short_count"),
                func.sum(func.cast(AISignal.signal == "COVER", Integer)).label("cover_count"),
                func.sum(func.cast(AISignal.signal == "HOLD", Integer)).label("hold_count"),
                func.avg(AISignal.confidence).label("avg_confidence"),
            ).group_by(AISignal.symbol).order_by(func.count().desc())
        )
        by_symbol = []
        sym_rows = sym_q.all()
        sym_names = [r.symbol for r in sym_rows]

        trade_by_sym_q = await db.execute(
            select(
                TradeRecord.symbol,
                func.count().label("traded"),
                func.sum(func.cast(TradeRecord.status == "filled", Integer)).label("filled"),
            ).group_by(TradeRecord.symbol)
        )
        trade_sym_map = {r.symbol: {"traded": r.traded, "filled": r.filled or 0} for r in trade_by_sym_q.all()}

        for r in sym_rows:
            t = trade_sym_map.get(r.symbol, {"traded": 0, "filled": 0})
            by_symbol.append({
                "symbol": r.symbol,
                "total": r.total,
                "buy_count": r.buy_count or 0,
                "sell_count": r.sell_count or 0,
                "short_count": r.short_count or 0,
                "cover_count": r.cover_count or 0,
                "hold_count": r.hold_count or 0,
                "traded": t["traded"],
                "filled": t["filled"],
                "avg_confidence": round(float(r.avg_confidence or 0), 1),
            })

        # 4) 近期信号量
        async def _recent(hours):
            cutoff = now - timedelta(hours=hours)
            sig_cnt_q = await db.execute(
                select(func.count()).select_from(AISignal).where(AISignal.created_at >= cutoff)
            )
            sig_cnt = int(sig_cnt_q.scalar() or 0)
            act_cnt_q = await db.execute(
                select(func.count()).select_from(AISignal).where(
                    AISignal.created_at >= cutoff,
                    AISignal.signal.in_(["BUY", "SELL", "SHORT", "COVER"]),
                )
            )
            act_cnt = int(act_cnt_q.scalar() or 0)
            trd_cnt_q = await db.execute(
                select(func.count()).select_from(TradeRecord).where(TradeRecord.created_at >= cutoff)
            )
            trd_cnt = int(trd_cnt_q.scalar() or 0)
            return {"total": sig_cnt, "actionable": act_cnt, "traded": trd_cnt}

        recent_accuracy = {
            "last_24h": await _recent(24),
            "last_7d": await _recent(24 * 7),
            "last_30d": await _recent(24 * 30),
        }

        return _ok({
            "total_signals": total_signals,
            "signal_breakdown": signal_breakdown,
            "trade_stats": trade_stats,
            "by_symbol": by_symbol,
            "recent_accuracy": recent_accuracy,
        })

    except Exception:
        logger.exception("signal-stats 统计失败")
        raise HTTPException(status_code=500, detail="统计查询失败")
