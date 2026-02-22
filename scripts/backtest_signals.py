#!/usr/bin/env python3
"""
钢子出击 - 离线回测脚本（更像量化）

目标：
- 读取 SQLite 中的 ai_signals
- 对 BUY/SHORT 入场信号，按 AI 建议的 take_profit_pct / stop_loss_pct
  在 24h 窗口内基于 K 线高低点模拟是否先触发 TP/SL
- 计算扣除手续费+滑点后的净收益（固定费率假设）
- 输出报告（JSON 明细 + Markdown 汇总），用于“分桶分析”指导策略门槛优化

注意：
- 这是离线分析工具，不影响线上交易逻辑
- K 线来自 Binance 合约接口（fapi），如某些 symbol 被下架会失败并被跳过
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import math
import os
import sqlite3
import statistics
import time
from pathlib import Path
from typing import Any, Iterable

import httpx


FAPI_BASE = "https://fapi.binance.com"


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_datetime(value: Any) -> dt.datetime | None:
    if value is None:
        return None

    if isinstance(value, dt.datetime):
        # sqlite 读出来一般是 str，这里只是兜底
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)

    if isinstance(value, (int, float)):
        # 兼容某些表里存 timestamp 秒/毫秒
        ts = float(value)
        if ts > 10_000_000_000:  # ms
            ts = ts / 1000.0
        return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)

    if not isinstance(value, str):
        return None

    s = value.strip()
    if not s:
        return None

    # 常见：2026-02-17 03:51:43.482000
    # 或：2026-02-17T03:51:43.482000+00:00
    # 或：2026-02-17T03:51:43.482000Z
    s = s.replace("Z", "+00:00")
    try:
        d = dt.datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            d = dt.datetime.strptime(s, fmt)
            return d.replace(tzinfo=dt.timezone.utc)
        except Exception:
            continue

    return None


def _dt_to_ms(d: dt.datetime) -> int:
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp() * 1000)


def _floor_to_interval_ms(ts_ms: int, interval_ms: int) -> int:
    return ts_ms - (ts_ms % interval_ms)


def _ceil_to_interval_ms(ts_ms: int, interval_ms: int) -> int:
    floored = _floor_to_interval_ms(ts_ms, interval_ms)
    return floored if ts_ms == floored else floored + interval_ms


def _interval_to_ms(interval: str) -> int:
    # Binance interval: 1m/3m/5m/15m/30m/1h/2h/4h/6h/8h/12h/1d...
    n = int(interval[:-1])
    unit = interval[-1]
    if unit == "m":
        return n * 60 * 1000
    if unit == "h":
        return n * 60 * 60 * 1000
    if unit == "d":
        return n * 24 * 60 * 60 * 1000
    raise ValueError(f"unsupported interval: {interval}")



# v1.1: 币种动态滑点系数
_TIER1_SYMBOLS = {"BTCUSDT", "ETHUSDT"}

def _dynamic_slippage_bps(symbol: str, base_bps: float, k_btc: float = 0.08, k_default: float = 0.18) -> float:
    """根据币种流动性调整滑点 bps
    主流币（BTC/ETH）用 k_btc 系数，其余用 k_default
    """
    sym = symbol.upper().replace("/USDT:USDT", "USDT").replace("/USDT", "USDT")
    k = k_btc if sym in _TIER1_SYMBOLS else k_default
    return round(base_bps * (1 + k), 2)


def _confidence_bucket(conf: float) -> str:
    # 分桶尽量稳定：60-69/70-79/80-89/90-100
    if conf < 60:
        return "<60"
    if conf < 70:
        return "60-69"
    if conf < 80:
        return "70-79"
    if conf < 90:
        return "80-89"
    return "90+"


@dataclasses.dataclass(frozen=True)
class SignalRow:
    id: int
    symbol: str
    signal: str
    confidence: float
    price_at_signal: float
    stop_loss_pct: float
    take_profit_pct: float
    created_at: dt.datetime


@dataclasses.dataclass
class TradeSimResult:
    signal_id: int
    symbol: str
    side: str  # LONG / SHORT
    confidence: float
    created_at: str
    entry_price: float
    tp_pct: float
    sl_pct: float
    exit_reason: str  # TP / SL / TIMEOUT / SKIP
    exit_price: float
    exit_ts_ms: int
    duration_min: int
    gross_pnl_pct: float
    net_pnl_pct: float
    both_hit_same_candle: bool
    notes: str = ""


def _query_signals(conn: sqlite3.Connection, limit: int) -> list[SignalRow]:
    # 只回测开仓信号：BUY（开多）/SHORT（开空）
    sql = """
    SELECT id, symbol, signal, confidence, price_at_signal,
           stop_loss_pct, take_profit_pct, created_at
    FROM ai_signals
    WHERE signal IN ('BUY', 'SHORT')
    ORDER BY created_at DESC
    LIMIT ?
    """
    rows = conn.execute(sql, (limit,)).fetchall()
    out: list[SignalRow] = []
    for r in rows:
        created = _parse_datetime(r[7])
        if created is None:
            continue
        out.append(
            SignalRow(
                id=int(r[0]),
                symbol=str(r[1]).upper(),
                signal=str(r[2]).upper(),
                confidence=float(r[3] or 0),
                price_at_signal=float(r[4] or 0),
                stop_loss_pct=float(r[5] or 0),
                take_profit_pct=float(r[6] or 0),
                created_at=created,
            )
        )
    return out


def _fetch_klines(
    client: httpx.Client,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    limit: int = 1000,
    retries: int = 3,
) -> list[list[Any]]:
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": limit,
    }
    last_err: Exception | None = None
    for i in range(retries):
        try:
            resp = client.get(f"{FAPI_BASE}/fapi/v1/klines", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                raise RuntimeError(f"unexpected response: {type(data)}")
            return data
        except Exception as e:
            last_err = e
            # 简单退避
            time.sleep(0.5 * (i + 1))
    raise RuntimeError(f"fetch klines failed for {symbol}: {last_err}") from last_err


def _cache_key(symbol: str, interval: str, start_ms: int, end_ms: int) -> str:
    return f"{symbol}_{interval}_{start_ms}_{end_ms}.json"


def _load_klines_cached(
    client: httpx.Client,
    cache_dir: Path,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
) -> list[list[Any]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(symbol, interval, start_ms, end_ms)
    fp = cache_dir / key
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            # 缓存损坏就忽略
            pass

    data = _fetch_klines(client, symbol, interval, start_ms, end_ms)
    fp.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    return data


def _simulate_trade(
    sig: SignalRow,
    klines: list[list[Any]],
    signal_ts_ms: int,
    window_end_ms: int,
    interval_ms: int,
    fee_bps: float,
    slip_bps: float,
) -> TradeSimResult:
    first_open = float(klines[0][1]) if klines else 0.0
    entry = first_open if first_open > 0 else float(sig.price_at_signal or 0)
    if entry <= 0:
        return TradeSimResult(
            signal_id=sig.id,
            symbol=sig.symbol,
            side="SKIP",
            confidence=sig.confidence,
            created_at=sig.created_at.isoformat(),
            entry_price=entry,
            tp_pct=sig.take_profit_pct,
            sl_pct=sig.stop_loss_pct,
            exit_reason="SKIP",
            exit_price=0,
            exit_ts_ms=0,
            duration_min=0,
            gross_pnl_pct=0.0,
            net_pnl_pct=0.0,
            both_hit_same_candle=False,
            notes="entry_price<=0",
        )

    side = "LONG" if sig.signal == "BUY" else "SHORT"
    tp_pct = float(sig.take_profit_pct or 0)
    sl_pct = float(sig.stop_loss_pct or 0)

    # 没有 AI 建议的 TP/SL，就只看窗口结束价
    has_tp = tp_pct > 0
    has_sl = sl_pct > 0

    if side == "LONG":
        tp_price = entry * (1 + tp_pct / 100) if has_tp else math.inf
        sl_price = entry * (1 - sl_pct / 100) if has_sl else -math.inf
    else:
        # SHORT：价格下跌是盈利；TP=跌 tp_pct，SL=涨 sl_pct
        tp_price = entry * (1 - tp_pct / 100) if has_tp else -math.inf
        sl_price = entry * (1 + sl_pct / 100) if has_sl else math.inf

    exit_reason = "TIMEOUT"
    exit_price = entry
    exit_ts_ms = window_end_ms
    both_hit_same = False
    last_close: float | None = None
    last_close_ts: int | None = None

    for k in klines:
        open_ts = int(k[0])
        if open_ts < signal_ts_ms:
            continue
        if open_ts >= window_end_ms:
            break
        close_ts = int(k[6]) if len(k) > 6 else (open_ts + interval_ms)
        if close_ts > window_end_ms:
            break
        high = float(k[2])
        low = float(k[3])
        close = float(k[4])
        last_close = close
        last_close_ts = close_ts

        if side == "LONG":
            hit_tp = has_tp and high >= tp_price
            hit_sl = has_sl and low <= sl_price
        else:
            hit_tp = has_tp and low <= tp_price
            hit_sl = has_sl and high >= sl_price

        if hit_tp and hit_sl:
            both_hit_same = True
            exit_reason = "SL"
            exit_price = sl_price
            exit_ts_ms = close_ts
            break
        if hit_sl:
            exit_reason = "SL"
            exit_price = sl_price
            exit_ts_ms = close_ts
            break
        if hit_tp:
            exit_reason = "TP"
            exit_price = tp_price
            exit_ts_ms = close_ts
            break

    duration_min = max(0, int(round((exit_ts_ms - _dt_to_ms(sig.created_at)) / 60000)))

    if exit_reason == "TIMEOUT" and last_close is not None and last_close_ts is not None:
        if last_close_ts <= window_end_ms:
            exit_price = last_close
            exit_ts_ms = last_close_ts
            duration_min = max(0, int(round((exit_ts_ms - _dt_to_ms(sig.created_at)) / 60000)))

    if side == "LONG":
        gross = (exit_price - entry) / entry * 100
    else:
        gross = (entry - exit_price) / entry * 100

    # 费率假设：单边手续费+滑点（bps），来回两边
    total_cost_pct = 2.0 * (fee_bps + slip_bps) / 100.0
    net = gross - total_cost_pct

    return TradeSimResult(
        signal_id=sig.id,
        symbol=sig.symbol,
        side=side,
        confidence=sig.confidence,
        created_at=sig.created_at.isoformat(),
        entry_price=round(entry, 8),
        tp_pct=round(tp_pct, 4),
        sl_pct=round(sl_pct, 4),
        exit_reason=exit_reason,
        exit_price=round(exit_price, 8),
        exit_ts_ms=int(exit_ts_ms),
        duration_min=int(duration_min),
        gross_pnl_pct=round(gross, 4),
        net_pnl_pct=round(net, 4),
        both_hit_same_candle=both_hit_same,
    )


def _summarize(results: list[TradeSimResult]) -> dict[str, Any]:
    ok = [r for r in results if r.exit_reason != "SKIP"]
    net_pnls = [r.net_pnl_pct for r in ok]
    gross_pnls = [r.gross_pnl_pct for r in ok]

    def _safe_mean(xs: list[float]) -> float:
        return float(statistics.mean(xs)) if xs else 0.0

    def _safe_median(xs: list[float]) -> float:
        return float(statistics.median(xs)) if xs else 0.0

    win = [x for x in net_pnls if x > 0]
    loss = [x for x in net_pnls if x <= 0]

    by_symbol: dict[str, list[TradeSimResult]] = {}
    by_bucket: dict[str, list[TradeSimResult]] = {}

    for r in ok:
        by_symbol.setdefault(r.symbol, []).append(r)
        by_bucket.setdefault(_confidence_bucket(r.confidence), []).append(r)

    def _bucket_stats(rs: list[TradeSimResult]) -> dict[str, Any]:
        xs = [x.net_pnl_pct for x in rs]
        wins = sum(1 for x in xs if x > 0)
        total = len(xs)
        return {
            "trades": total,
            "winrate": round((wins / total * 100) if total else 0.0, 2),
            "net_mean": round(_safe_mean(xs), 4),
            "net_median": round(_safe_median(xs), 4),
        }

    return {
        "trades_total": len(results),
        "trades_simulated": len(ok),
        "trades_skipped": len(results) - len(ok),
        "winrate": round((len(win) / len(ok) * 100) if ok else 0.0, 2),
        "net_mean": round(_safe_mean(net_pnls), 4),
        "net_median": round(_safe_median(net_pnls), 4),
        "net_best": round(max(net_pnls) if net_pnls else 0.0, 4),
        "net_worst": round(min(net_pnls) if net_pnls else 0.0, 4),
        "gross_mean": round(_safe_mean(gross_pnls), 4),
        "by_symbol": {sym: _bucket_stats(rs) for sym, rs in sorted(by_symbol.items())},
        "by_confidence": {
            b: _bucket_stats(rs) for b, rs in sorted(by_bucket.items(), key=lambda x: x[0])
        },
    }


def _write_markdown(
    out_path: Path,
    meta: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    lines: list[str] = []
    lines.append("# Backtest Report (Signals)")
    lines.append("")
    lines.append(f"- generated_at: `{meta['generated_at']}`")
    lines.append(f"- db_path: `{meta['db_path']}`")
    lines.append(f"- interval: `{meta['interval']}`")
    lines.append(f"- window_hours: `{meta['window_hours']}`")
    lines.append(
        f"- costs: fee_bps={meta['fee_bps']}, slippage_bps={meta['slippage_bps']} (round trip)"
    )
    lines.append(f"- signals_limit: `{meta['limit']}` (BUY/SHORT only)")
    lines.append("")

    lines.append("## Overall")
    lines.append("")
    lines.append(f"- trades_simulated: `{summary['trades_simulated']}`")
    lines.append(f"- winrate(net>0): `{summary['winrate']}%`")
    lines.append(f"- net_mean: `{summary['net_mean']}%`")
    lines.append(f"- net_median: `{summary['net_median']}%`")
    lines.append(f"- net_best / net_worst: `{summary['net_best']}% / {summary['net_worst']}%`")
    lines.append("")

    lines.append("## By Confidence Bucket (net pnl)")
    lines.append("")
    lines.append("| bucket | trades | winrate | net_mean | net_median |")
    lines.append("|---|---:|---:|---:|---:|")
    for bucket, st in summary["by_confidence"].items():
        lines.append(
            f"| {bucket} | {st['trades']} | {st['winrate']}% | {st['net_mean']}% | {st['net_median']}% |"
        )
    lines.append("")

    lines.append("## By Symbol (net pnl)")
    lines.append("")
    lines.append("| symbol | trades | winrate | net_mean | net_median |")
    lines.append("|---|---:|---:|---:|---:|")
    for sym, st in summary["by_symbol"].items():
        lines.append(
            f"| {sym} | {st['trades']} | {st['winrate']}% | {st['net_mean']}% | {st['net_median']}% |"
        )
    lines.append("")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-path", default="data/gangzi.db")
    ap.add_argument("--limit", type=int, default=500, help="回测最近 N 条 BUY/SHORT 信号")
    ap.add_argument("--interval", default="5m", help="K线周期，如 5m/15m/1h")
    ap.add_argument("--window-hours", type=int, default=24, help="每条信号回测窗口（小时）")
    ap.add_argument("--fee-bps", type=float, default=4.0, help="单边手续费，单位 bps")
    ap.add_argument("--slippage-bps", type=float, default=2.0, help="单边滑点，单位 bps")
    ap.add_argument("--k-btc", type=float, default=0.08, help="v1.1: BTC/ETH 滑点系数")
    ap.add_argument("--k-default", type=float, default=0.18, help="v1.1: 山寨币滑点系数")
    ap.add_argument("--walk-forward", action="store_true", help="v1.1: 按月滚动回测（walk-forward）")
    ap.add_argument(
        "--out-dir",
        default="reports",
        help="输出目录（会创建 JSON+MD）",
    )
    ap.add_argument(
        "--cache-dir",
        default=".cache/backtest_klines",
        help="K 线缓存目录（避免重复请求）",
    )
    args = ap.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    db_path = (project_root / args.db_path).resolve()
    out_dir = (project_root / args.out_dir).resolve()
    cache_dir = (project_root / args.cache_dir).resolve()

    out_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        raise SystemExit(f"db not found: {db_path}")

    interval_ms = _interval_to_ms(args.interval)
    window_ms = int(args.window_hours) * 60 * 60 * 1000

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        signals = _query_signals(conn, int(args.limit))

    if not signals:
        print("no signals found (BUY/SHORT)")
        return 0

    # 为了降低 API 压力：按 symbol+时间窗请求，每条信号都独立缓存
    results: list[TradeSimResult] = []
    with httpx.Client(headers={"User-Agent": "gangzi-backtest/1.0"}) as client:
        for sig in signals:
            signal_ts_ms = _dt_to_ms(sig.created_at)
            start_ms = _ceil_to_interval_ms(signal_ts_ms, interval_ms)
            end_ms = start_ms + window_ms

            try:
                klines = _load_klines_cached(
                    client=client,
                    cache_dir=cache_dir,
                    symbol=sig.symbol,
                    interval=args.interval,
                    start_ms=start_ms,
                    end_ms=end_ms,
                )
                if not klines:
                    results.append(
                        TradeSimResult(
                            signal_id=sig.id,
                            symbol=sig.symbol,
                            side="SKIP",
                            confidence=sig.confidence,
                            created_at=sig.created_at.isoformat(),
                            entry_price=float(sig.price_at_signal or 0),
                            tp_pct=float(sig.take_profit_pct or 0),
                            sl_pct=float(sig.stop_loss_pct or 0),
                            exit_reason="SKIP",
                            exit_price=0,
                            exit_ts_ms=0,
                            duration_min=0,
                            gross_pnl_pct=0.0,
                            net_pnl_pct=0.0,
                            both_hit_same_candle=False,
                            notes="empty klines",
                        )
                    )
                    continue

                # v1.1: 币种动态滑点
                actual_slip = _dynamic_slippage_bps(
                    sig.symbol, float(args.slippage_bps),
                    k_btc=float(args.k_btc), k_default=float(args.k_default),
                )
                results.append(
                    _simulate_trade(
                        sig=sig,
                        klines=klines,
                        signal_ts_ms=signal_ts_ms,
                        window_end_ms=end_ms,
                        interval_ms=interval_ms,
                        fee_bps=float(args.fee_bps),
                        slip_bps=actual_slip,
                    )
                )
            except Exception as e:
                results.append(
                    TradeSimResult(
                        signal_id=sig.id,
                        symbol=sig.symbol,
                        side="SKIP",
                        confidence=sig.confidence,
                        created_at=sig.created_at.isoformat(),
                        entry_price=float(sig.price_at_signal or 0),
                        tp_pct=float(sig.take_profit_pct or 0),
                        sl_pct=float(sig.stop_loss_pct or 0),
                        exit_reason="SKIP",
                        exit_price=0,
                        exit_ts_ms=0,
                        duration_min=0,
                        gross_pnl_pct=0.0,
                        net_pnl_pct=0.0,
                        both_hit_same_candle=False,
                        notes=f"fetch/sim error: {type(e).__name__}: {e}",
                    )
                )

    summary = _summarize(results)
    generated_at = _utc_now().isoformat()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = out_dir / f"backtest_signals_{stamp}"

    meta = {
        "generated_at": generated_at,
        "db_path": str(db_path),
        "interval": args.interval,
        "window_hours": int(args.window_hours),
        "fee_bps": float(args.fee_bps),
        "slippage_bps": float(args.slippage_bps),
        "limit": int(args.limit),
        "note": "This report backtests BUY/SHORT entries only; SELL/COVER are exits and not simulated here.",
        "k_btc": float(args.k_btc),
        "k_default": float(args.k_default),
        "walk_forward": getattr(args, "walk_forward", False),
    }
    json_payload = {
        "meta": meta,
        "summary": summary,
        "results": [dataclasses.asdict(r) for r in results],
    }

    (base.with_suffix(".json")).write_text(
        json.dumps(json_payload, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    _write_markdown(base.with_suffix(".md"), meta=meta, summary=summary)

    print(f"OK: wrote {base.with_suffix('.json')}")
    print(f"OK: wrote {base.with_suffix('.md')}")
    print(f"trades_simulated={summary['trades_simulated']} winrate={summary['winrate']}% net_mean={summary['net_mean']}%")

    # v1.1: walk-forward 月度汇总
    if getattr(args, "walk_forward", False):
        from collections import defaultdict as dd
        monthly = dd(list)
        for r in results:
            if r.side == "SKIP":
                continue
            month = r.created_at[:7]
            monthly[month].append(r)
        print("\n=== Walk-Forward 月度汇总 ===")
        for month in sorted(monthly.keys()):
            mrs = monthly[month]
            wins = sum(1 for r in mrs if r.net_pnl_pct > 0)
            total_m = len(mrs)
            wr = round(wins / total_m * 100, 1) if total_m else 0
            avg_net = round(sum(r.net_pnl_pct for r in mrs) / total_m, 3) if total_m else 0
            print(f"  {month}: {total_m} 笔, 胜率 {wr}%, 平均净盈亏 {avg_net}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

