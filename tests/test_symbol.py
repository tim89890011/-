"""
tests/test_symbol.py - symbol 格式转换工具测试
"""

import pytest

from backend.utils.symbol import to_raw, to_ccxt, to_base


class TestToRaw:
    def test_ccxt_format(self):
        assert to_raw("BTC/USDT:USDT") == "BTCUSDT"

    def test_slash_format(self):
        assert to_raw("BTC/USDT") == "BTCUSDT"

    def test_already_raw(self):
        assert to_raw("BTCUSDT") == "BTCUSDT"

    def test_lowercase(self):
        assert to_raw("btcusdt") == "BTCUSDT"

    def test_eth(self):
        assert to_raw("ETH/USDT:USDT") == "ETHUSDT"

    def test_doge(self):
        assert to_raw("DOGEUSDT") == "DOGEUSDT"

    def test_mixed_case(self):
        assert to_raw("Btc/Usdt:Usdt") == "BTCUSDT"


class TestToCcxt:
    def test_from_raw(self):
        assert to_ccxt("BTCUSDT") == "BTC/USDT:USDT"

    def test_from_ccxt(self):
        assert to_ccxt("BTC/USDT:USDT") == "BTC/USDT:USDT"

    def test_lowercase(self):
        assert to_ccxt("btcusdt") == "BTC/USDT:USDT"

    def test_eth(self):
        assert to_ccxt("ETHUSDT") == "ETH/USDT:USDT"

    def test_doge(self):
        assert to_ccxt("DOGEUSDT") == "DOGE/USDT:USDT"


class TestToBase:
    def test_from_raw(self):
        assert to_base("BTCUSDT") == "BTC"

    def test_from_ccxt(self):
        assert to_base("BTC/USDT:USDT") == "BTC"

    def test_lowercase(self):
        assert to_base("ethusdt") == "ETH"

    def test_doge(self):
        assert to_base("DOGEUSDT") == "DOGE"

    def test_sol(self):
        assert to_base("SOL/USDT:USDT") == "SOL"
