# History Regression Report

> Generated: 2026-02-23
> Test environment: Python 3.13.1, pytest 9.0.2, macOS Darwin 25.2.0
> Full test output: artifacts/history_regression.log

---

## Executive Summary

- **Total tests executed:** 171 (full suite), 86 (targeted regression filter)
- **Pass rate:** 171/171 (100%) -- all tests pass
- **Themes with test coverage:** 7 of 10 (partial or full)
- **Themes with zero coverage:** 3 (close flow, UI buttons, WS field contract schema)
- **Blocking items:** 1 (repository safety: secrets in tracked file)

---

## Per-Theme PASS/FAIL Table

| # | Theme | Patch Evidence | Test Count | Test Result | Coverage Level | Verdict |
|---|-------|---------------|------------|-------------|----------------|---------|
| 1 | TP/SL/Trailing/tp_priority | `patch_tp_priority.py` | 10 | ALL PASS | Unit price calc only; no exchange integration | **PARTIAL** |
| 2 | Close operations | `patch_single_close.py`, `patch_close_reason.py`, `patch_close_btn_fix.py`, `patch_close_btn_pos.py` | 1 | PASS | Constant only; no close flow | **GAP** |
| 3 | Leverage PnL / Trade Pairing | `patch_leverage_pnl.py`, `patch_leverage_pnl_v2.py`, `patch_exchange_pnl.py` | 24 | ALL PASS | Comprehensive unit tests | **PASS** |
| 4 | Reason display and tags | `patch_reason_inline.py`, `patch_reason_tag.py` | 1 | PASS | Schema defaults only | **GAP** |
| 5 | UI buttons/layout | `patch_btn_move.py`, `patch_close_btn_pos.py` | 0 | N/A | No tests | **GAP** |
| 6 | WS field contract | `patch_save_record.py`, `patch_p0_p1.py` | 9 | ALL PASS | Broadcast calls verified; JSON structure not validated | **PARTIAL** |
| 7 | Callback/signal chain | (root cause per REFACTOR_DIAGNOSIS) | 11 | ALL PASS | Registration, invocation, exception safety | **PASS** |
| 8 | Signal schema validation | (REFACTOR_DIAGNOSIS section 15) | 27 | ALL PASS | Pydantic model + parser + fallback strategies | **PASS** |
| 9 | Symbol format | (REFACTOR_DIAGNOSIS section 4.3) | 12 | ALL PASS | `to_raw`, `to_ccxt`, `to_base` conversions | **PASS** |
| 10 | Market regime | (REFACTOR_DIAGNOSIS section 4.2) | 11 | ALL PASS | Classification, volatile, squeeze detection | **PASS** |

---

## Test Evidence Details

### Theme 1: TP/SL/Trailing (PARTIAL)

**Test file:** `tests/test_executor_core.py`

Tests present:
- `TestTpSlPriceCalculation::test_long_tp_sl_prices` -- long TP > entry, SL < entry
- `TestTpSlPriceCalculation::test_short_tp_sl_prices` -- short TP < entry, SL > entry
- `TestTpSlPriceCalculation::test_higher_leverage_narrows_range` -- leverage effect on TP distance
- `TestTpSlPriceCalculation::test_atr_based_tp_sl_bounds` -- ATR clamp [2.5,8.0]/[1.5,4.0]
- `TestTightenTrailingStop::test_tighten_sets_flag` -- SELL tighten mode activates
- `TestTightenTrailingStop::test_not_tightened_initially` -- default is not tightened
- `TestTightenTrailingStop::test_tighten_expires_after_30min` -- 30-minute expiry
- `TestGetSavedTpSl::test_returns_params` -- retrieves saved TP/SL percentages
- `TestGetSavedTpSl::test_returns_none_when_missing` -- graceful None for missing
- `TestGetSavedTpSl::test_returns_none_when_no_tp_pct` -- None when incomplete data

**Gap:** No test for `_place_exchange_tp_sl()` integration (creating actual exchange orders). No test for TP priority when trailing stop conflicts (the exact issue `patch_tp_priority.py` fixed).

### Theme 2: Close Operations (GAP)

**Test file:** `tests/test_executor_core.py`

Tests present:
- `TestCloseCooldownConstant::test_close_cooldown_is_30` -- asserts `_CLOSE_COOLDOWN_SECONDS == 30`

**Gap:** No test for:
- Close order execution flow (calling exchange.create_order with correct side)
- Close cooldown enforcement (rejection within 30s window)
- Close reason persistence to TradeRecord
- Single close isolation (closing one position does not affect others)
- Close button UI rendering and behavior (E2E)

### Theme 3: Leverage PnL / Trade Pairing (PASS)

**Test files:** `tests/test_pnl.py`

Tests present:
- `TestCalcPnlPct`: 10 tests covering long/short profit/loss, leverage 1/3/5, zero/negative entry, no-change
- `TestPairTrades`: 14 tests covering simple long/short, FIFO ordering, multiple pairs, mixed long/short, unpaired trades, empty/single rows, dict input, desc ordering

**Assessment:** This is the best-covered regression theme. Both `calc_pnl_pct` and `pair_trades` have thorough unit tests including edge cases.

### Theme 4: Reason Display (GAP)

**Test file:** `tests/test_signal_schema.py`

Tests present:
- `test_default_fields` -- `reason` defaults to `""`, `risk_level` defaults to `"中"`
- `test_full_signal_with_all_fields` -- reason="MACD 死叉" preserved

**Gap:** No contract test verifying reason survives WS serialization. No E2E test for frontend rendering.

### Theme 5: UI Buttons/Layout (GAP)

**No tests exist.** No E2E framework is configured for the project.

### Theme 6: WS Field Contract (PARTIAL)

**Test file:** `tests/test_websocket.py`

Tests present:
- 9 broadcast function tests verifying calls to `ws.send_text()`
- Verifies broadcast_signal, broadcast_trade_status, broadcast_order_update, broadcast_position_update, broadcast_balance_update

**Gap:** Tests verify that `send_text` is called but do not assert the JSON structure or field names of the payload. This means a field rename or removal would not be caught.

### Theme 7: Callback/Signal Chain (PASS)

**Test file:** `tests/test_callback_wiring.py`

Tests present:
- 4 registration tests (set, replace, initially None)
- 7 invocation tests (BUY triggers both callbacks, HOLD suppresses, exception isolation, None safety)

### Theme 8: Signal Schema Validation (PASS)

**Test files:** `tests/test_signal_schema.py` (18 tests), `tests/test_json_parser.py` (9 tests)

Comprehensive coverage of Pydantic model validation, confidence clamping, signal type normalization, parser fallback strategies (direct JSON, markdown block, regex extraction, Chinese text), and error logging.

### Theme 9: Symbol Format (PASS)

**Test file:** `tests/test_symbol.py` (12 tests)

All three conversion functions (`to_raw`, `to_ccxt`, `to_base`) tested with multiple coin types and case variations.

### Theme 10: Market Regime (PASS)

**Test file:** `tests/test_regime.py` (11 tests)

Classification logic, volatile detection, squeeze detection, threshold constants, and edge cases (empty indicators) all tested.

---

## Blocking Items

### BLOCK-1: Repository Safety -- Secrets in Tracked File

**File:** `REFACTOR_DIAGNOSIS.md` (line 284)
**Issue:** Contains real `DEEPSEEK_API_KEY=sk-2a3a102d1e314d15bae67034e0d0ec46` and other credentials
**Impact:** Anyone with repo access can extract production credentials
**Required action:** Redact secrets from `REFACTOR_DIAGNOSIS.md`, rotate all exposed keys
**See:** `artifacts/repo_safety.log` for full detail

---

## Non-Blocking Suggestions

### Suggestion 1: Add WS Field Contract Tests (Priority: HIGH)

Create `tests/test_ws_contract.py` that:
- Captures the actual JSON sent by each broadcast function
- Asserts field names match what `frontend/js/websocket.js` expects
- Prevents silent field renames that historically caused 2+ patches

### Suggestion 2: Add Close Flow Integration Tests (Priority: HIGH)

Create `tests/test_close_flow.py` that:
- Mocks exchange and tests the full close path
- Verifies cooldown enforcement (reject within 30s)
- Verifies close reason is persisted in TradeRecord
- Historically the most-patched area (4/13 patches)

### Suggestion 3: Add TP/SL Exchange Placement Test (Priority: MEDIUM)

Extend `tests/test_executor_core.py` or create `tests/test_tpsl_integration.py` that:
- Mocks exchange and calls `_place_exchange_tp_sl()`
- Verifies correct order parameters for long/short
- Tests TP priority when trailing stop is also active

### Suggestion 4: Set Up E2E Test Infrastructure (Priority: MEDIUM)

Create `e2e/` directory with Playwright configuration:
- Test critical UI flows: close button, trade panel, signal display
- Prevent layout/button regression that historically required patches

### Suggestion 5: Add Reason Propagation Contract Test (Priority: LOW)

Extend `tests/test_signal_schema.py`:
- Verify reason field survives debate -> WS broadcast -> JSON serialization
- Verify risk_level is one of the expected values ["低", "中", "高"]

---

## Test Infrastructure Assessment

| Component | Status | Notes |
|-----------|--------|-------|
| conftest.py | Good | In-memory SQLite, mock exchange, factory functions |
| pytest fixtures | Good | async DB session with rollback, mock AutoTrader |
| Test isolation | Good | Each test gets fresh session/state |
| asyncio support | Good | pytest-asyncio configured with auto mode |
| CI integration | Exists | `scripts/ci.sh` present; `.github/` directory exists |
| Code coverage tool | Missing | No pytest-cov or coverage configuration |
| E2E framework | Missing | No Playwright or similar configured |
| Contract testing | Missing | No schema validation for WS messages |

---

## Conclusion

The project has a solid foundation of 171 passing unit tests covering the most critical
business logic (PnL calculation, signal schema validation, callback wiring, symbol conversion,
market regime classification). However, three historically problematic areas remain untested:

1. **Close operations** (4/13 historical patches, only 1 constant-check test)
2. **UI buttons/layout** (2/13 historical patches, zero tests)
3. **WS field contract** (2/13 historical patches, broadcast tested but JSON schema not validated)

These gaps directly correlate with the themes that required the most patches historically,
indicating they are the highest-risk areas for future regressions.

**Repository safety gate FAILS** due to secrets in `REFACTOR_DIAGNOSIS.md`. This must be
resolved before any release.
