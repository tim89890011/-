"""
统一 PNL 计算与交易配对模块

所有 PNL 百分比计算和交易配对逻辑的唯一来源，
替代散落在 debate.py / executor.py / gate.py 中的重复实现。
"""


def calc_pnl_pct(
    entry_price: float,
    current_price: float,
    side: str,
    leverage: float = 1.0,
) -> float:
    """
    计算 PNL 百分比

    Args:
        entry_price: 开仓价格
        current_price: 当前/平仓价格
        side: "long" 或 "short"
        leverage: 杠杆倍数，默认 1（不含杠杆）

    Returns:
        PNL 百分比（已乘以杠杆），例如 15.0 代表 +15%
    """
    if entry_price <= 0:
        return 0.0
    if side == "long":
        raw_pct = (current_price - entry_price) / entry_price * 100
    else:
        raw_pct = (entry_price - current_price) / entry_price * 100
    return raw_pct * leverage


def pair_trades(rows, sort_order: str = "desc") -> list[dict]:
    """
    将交易记录按 FIFO 规则配对成开平仓对

    Args:
        rows: 交易记录列表，每条需要有 side, quote_amount, created_at
              支持 ORM 对象（属性访问）或字典
        sort_order: 数据排序方式，"desc"（最新在前）或 "asc"（最早在前）

    Returns:
        配对列表，每个元素为:
        {"direction": "多"|"空", "pnl": float, "open_time": datetime, "close_time": datetime}
    """
    items = list(rows)
    if sort_order == "desc":
        items = list(reversed(items))

    pairs = []
    shorts_stack = []
    buys_stack = []

    for r in items:
        side = _get_side(r)
        if side == "SHORT":
            shorts_stack.append(r)
        elif side == "COVER" and shorts_stack:
            s = shorts_stack.pop(0)
            pnl = _get_quote(s) - _get_quote(r)
            pairs.append({
                "direction": "空",
                "pnl": pnl,
                "open_time": _get_time(s),
                "close_time": _get_time(r),
            })
        elif side == "BUY":
            buys_stack.append(r)
        elif side == "SELL" and buys_stack:
            b = buys_stack.pop(0)
            pnl = _get_quote(r) - _get_quote(b)
            pairs.append({
                "direction": "多",
                "pnl": pnl,
                "open_time": _get_time(b),
                "close_time": _get_time(r),
            })

    return pairs


def _get_side(r) -> str:
    if hasattr(r, "side"):
        return r.side
    return r.get("side", "")


def _get_quote(r) -> float:
    if hasattr(r, "quote_amount"):
        return float(r.quote_amount or 0)
    return float(r.get("quote_amount", 0))


def _get_time(r):
    if hasattr(r, "created_at"):
        return r.created_at
    return r.get("created_at")
