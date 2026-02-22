"""
symbol 格式转换工具

统一处理 Binance 交易对符号在不同格式之间的转换：
- raw:  "BTCUSDT"        (Binance REST/WS, 数据库, AI 信号)
- ccxt: "BTC/USDT:USDT"  (ccxt 合约格式)
- base: "BTC"            (不含 USDT 的币种名)
"""


def to_raw(symbol: str) -> str:
    """
    将任意格式转为 raw 格式: "BTCUSDT"

    >>> to_raw("BTC/USDT:USDT")
    'BTCUSDT'
    >>> to_raw("BTC/USDT")
    'BTCUSDT'
    >>> to_raw("BTCUSDT")
    'BTCUSDT'
    >>> to_raw("btcusdt")
    'BTCUSDT'
    """
    s = symbol.upper()
    return s.replace("/USDT:USDT", "USDT").replace("/USDT", "USDT")


def to_ccxt(symbol: str) -> str:
    """
    将任意格式转为 ccxt 合约格式: "BTC/USDT:USDT"

    >>> to_ccxt("BTCUSDT")
    'BTC/USDT:USDT'
    >>> to_ccxt("BTC/USDT:USDT")
    'BTC/USDT:USDT'
    >>> to_ccxt("btcusdt")
    'BTC/USDT:USDT'
    """
    raw = to_raw(symbol)
    base = raw.replace("USDT", "")
    return f"{base}/USDT:USDT"


def to_base(symbol: str) -> str:
    """
    提取币种名: "BTC"

    >>> to_base("BTCUSDT")
    'BTC'
    >>> to_base("BTC/USDT:USDT")
    'BTC'
    """
    return to_raw(symbol).replace("USDT", "")
