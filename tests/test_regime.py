"""backend/market/regime.py のテスト"""

from backend.market.regime import (
    classify_market_regime,
    is_volatile,
    is_squeeze,
    ATR_VOLATILE_THRESHOLD,
    BB_VOLATILE_THRESHOLD,
    BB_SQUEEZE_THRESHOLD,
    ATR_SQUEEZE_THRESHOLD,
)


def _make_indicators(
    *,
    price=100,
    bb_upper=105,
    bb_lower=95,
    bb_mid=100,
    atr=1.0,
    ma7=0,
    ma25=0,
    ma99=0,
):
    return {
        "price": price,
        "bollinger": {"upper": bb_upper, "lower": bb_lower, "middle": bb_mid},
        "atr": atr,
        "ma": {"ma7": ma7, "ma25": ma25, "ma99": ma99},
    }


class TestClassifyMarketRegime:
    """classify_market_regime 分類ロジック"""

    def test_volatile_by_atr(self):
        """ATR% が閾値超え → 剧烈波动"""
        ind = _make_indicators(price=100, atr=ATR_VOLATILE_THRESHOLD * 100 / 100 + 0.1)
        assert classify_market_regime(ind) == "剧烈波动"

    def test_volatile_by_bb_width(self):
        """BB幅 が閾値超え → 剧烈波动"""
        # bb_width = (upper - lower) / mid * 100 > BB_VOLATILE_THRESHOLD
        mid = 100
        spread = BB_VOLATILE_THRESHOLD * mid / 100 + 0.1
        ind = _make_indicators(bb_upper=mid + spread / 2 + 0.1, bb_lower=mid - spread / 2 - 0.1, bb_mid=mid)
        assert classify_market_regime(ind) == "剧烈波动"

    def test_trend_up(self):
        """MA7 > MA25 > MA99 + bb_width > 3 → 趋势行情(上涨)"""
        ind = _make_indicators(
            bb_upper=104, bb_lower=96, bb_mid=100,  # bb_width = 8% — but need >3 and <8 for trend
            atr=0.5, ma7=110, ma25=105, ma99=100,
        )
        # bb_width = (104-96)/100*100 = 8.0 → actually that equals BB_VOLATILE_THRESHOLD, which is ">"
        # Let's adjust to be just below volatile
        ind = _make_indicators(
            bb_upper=103.5, bb_lower=96.5, bb_mid=100,  # bb_width = 7%
            atr=0.5, ma7=110, ma25=105, ma99=100,
        )
        result = classify_market_regime(ind)
        assert result == "趋势行情(上涨)"

    def test_trend_down(self):
        """MA7 < MA25 < MA99 + bb_width > 3 → 趋势行情(下跌)"""
        ind = _make_indicators(
            bb_upper=103.5, bb_lower=96.5, bb_mid=100,  # bb_width = 7%
            atr=0.5, ma7=90, ma25=95, ma99=100,
        )
        result = classify_market_regime(ind)
        assert result == "趋势行情(下跌)"

    def test_range_market(self):
        """非波動・非トレンド → 震荡行情"""
        ind = _make_indicators(
            bb_upper=101, bb_lower=99, bb_mid=100,  # bb_width = 2%
            atr=0.5, ma7=100, ma25=100, ma99=100,  # MA not aligned (all equal)
        )
        assert classify_market_regime(ind) == "震荡行情"

    def test_narrow_bb_no_trend(self):
        """BB幅 < 3.0 + MA aligned → still 震荡行情 (bb_width threshold for trend)"""
        ind = _make_indicators(
            bb_upper=101.2, bb_lower=98.8, bb_mid=100,  # bb_width = 2.4%
            atr=0.5, ma7=110, ma25=105, ma99=100,
        )
        assert classify_market_regime(ind) == "震荡行情"

    def test_empty_indicators(self):
        """空dict → 震荡行情 (デフォルト)"""
        assert classify_market_regime({}) == "震荡行情"


class TestIsVolatile:
    def test_volatile_true(self):
        ind = _make_indicators(price=100, atr=3.5)
        assert is_volatile(ind) is True

    def test_volatile_false(self):
        ind = _make_indicators(price=100, atr=0.5, bb_upper=103, bb_lower=97)
        assert is_volatile(ind) is False


class TestIsSqueeze:
    def test_squeeze_true(self):
        """BB幅 < 2.0 and ATR% < 0.5 → squeeze"""
        ind = _make_indicators(
            bb_upper=100.8, bb_lower=99.2, bb_mid=100,  # bb_width = 1.6%
            price=100, atr=0.3,  # atr_pct = 0.3%
        )
        assert is_squeeze(ind) is True

    def test_squeeze_false_wide_bb(self):
        """BB幅 >= 2.0 → not squeeze"""
        ind = _make_indicators(
            bb_upper=102, bb_lower=98, bb_mid=100,  # bb_width = 4%
            price=100, atr=0.3,
        )
        assert is_squeeze(ind) is False

    def test_squeeze_false_high_atr(self):
        """ATR% >= 0.5 → not squeeze"""
        ind = _make_indicators(
            bb_upper=100.8, bb_lower=99.2, bb_mid=100,  # bb_width = 1.6%
            price=100, atr=0.6,  # atr_pct = 0.6%
        )
        assert is_squeeze(ind) is False

    def test_thresholds_match_constants(self):
        """閾値定数が期待値と一致"""
        assert ATR_VOLATILE_THRESHOLD == 3.0
        assert BB_VOLATILE_THRESHOLD == 8.0
        assert BB_SQUEEZE_THRESHOLD == 2.0
        assert ATR_SQUEEZE_THRESHOLD == 0.5
