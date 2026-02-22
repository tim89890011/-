# Regression Coverage Gap Analysis

> Generated: 2026-02-23
> Based on: tests/ directory analysis, HISTORY_REGRESSION_MAP.md themes

---

## Summary

| Theme | pytest Tests | Contract Tests | E2E Tests | Gap Severity |
|-------|-------------|----------------|-----------|--------------|
| 1. TP/SL/Trailing/tp_priority | 10 tests | 0 | 0 | **MEDIUM** - price calc covered, but no integration test for actual exchange TP/SL order placement |
| 2. Close operations | 1 test (cooldown constant) | 0 | 0 | **HIGH** - only constant check; no close flow, close reason, or UI test |
| 3. Leverage PnL / Trade Pairing | 24 tests | 0 | 0 | **LOW** - well covered at unit level |
| 4. Reason display and tags | 1 test (schema defaults) | 0 | 0 | **HIGH** - no WS contract test; no frontend rendering test |
| 5. UI buttons/layout | 0 | 0 | 0 | **CRITICAL** - zero coverage; historically most patched area |
| 6. WS field contract | 9 tests (broadcast functions) | 0 | 0 | **HIGH** - tests verify calls happen but do not assert JSON structure |
| 7. Callback/signal chain | 11 tests | 0 | 0 | **LOW** - well covered at unit level |
| 8. Signal schema validation | 27 tests | 0 | 0 | **LOW** - well covered at unit level |
| 9. Symbol format | 12 tests | 0 | 0 | **LOW** - well covered at unit level |
| 10. Market regime | 11 tests | 0 | 0 | **LOW** - well covered at unit level |

---

## Detailed Gap Analysis

### Gap 1: Close Flow Integration (HIGH)

**What exists:**
- `test_executor_core.py::TestCloseCooldownConstant::test_close_cooldown_is_30` -- asserts constant value only

**What is missing:**
- Close order flow test: given a position, calling close should create the correct market order
- Close cooldown enforcement: attempting close within 30s should be rejected
- Close reason propagation: close reason should appear in TradeRecord and WS broadcast
- Single close correctness: closing one position should not affect others

**Historical evidence:** 4 patch files (`patch_single_close.py`, `patch_close_reason.py`, `patch_close_btn_fix.py`, `patch_close_btn_pos.py`)

**Suggested test file:** `tests/test_close_flow.py`
**Suggested assertions:**
```python
# 1. Close cooldown enforced
assert trader._check_close_cooldown("BTCUSDT") is True  # within 30s
# 2. Close order creates correct side
assert order["side"] == "sell" for long close
# 3. Close reason persisted
assert record.source contains close reason
```

---

### Gap 2: WS Field Contract (HIGH)

**What exists:**
- `test_websocket.py::TestBroadcastFunctions` -- 9 tests verifying broadcast functions call `ws.send_text()`

**What is missing:**
- JSON structure assertion: the actual JSON payload sent over WS should match a schema
- Field completeness: signal broadcasts should include `signal`, `confidence`, `reason`, `risk_level`, `symbol`, `timestamp`
- Trade status broadcasts should include `status`, `symbol`, `side`, `price`, `quantity`

**Historical evidence:** `patch_save_record.py`, `patch_p0_p1.py` (field mismatch between backend and frontend)

**Suggested test file:** `tests/test_ws_contract.py`
**Suggested assertions:**
```python
# 1. Signal broadcast JSON structure
payload = json.loads(ws.send_text.call_args[0][0])
assert "type" in payload
assert "signal" in payload["data"]
assert "confidence" in payload["data"]

# 2. Trade status JSON structure
payload = json.loads(ws.send_text.call_args[0][0])
assert payload["type"] == "trade_status"
```

---

### Gap 3: Reason Display/Tags (HIGH)

**What exists:**
- `test_signal_schema.py::TestSignalOutputModel::test_default_fields` -- confirms `reason` defaults to `""`

**What is missing:**
- End-to-end: reason from AI -> debate -> WS -> frontend rendering
- Tag format: `risk_level` value should be one of ["低", "中", "高"]
- Reason not truncated or lost during WS serialization

**Historical evidence:** `patch_reason_inline.py`, `patch_reason_tag.py`

**Suggested test file:** `tests/test_signal_schema.py` (extend existing) or `tests/test_ws_contract.py`

---

### Gap 4: UI Buttons/Layout (CRITICAL)

**What exists:** Nothing

**What is missing:**
- E2E test for trade panel button rendering
- Button click fires correct API call
- Button position/layout not broken after code changes

**Historical evidence:** `patch_btn_move.py`, `patch_close_btn_pos.py`

**Suggested approach:** Playwright E2E tests in `e2e/` directory
**Suggested assertions:**
```javascript
// 1. Close button exists and is clickable
await expect(page.locator('[data-testid="close-position-btn"]')).toBeVisible()
// 2. Buy/Sell buttons exist
await expect(page.locator('[data-testid="buy-btn"]')).toBeEnabled()
```

---

### Gap 5: TP/SL Exchange Order Placement (MEDIUM)

**What exists:**
- Price calculation formulas tested (4 tests)
- ATR-based bounds tested (1 test)
- Trailing stop tighten/expire tested (3 tests)
- Saved TP/SL retrieval tested (3 tests)

**What is missing:**
- Integration test: `_place_exchange_tp_sl()` actually calls `exchange.create_order()` with correct params
- TP priority logic: when TP and trailing stop conflict, which takes precedence

**Historical evidence:** `patch_tp_priority.py`

**Suggested test file:** `tests/test_tpsl_integration.py`
**Suggested assertions:**
```python
# 1. exchange.create_order called with TP order
exchange.create_order.assert_any_call(symbol, "TAKE_PROFIT_MARKET", ...)
# 2. TP priority over trailing when both active
assert tp_order_placed_before_trailing
```

---

## Coverage Statistics

### By test file:

| File | Tests | Lines | Themes Covered |
|------|-------|-------|----------------|
| test_pnl.py | 15 | 270 | PnL calc, trade pairing |
| test_signal_schema.py | 18 | 189 | Signal schema, JSON parsing |
| test_executor_core.py | 18 | 279 | TP/SL calc, cooldown, trailing stop, clamp, parse_order |
| test_callback_wiring.py | 11 | 229 | Callback registration/invocation |
| test_websocket.py | 17 | 300 | WS broadcast functions, auth, health |
| test_json_parser.py | 9 | 107 | JSON parsing strategies |
| test_symbol.py | 12 | 65 | Symbol format conversion |
| test_regime.py | 11 | 135 | Market regime classification |
| conftest.py | - | 306 | Test infrastructure (DB, mock trader, factories) |
| **TOTAL** | **111** | **1,880** | 7 of 10 themes partially covered |

### By coverage type:

| Type | Count | Status |
|------|-------|--------|
| Unit (pytest) | 111 tests | Exists, covers 7/10 themes |
| Contract (WS schema) | 0 tests | **Missing entirely** |
| Integration (exchange mock) | 0 tests | **Missing entirely** |
| E2E (Playwright) | 0 tests | **Missing entirely** |

---

## Priority Recommendations (suggest only, do not implement)

1. **P0:** Add WS field contract tests -- prevents the most common historical regression (field mismatch)
2. **P0:** Add close flow integration tests -- historically 4/13 patches were close-related
3. **P1:** Add TP/SL exchange placement integration test -- `patch_tp_priority.py` evidence
4. **P1:** Set up Playwright E2E for critical UI buttons -- `patch_btn_move.py` evidence
5. **P2:** Add reason propagation contract test -- `patch_reason_tag.py` evidence
