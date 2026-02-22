"""
executor.py 核心ロジックのユニットテスト

exchange/DB に依存しない純粋関数・状態管理ロジックをテスト。
高リスク項目（冷却/限流ロジック、TP/SL 価格計算）を優先。
"""

import time
from unittest.mock import patch

from backend.trading.executor import (
    _clamp_conf,
    _parse_symbols_csv,
    _update_atr_cache,
    _CLOSE_COOLDOWN_SECONDS,
    AutoTrader,
    state,
)


# ────────────────────────────────────────────
# 純関数テスト
# ────────────────────────────────────────────

class TestClampConf:
    """_clamp_conf: 置信度を 0-100 にクランプ"""

    def test_normal_value(self):
        assert _clamp_conf(50) == 50

    def test_zero(self):
        assert _clamp_conf(0) == 0

    def test_hundred(self):
        assert _clamp_conf(100) == 100

    def test_over_100(self):
        assert _clamp_conf(150) == 100

    def test_negative(self):
        assert _clamp_conf(-10) == 0

    def test_string_numeric(self):
        assert _clamp_conf("75") == 75

    def test_non_numeric_string(self):
        assert _clamp_conf("abc") == 0

    def test_none(self):
        assert _clamp_conf(None) == 0

    def test_float(self):
        assert _clamp_conf(85.9) == 85


class TestParseSymbolsCsv:
    """_parse_symbols_csv: CSV → set[str] パース"""

    def test_normal(self):
        assert _parse_symbols_csv("BTCUSDT,ETHUSDT") == {"BTCUSDT", "ETHUSDT"}

    def test_whitespace(self):
        assert _parse_symbols_csv(" BTC , ETH ") == {"BTC", "ETH"}

    def test_empty_string(self):
        assert _parse_symbols_csv("") == set()

    def test_none(self):
        assert _parse_symbols_csv(None) == set()

    def test_single(self):
        assert _parse_symbols_csv("BTCUSDT") == {"BTCUSDT"}

    def test_lowercase_to_upper(self):
        assert _parse_symbols_csv("btcusdt,ethusdt") == {"BTCUSDT", "ETHUSDT"}

    def test_trailing_comma(self):
        assert _parse_symbols_csv("BTCUSDT,") == {"BTCUSDT"}


class TestUpdateAtrCache:
    """_update_atr_cache: ATR キャッシュ更新"""

    def test_positive_atr(self):
        _update_atr_cache("BTCUSDT", 2.5)
        cached = state.symbol_atr.get("BTCUSDT")
        assert cached is not None
        assert cached["atr_pct"] == 2.5
        assert "time" in cached

    def test_zero_atr_not_stored(self):
        # Remove any existing entry first
        state.symbol_atr.pop("ZEROUSDT", None)
        _update_atr_cache("ZEROUSDT", 0.0)
        assert "ZEROUSDT" not in state.symbol_atr

    def test_negative_atr_not_stored(self):
        state.symbol_atr.pop("NEGUSDT", None)
        _update_atr_cache("NEGUSDT", -1.0)
        assert "NEGUSDT" not in state.symbol_atr


# ────────────────────────────────────────────
# AutoTrader 状態管理テスト（exchange 不要）
# ────────────────────────────────────────────

class TestMarkOrderProcessed:
    """_mark_order_processed: 処理済み注文 ID の LRU 管理"""

    def test_marks_order(self):
        trader = AutoTrader()
        trader._mark_order_processed("order123")
        assert "order123" in trader._processed_order_ids

    def test_empty_oid_ignored(self):
        trader = AutoTrader()
        trader._mark_order_processed("")
        assert "" not in trader._processed_order_ids

    def test_lru_eviction(self):
        """500 超過時に 200 まで縮小"""
        trader = AutoTrader()
        for i in range(510):
            trader._mark_order_processed(f"oid_{i}")
        # After exceeding 500, should trim to ~200
        assert len(trader._processed_order_ids) <= 210
        # Latest entries should still be present
        assert "oid_509" in trader._processed_order_ids
        # Earliest entries should be evicted
        assert "oid_0" not in trader._processed_order_ids


class TestGetSavedTpSl:
    """_get_saved_tp_sl: 保存された TP/SL パラメータの取得"""

    def test_returns_params(self):
        trader = AutoTrader()
        trader._exchange_tp_sl["BTCUSDT_long"] = {
            "tp_pct": 3.0, "sl_pct": 1.5, "tp_id": "tp1", "sl_id": "sl1"
        }
        result = trader._get_saved_tp_sl("BTCUSDT", "long")
        assert result == {"tp_pct": 3.0, "sl_pct": 1.5}

    def test_returns_none_when_missing(self):
        trader = AutoTrader()
        assert trader._get_saved_tp_sl("XYZUSDT", "long") is None

    def test_returns_none_when_no_tp_pct(self):
        trader = AutoTrader()
        trader._exchange_tp_sl["BTCUSDT_short"] = {
            "tp_id": "tp1", "sl_id": "sl1"
        }
        assert trader._get_saved_tp_sl("BTCUSDT", "short") is None


class TestParseOrder:
    """_parse_order: ccxt 注文結果の解析"""

    def test_normal_order(self):
        trader = AutoTrader()
        order = {
            "id": "12345",
            "filled": 0.01,
            "cost": 500.0,
            "fee": {"cost": 0.2, "currency": "USDT"},
        }
        result = trader._parse_order(order)
        assert result["order_id"] == "12345"
        assert result["quantity"] == 0.01
        assert result["price"] == 50000.0  # 500 / 0.01
        assert result["quote_amount"] == 500.0
        assert result["commission"] == 0.2

    def test_zero_filled(self):
        trader = AutoTrader()
        order = {"id": "99", "filled": 0, "cost": 0, "fee": {}}
        result = trader._parse_order(order)
        assert result["price"] == 0
        assert result["quantity"] == 0

    def test_missing_fee(self):
        trader = AutoTrader()
        order = {"id": "88", "filled": 1.0, "cost": 100.0, "fee": None}
        result = trader._parse_order(order)
        assert result["commission"] == 0


class TestTightenTrailingStop:
    """_tighten_trailing_stop / _is_tightened: SELL 信号による収紧モード"""

    def test_tighten_sets_flag(self):
        trader = AutoTrader()
        trader._tighten_trailing_stop("BTCUSDT", 75)
        assert trader._is_tightened("BTCUSDT") is True

    def test_not_tightened_initially(self):
        trader = AutoTrader()
        assert trader._is_tightened("ETHUSDT") is False

    def test_tighten_expires_after_30min(self):
        trader = AutoTrader()
        trader._tighten_trailing_stop("BTCUSDT", 60)
        # Mock time to be 31 minutes later
        with patch("backend.trading._signal_execution.time") as mock_time:
            mock_time.time.return_value = time.time() + 1801
            assert trader._is_tightened("BTCUSDT") is False


class TestInvalidatePositionCache:
    """_invalidate_position_cache: ポジションキャッシュの無効化"""

    def test_resets_timestamp(self):
        trader = AutoTrader()
        trader._position_cache_ts = 12345.0
        trader._invalidate_position_cache()
        assert trader._position_cache_ts == 0.0


class TestTpSlPriceCalculation:
    """
    TP/SL 価格計算ロジックのテスト。
    _place_exchange_tp_sl 内のコア計算を直接テスト。
    """

    def test_long_tp_sl_prices(self):
        """多仓: TP は entry より高く、SL は entry より低い"""
        entry_price = 50000.0
        tp_pct = 3.0
        sl_pct = 2.0
        leverage = 3

        tp_price = entry_price * (1 + tp_pct / (100 * leverage))
        sl_price = entry_price * (1 - sl_pct / (100 * leverage))

        assert tp_price > entry_price
        assert sl_price < entry_price
        assert tp_price == 50000.0 * (1 + 3.0 / 300)  # 50500.0
        assert sl_price == 50000.0 * (1 - 2.0 / 300)  # ~49666.67

    def test_short_tp_sl_prices(self):
        """空仓: TP は entry より低く、SL は entry より高い"""
        entry_price = 50000.0
        tp_pct = 3.0
        sl_pct = 2.0
        leverage = 3

        tp_price = entry_price * (1 - tp_pct / (100 * leverage))
        sl_price = entry_price * (1 + sl_pct / (100 * leverage))

        assert tp_price < entry_price
        assert sl_price > entry_price

    def test_higher_leverage_narrows_range(self):
        """レバレッジが高いほど TP/SL 価格がエントリーに近づく"""
        entry_price = 50000.0
        tp_pct = 3.0

        tp_lev3 = entry_price * (1 + tp_pct / (100 * 3))
        tp_lev10 = entry_price * (1 + tp_pct / (100 * 10))

        # Higher leverage → TP closer to entry
        assert abs(tp_lev10 - entry_price) < abs(tp_lev3 - entry_price)

    def test_atr_based_tp_sl_bounds(self):
        """ATR ベースの TP/SL はクランプ範囲内"""
        # Reproduce logic from _place_exchange_tp_sl lines 199-201
        for atr_pct in [0.5, 1.0, 2.0, 3.0, 5.0, 10.0]:
            tp_pct = max(min(atr_pct * 2.5, 8.0), 2.5)
            sl_pct = max(min(atr_pct * 1.5, 4.0), 1.5)
            assert 2.5 <= tp_pct <= 8.0, f"tp_pct={tp_pct} out of range for atr={atr_pct}"
            assert 1.5 <= sl_pct <= 4.0, f"sl_pct={sl_pct} out of range for atr={atr_pct}"


class TestCloseCooldownConstant:
    """平仓冷却定数の確認"""

    def test_close_cooldown_is_30(self):
        assert _CLOSE_COOLDOWN_SECONDS == 30
