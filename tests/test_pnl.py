"""
tests/test_pnl.py - PNL 计算与交易配对的测试
遵循 TDD：先写测试（红灯），再写实现（绿灯）
"""

import pytest
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta


# ====== calc_pnl_pct 测试 ======

class TestCalcPnlPct:
    """测试统一 PNL 百分比计算"""

    def test_long_profit(self):
        """多仓盈利：当前价高于开仓价"""
        from backend.trading.pnl import calc_pnl_pct
        result = calc_pnl_pct(entry_price=100, current_price=105, side="long")
        assert result == pytest.approx(5.0)

    def test_long_loss(self):
        """多仓亏损：当前价低于开仓价"""
        from backend.trading.pnl import calc_pnl_pct
        result = calc_pnl_pct(entry_price=100, current_price=95, side="long")
        assert result == pytest.approx(-5.0)

    def test_short_profit(self):
        """空仓盈利：当前价低于开仓价"""
        from backend.trading.pnl import calc_pnl_pct
        result = calc_pnl_pct(entry_price=100, current_price=95, side="short")
        assert result == pytest.approx(5.0)

    def test_short_loss(self):
        """空仓亏损：当前价高于开仓价"""
        from backend.trading.pnl import calc_pnl_pct
        result = calc_pnl_pct(entry_price=100, current_price=105, side="short")
        assert result == pytest.approx(-5.0)

    def test_with_leverage(self):
        """杠杆放大：3x 杠杆下 5% 价格变动 = 15% PNL"""
        from backend.trading.pnl import calc_pnl_pct
        result = calc_pnl_pct(entry_price=100, current_price=105, side="long", leverage=3)
        assert result == pytest.approx(15.0)

    def test_leverage_short(self):
        """空仓+杠杆"""
        from backend.trading.pnl import calc_pnl_pct
        result = calc_pnl_pct(entry_price=100, current_price=97, side="short", leverage=5)
        assert result == pytest.approx(15.0)

    def test_zero_entry_price(self):
        """开仓价为 0 时返回 0，不报错"""
        from backend.trading.pnl import calc_pnl_pct
        result = calc_pnl_pct(entry_price=0, current_price=100, side="long")
        assert result == 0.0

    def test_negative_entry_price(self):
        """开仓价为负数时返回 0"""
        from backend.trading.pnl import calc_pnl_pct
        result = calc_pnl_pct(entry_price=-10, current_price=100, side="long")
        assert result == 0.0

    def test_default_leverage_is_one(self):
        """默认杠杆为 1"""
        from backend.trading.pnl import calc_pnl_pct
        result = calc_pnl_pct(entry_price=100, current_price=110, side="long")
        assert result == pytest.approx(10.0)

    def test_no_change(self):
        """价格不变 = 0%"""
        from backend.trading.pnl import calc_pnl_pct
        result = calc_pnl_pct(entry_price=50000, current_price=50000, side="long")
        assert result == pytest.approx(0.0)


# ====== pair_trades 测试 ======

def _make_trade(side: str, quote_amount: float, created_at: datetime):
    """创建模拟交易记录"""
    return SimpleNamespace(side=side, quote_amount=quote_amount, created_at=created_at)


class TestPairTrades:
    """测试交易配对逻辑"""

    def _base_time(self):
        return datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def test_simple_long_pair(self):
        """简单多仓配对：BUY -> SELL"""
        from backend.trading.pnl import pair_trades
        t = self._base_time()
        rows = [
            _make_trade("BUY", 100.0, t),
            _make_trade("SELL", 110.0, t + timedelta(hours=1)),
        ]
        pairs = pair_trades(rows, sort_order="asc")
        assert len(pairs) == 1
        assert pairs[0]["direction"] == "多"
        assert pairs[0]["pnl"] == pytest.approx(10.0)

    def test_simple_short_pair(self):
        """简单空仓配对：SHORT -> COVER"""
        from backend.trading.pnl import pair_trades
        t = self._base_time()
        rows = [
            _make_trade("SHORT", 100.0, t),
            _make_trade("COVER", 90.0, t + timedelta(hours=1)),
        ]
        pairs = pair_trades(rows, sort_order="asc")
        assert len(pairs) == 1
        assert pairs[0]["direction"] == "空"
        assert pairs[0]["pnl"] == pytest.approx(10.0)

    def test_short_loss(self):
        """空仓亏损：COVER 花了更多钱"""
        from backend.trading.pnl import pair_trades
        t = self._base_time()
        rows = [
            _make_trade("SHORT", 100.0, t),
            _make_trade("COVER", 120.0, t + timedelta(hours=1)),
        ]
        pairs = pair_trades(rows, sort_order="asc")
        assert len(pairs) == 1
        assert pairs[0]["pnl"] == pytest.approx(-20.0)

    def test_desc_order_reversal(self):
        """DESC 排序的数据应被正确反转后配对"""
        from backend.trading.pnl import pair_trades
        t = self._base_time()
        # DESC 顺序 (最新在前)
        rows = [
            _make_trade("SELL", 110.0, t + timedelta(hours=1)),
            _make_trade("BUY", 100.0, t),
        ]
        pairs = pair_trades(rows, sort_order="desc")
        assert len(pairs) == 1
        assert pairs[0]["direction"] == "多"
        assert pairs[0]["pnl"] == pytest.approx(10.0)

    def test_multiple_pairs(self):
        """多笔交易正确配对"""
        from backend.trading.pnl import pair_trades
        t = self._base_time()
        rows = [
            _make_trade("BUY", 100.0, t),
            _make_trade("SELL", 105.0, t + timedelta(hours=1)),
            _make_trade("BUY", 110.0, t + timedelta(hours=2)),
            _make_trade("SELL", 108.0, t + timedelta(hours=3)),
        ]
        pairs = pair_trades(rows, sort_order="asc")
        assert len(pairs) == 2
        assert pairs[0]["pnl"] == pytest.approx(5.0)   # 第一笔赚 5
        assert pairs[1]["pnl"] == pytest.approx(-2.0)   # 第二笔亏 2

    def test_desc_multiple_pairs(self):
        """DESC 排序 + 多笔交易：验证反转后配对正确"""
        from backend.trading.pnl import pair_trades
        t = self._base_time()
        # DESC 顺序
        rows = [
            _make_trade("SELL", 108.0, t + timedelta(hours=3)),
            _make_trade("BUY", 110.0, t + timedelta(hours=2)),
            _make_trade("SELL", 105.0, t + timedelta(hours=1)),
            _make_trade("BUY", 100.0, t),
        ]
        pairs = pair_trades(rows, sort_order="desc")
        assert len(pairs) == 2
        assert pairs[0]["pnl"] == pytest.approx(5.0)   # BUY100 -> SELL105
        assert pairs[1]["pnl"] == pytest.approx(-2.0)   # BUY110 -> SELL108

    def test_mixed_long_short(self):
        """多空混合配对"""
        from backend.trading.pnl import pair_trades
        t = self._base_time()
        rows = [
            _make_trade("BUY", 100.0, t),
            _make_trade("SHORT", 200.0, t + timedelta(minutes=5)),
            _make_trade("SELL", 105.0, t + timedelta(hours=1)),
            _make_trade("COVER", 190.0, t + timedelta(hours=2)),
        ]
        pairs = pair_trades(rows, sort_order="asc")
        assert len(pairs) == 2
        # BUY100 -> SELL105 = +5
        long_pair = [p for p in pairs if p["direction"] == "多"][0]
        assert long_pair["pnl"] == pytest.approx(5.0)
        # SHORT200 -> COVER190 = +10
        short_pair = [p for p in pairs if p["direction"] == "空"][0]
        assert short_pair["pnl"] == pytest.approx(10.0)

    def test_unpaired_trades_ignored(self):
        """未配对的交易不计入结果"""
        from backend.trading.pnl import pair_trades
        t = self._base_time()
        rows = [
            _make_trade("BUY", 100.0, t),
            _make_trade("BUY", 200.0, t + timedelta(hours=1)),
            # 只有一个 SELL，只能配对一个 BUY
            _make_trade("SELL", 110.0, t + timedelta(hours=2)),
        ]
        pairs = pair_trades(rows, sort_order="asc")
        assert len(pairs) == 1
        # 第一个 BUY(100) 配对 SELL(110)
        assert pairs[0]["pnl"] == pytest.approx(10.0)

    def test_fifo_order(self):
        """FIFO 配对：先开的仓先平"""
        from backend.trading.pnl import pair_trades
        t = self._base_time()
        rows = [
            _make_trade("BUY", 100.0, t),                           # 先买
            _make_trade("BUY", 200.0, t + timedelta(hours=1)),       # 后买
            _make_trade("SELL", 110.0, t + timedelta(hours=2)),      # 平第一笔
            _make_trade("SELL", 220.0, t + timedelta(hours=3)),      # 平第二笔
        ]
        pairs = pair_trades(rows, sort_order="asc")
        assert len(pairs) == 2
        assert pairs[0]["pnl"] == pytest.approx(10.0)    # BUY100 -> SELL110
        assert pairs[1]["pnl"] == pytest.approx(20.0)    # BUY200 -> SELL220

    def test_empty_rows(self):
        """空列表不报错"""
        from backend.trading.pnl import pair_trades
        pairs = pair_trades([], sort_order="asc")
        assert pairs == []

    def test_single_trade(self):
        """单条记录无法配对"""
        from backend.trading.pnl import pair_trades
        t = self._base_time()
        rows = [_make_trade("BUY", 100.0, t)]
        pairs = pair_trades(rows, sort_order="asc")
        assert pairs == []

    def test_cover_before_short_ignored(self):
        """COVER 出现在 SHORT 之前时跳过"""
        from backend.trading.pnl import pair_trades
        t = self._base_time()
        rows = [
            _make_trade("COVER", 90.0, t),
            _make_trade("SHORT", 100.0, t + timedelta(hours=1)),
        ]
        pairs = pair_trades(rows, sort_order="asc")
        assert pairs == []

    def test_dict_input(self):
        """支持字典格式的输入"""
        from backend.trading.pnl import pair_trades
        t = self._base_time()
        rows = [
            {"side": "BUY", "quote_amount": 100.0, "created_at": t},
            {"side": "SELL", "quote_amount": 115.0, "created_at": t + timedelta(hours=1)},
        ]
        pairs = pair_trades(rows, sort_order="asc")
        assert len(pairs) == 1
        assert pairs[0]["pnl"] == pytest.approx(15.0)

    def test_open_time_recorded(self):
        """配对结果记录开仓时间"""
        from backend.trading.pnl import pair_trades
        t = self._base_time()
        rows = [
            _make_trade("BUY", 100.0, t),
            _make_trade("SELL", 110.0, t + timedelta(hours=1)),
        ]
        pairs = pair_trades(rows, sort_order="asc")
        assert pairs[0]["open_time"] == t
        assert pairs[0]["close_time"] == t + timedelta(hours=1)
