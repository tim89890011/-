# History Regression Map

> Generated: 2026-02-23
> Source: _archive_py/ patch files, REFACTOR_DIAGNOSIS.md, and project codebase analysis

This document maps historical regression themes (evidenced by 13 patch files in the
deleted `_archive_py/` directory) to current code modules, the appropriate test type,
and the minimum verifiable assertion for each theme.

---

## Historical Patch Evidence

The following 13 patch files were found in `_archive_py/` (now deleted, confirmed via
REFACTOR_DIAGNOSIS.md section 17):

```
patch_btn_move.py         patch_close_btn_fix.py      patch_close_btn_pos.py
patch_close_reason.py     patch_exchange_pnl.py        patch_leverage_pnl.py
patch_leverage_pnl_v2.py  patch_p0_p1.py               patch_reason_inline.py
patch_reason_tag.py       patch_save_record.py          patch_single_close.py
patch_tp_priority.py
```

---

## Theme-to-Module Mapping

### Theme 1: TP/SL/TrailingStop/tp_priority

| Aspect | Detail |
|--------|--------|
| Historical patches | `patch_tp_priority.py` |
| Current modules | `backend/trading/_tpsl_monitor.py`, `backend/trading/executor.py`, `backend/trading/_signal_execution.py` |
| Test type needed | **pytest** (unit: price calculation, ATR bounds, tighten/expire logic) |
| Minimum assertion | Long TP > entry, short TP < entry; ATR-based TP/SL clamped to [2.5,8.0]/[1.5,4.0]; trailing stop expires after 30min |
| Current coverage | `test_executor_core.py::TestTpSlPriceCalculation` (4 tests), `TestTightenTrailingStop` (3 tests), `TestGetSavedTpSl` (3 tests) |

### Theme 2: Close Operations (single close, close reason, close button)

| Aspect | Detail |
|--------|--------|
| Historical patches | `patch_single_close.py`, `patch_close_reason.py`, `patch_close_btn_fix.py`, `patch_close_btn_pos.py` |
| Current modules | `backend/trading/_trading_ops.py` (close logic), `backend/trading/executor.py` (cooldown), `frontend/js/trading-panel.js` (UI buttons) |
| Test type needed | **pytest** (unit: close cooldown constant), **E2E** (Playwright: close button renders and fires correctly) |
| Minimum assertion | `_CLOSE_COOLDOWN_SECONDS == 30`; close button triggers correct API call |
| Current coverage | `test_executor_core.py::TestCloseCooldownConstant` (1 test). **No E2E tests for close UI.** |

### Theme 3: Leverage PnL / Exchange PnL / Trade Pairing

| Aspect | Detail |
|--------|--------|
| Historical patches | `patch_leverage_pnl.py`, `patch_leverage_pnl_v2.py`, `patch_exchange_pnl.py` |
| Current modules | `backend/trading/pnl.py` (`calc_pnl_pct`, `pair_trades`) |
| Test type needed | **pytest** (unit: PnL calculation with various leverage, long/short, pairing FIFO) |
| Minimum assertion | `calc_pnl_pct(entry=100, current=105, side="long", leverage=3) == 15.0`; `pair_trades` correctly matches BUY/SELL pairs with FIFO ordering |
| Current coverage | `test_pnl.py::TestCalcPnlPct` (10 tests, including leverage), `test_pnl.py::TestPairTrades` (14 tests) |

### Theme 4: Reason Display and Tags

| Aspect | Detail |
|--------|--------|
| Historical patches | `patch_reason_inline.py`, `patch_reason_tag.py` |
| Current modules | `backend/ai_engine/schemas.py` (SignalOutput.reason, .risk_level), `frontend/js/ai-signal.js` (rendering) |
| Test type needed | **pytest** (unit: schema default fields), **contract** (WS message contains `reason` field), **E2E** (reason tag rendered in UI) |
| Minimum assertion | `SignalOutput(signal="HOLD", confidence=50).reason == ""`; WS broadcast JSON includes `reason` key |
| Current coverage | `test_signal_schema.py::TestSignalOutputModel::test_default_fields` covers schema defaults. **No contract or E2E tests.** |

### Theme 5: UI Buttons/Layout

| Aspect | Detail |
|--------|--------|
| Historical patches | `patch_btn_move.py`, `patch_close_btn_pos.py` |
| Current modules | `frontend/js/trading-panel.js` (button rendering and positioning) |
| Test type needed | **E2E** (Playwright: button visible, clickable, correct position) |
| Minimum assertion | Trade action buttons are rendered and responsive to click events |
| Current coverage | **No E2E tests exist.** |

### Theme 6: Frontend-Backend WebSocket Field Contract

| Aspect | Detail |
|--------|--------|
| Historical patches | `patch_save_record.py`, `patch_p0_p1.py` |
| Current modules | `backend/websocket/manager.py` (broadcast functions), `backend/websocket/routes.py`, `frontend/js/websocket.js` (message dispatch) |
| Test type needed | **contract** (JSON schema of WS messages matches frontend expectations), **pytest** (broadcast functions send correct JSON structure) |
| Minimum assertion | `broadcast_signal({"action": "BUY"})` sends JSON with `type="signal"` wrapper; `broadcast_trade_status(...)` sends JSON with `type="trade_status"` wrapper |
| Current coverage | `test_websocket.py::TestBroadcastFunctions` (9 tests: signal, trade_status, order, position, balance). Verifies calls are made, but **does not assert JSON field structure/schema.** |

### Theme 7: Callback/Signal Chain Integrity

| Aspect | Detail |
|--------|--------|
| Historical patches | (Implicit from all patches; root cause of many regressions per REFACTOR_DIAGNOSIS section 3) |
| Current modules | `backend/ai_engine/debate.py` (callback setters), `backend/main.py` (callback wiring) |
| Test type needed | **pytest** (unit: callback registration, invocation, exception isolation) |
| Minimum assertion | `set_signal_broadcast_callback(fn)` stores `fn`; callback fires on BUY/SELL; does not fire on HOLD; exception in callback does not propagate |
| Current coverage | `test_callback_wiring.py` (11 tests: registration, invocation, exception safety, HOLD suppression) |

### Theme 8: Signal Schema Validation

| Aspect | Detail |
|--------|--------|
| Historical patches | (Implicit; REFACTOR_DIAGNOSIS section 15 documents missing schema validation as root cause) |
| Current modules | `backend/ai_engine/schemas.py` (SignalOutput Pydantic model), `backend/ai_engine/json_parser.py` |
| Test type needed | **pytest** (unit: schema validation, parser fallback strategies, invalid input rejection) |
| Minimum assertion | `SignalOutput(signal="INVALID", confidence=50)` raises exception; `parse_signal_from_text("random text")` returns None with warning log |
| Current coverage | `test_signal_schema.py` (18 tests), `test_json_parser.py` (9 tests) |

### Theme 9: Symbol Format Normalization

| Aspect | Detail |
|--------|--------|
| Historical patches | (Implicit; REFACTOR_DIAGNOSIS section 4.3 documents 15+ ad-hoc conversions) |
| Current modules | `backend/utils/symbol.py` (`to_raw`, `to_ccxt`, `to_base`) |
| Test type needed | **pytest** (unit: conversion correctness for various formats) |
| Minimum assertion | `to_raw("BTC/USDT:USDT") == "BTCUSDT"`; `to_ccxt("btcusdt") == "BTC/USDT:USDT"` |
| Current coverage | `test_symbol.py` (12 tests) |

### Theme 10: Market Regime Classification

| Aspect | Detail |
|--------|--------|
| Historical patches | (Implicit; REFACTOR_DIAGNOSIS section 4.2 documents cross-file duplication) |
| Current modules | `backend/market/regime.py` (`classify_market_regime`, `is_volatile`, `is_squeeze`) |
| Test type needed | **pytest** (unit: regime classification logic, threshold constants) |
| Minimum assertion | High ATR returns "剧烈波动"; aligned MAs return trend; default returns "震荡行情" |
| Current coverage | `test_regime.py` (11 tests) |
