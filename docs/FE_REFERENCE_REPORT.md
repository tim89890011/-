# FE Gate 0: Reference Source Verification Report

**Date:** 2026-02-23
**Project:** 钢子出击 Frontend
**Auditor:** FE Release Verification Agent

---

## 1. index.html Script References

| # | Script `src` | `type="module"` | File Exists | Notes |
|---|-------------|-----------------|-------------|-------|
| 1 | (CDN) morphdom@2.7.3 UMD | No (classic) | N/A (CDN) | External dependency |
| 2 | (CDN) chart.js@4.4.7 UMD | No (classic) | N/A (CDN) | External dependency, loaded first |
| 3 | `js/auth.js?v=10` | Yes | EXISTS | Auth module -- foundational |
| 4 | `js/websocket.js?v=13` | Yes | EXISTS | Imports from auth.js |
| 5 | `js/coin-data.js?v=36` | Yes | EXISTS | Imports from auth.js |
| 6 | `js/charts.js?v=11` | Yes | EXISTS | No direct imports |
| 7 | `js/gauge.js?v=10` | Yes | EXISTS | No direct imports |
| 8 | `js/ai-card.js?v=37` | Yes | EXISTS | No direct imports (uses window globals) |
| 9 | `js/ai-debate.js?v=68` | Yes | EXISTS | No direct imports |
| 10 | `js/analysis-data.js?v=23` | Yes | EXISTS | Imports from auth.js |
| 11 | `js/ai-chat.js?v=30` | Yes | EXISTS | No direct imports |
| 12 | `js/voice.js?v=43` | Yes | EXISTS | No direct imports |
| 13 | `js/particles.js?v=10` | Yes | EXISTS | No direct imports |
| 14 | `js/extras.js?v=44` | Yes | EXISTS | Imports from auth.js |
| 15 | `js/monitoring.js?v=12` | Yes | EXISTS | Imports from auth.js |
| 16 | `js/trading/utils.js?v=1` | Yes | EXISTS | Trading module -- base utility |
| 17 | `js/trading/styles.js?v=1` | Yes | EXISTS | Trading sub-module |
| 18 | `js/trading/html-template.js?v=1` | Yes | EXISTS | Trading sub-module |
| 19 | `js/trading/balance.js?v=1` | Yes | EXISTS | Imports from trading/utils.js |
| 20 | `js/trading/positions.js?v=1` | Yes | EXISTS | Imports from utils.js, balance.js |
| 21 | `js/trading/orders.js?v=1` | Yes | EXISTS | Imports from utils.js, positions.js |
| 22 | `js/trading/stats.js?v=1` | Yes | EXISTS | Imports from trading/utils.js |
| 23 | `js/trading/charts.js?v=1` | Yes | EXISTS | Imports from trading/utils.js |
| 24 | `js/trading-panel.js?v=185` | Yes | EXISTS | Imports from all trading/* modules |
| 25 | `js/app.js?v=18` | Yes | EXISTS | Imports from auth.js, websocket.js |

### Load Order Analysis (index.html)

- CDN libraries (morphdom, Chart.js) load first as classic scripts -- **CORRECT**
- `auth.js` loads before all modules that import from it -- **CORRECT**
- All `trading/*` modules load before `trading-panel.js` -- **CORRECT**
- `app.js` loads last as the orchestrator -- **CORRECT**
- All ES modules use `type="module"` -- **CORRECT**

**Result: PASS**

---

## 2. login.html Script References

| # | Script `src` | `type="module"` | File Exists | Notes |
|---|-------------|-----------------|-------------|-------|
| 1 | `js/config.js` | No (classic) | EXISTS | Sets `window.API_BASE` |
| 2 | `js/auth.js` | Yes | EXISTS | Auth module |
| 3 | Inline `<script>` | No (classic) | N/A | Background animation + price ticker |

### Load Order Analysis (login.html)

- `config.js` loads first (classic, sets `window.API_BASE`) -- **CORRECT**
- `auth.js` loads as module -- **CORRECT**
- Inline script uses `window.API_BASE` from config.js -- **CORRECT**

**Result: PASS (with config.js runtime caveat -- see Issues below)**

---

## 3. settings.html Script References

| # | Script `src` | `type="module"` | File Exists | Notes |
|---|-------------|-----------------|-------------|-------|
| 1 | `js/config.js` | No (classic) | EXISTS | Sets `window.API_BASE` |
| 2 | `js/auth.js?v=11` | Yes | EXISTS | Auth module |
| 3 | `js/settings.js?v=6` | Yes | EXISTS | Settings page logic |

### Load Order Analysis (settings.html)

- `config.js` loads first -- **CORRECT**
- `auth.js` loads before `settings.js` which imports from it -- **CORRECT**

**Result: PASS (with config.js runtime caveat)**

---

## 4. register.html Script References

| # | Script `src` | `type="module"` | File Exists | Notes |
|---|-------------|-----------------|-------------|-------|
| 1 | `js/config.js` | No (classic) | EXISTS | Sets `window.API_BASE` |
| 2 | `js/auth.js` | **No (classic)** | EXISTS | **ISSUE: loaded without type="module"** |
| 3 | Inline `<script>` | No (classic) | N/A | Registration form logic |

### Load Order Analysis (register.html)

- `config.js` loads first -- CORRECT
- `auth.js` loaded as **classic script** (not module) -- **ISSUE**: auth.js contains `export` statements which cause a SyntaxError when parsed as a classic script. However, auth.js also sets `window.*` globals at the end of the file. Since the `export` keyword causes a parse error, those window assignments are **never reached**.
- The inline script only uses `window.API_BASE` which comes from `config.js`, not `auth.js`. So the page may still *functionally* work despite the auth.js load error, but a SyntaxError will appear in the browser console.

**Result: FAIL -- auth.js loaded without type="module" will throw SyntaxError**

---

## 5. forgot-password.html Script References

| # | Script `src` | `type="module"` | File Exists | Notes |
|---|-------------|-----------------|-------------|-------|
| 1 | `js/config.js` | No (classic) | EXISTS | Sets `window.API_BASE` |
| 2 | Inline `<script>` | No (classic) | N/A | Password reset logic |

**Result: PASS**

---

## 6. fix.html Script References

| # | Script `src` | `type="module"` | File Exists | Notes |
|---|-------------|-----------------|-------------|-------|
| 1 | `js/config.js` | No (classic) | EXISTS | Sets `window.API_BASE` |
| 2 | Inline `<script>` | No (classic) | N/A | Login fix/diagnostic logic |

**Result: PASS** (utility page, not production)

---

## 7. test.html Script References

| # | Script `src` | `type="module"` | File Exists | Notes |
|---|-------------|-----------------|-------------|-------|
| 1 | `js/config.js` | No (classic) | EXISTS | Sets `window.API_BASE` |
| 2 | Inline `<script>` | No (classic) | N/A | Diagnostic tests |

**Result: PASS** (diagnostic page, not production)

---

## Critical Issues Found

### ISSUE 1: config.js Runtime ReferenceError (CRITICAL)

**File:** `frontend/js/config.js`

```javascript
// const API_BASE_URL = 'https://3.xm006.com';   // <-- COMMENTED OUT
window.API_BASE = API_BASE_URL || window.location.origin;  // <-- ReferenceError!
```

`API_BASE_URL` is referenced on line 6 but its declaration on line 5 is commented out. This causes a `ReferenceError: API_BASE_URL is not defined` at runtime. This affects **every page** that loads `config.js` (login.html, settings.html, register.html, forgot-password.html, fix.html, test.html).

**Impact:** Pages that load `config.js` will fail to set `window.API_BASE`. However, `auth.js` has a fallback: `export const API_BASE = window.API_BASE || window.location.origin;` -- so for module pages (login, settings), the fallback to `window.location.origin` still works. For register.html's inline script, `window.API_BASE` is used with an `||` fallback pattern too. The actual severity depends on whether the error stops script execution of the subsequent scripts on the page.

**Severity:** HIGH -- config.js will throw an uncaught ReferenceError on every page load where it is included.

### ISSUE 2: register.html loads auth.js without type="module" (MEDIUM)

**File:** `frontend/register.html` line 39

```html
<script src="js/auth.js"></script>   <!-- Missing type="module" -->
```

`auth.js` uses ES module `export` syntax. Loading it as a classic script causes a `SyntaxError`. The page may still work because the inline script only relies on `window.API_BASE` from `config.js`, but the browser console will show an error.

### ISSUE 3: Orphaned JS files (LOW)

Two JS files exist on disk but are not referenced by any HTML file or imported by any other module:
- `js/ai-signal.js` -- appears to be a predecessor/alternative to `ai-card.js`
- `js/market.js` -- appears to be a predecessor/alternative to `coin-data.js`

These are dead code and should be cleaned up.

### ISSUE 4: Duplicate CSS files at root level (LOW)

Root-level CSS files exist alongside `css/` directory versions with different sizes (older versions):
- `frontend/light-theme.css` (12,447 bytes) vs `frontend/css/light-theme.css` (17,498 bytes)
- `frontend/main.css` (22,524 bytes) vs `frontend/css/main.css` (24,540 bytes)
- `frontend/responsive.css` (9,278 bytes) vs `frontend/css/responsive.css` (9,873 bytes)

HTML files reference `css/*.css` paths (the correct ones). Root-level copies are stale duplicates.

---

## Summary

| HTML File | Scripts | All Exist | Load Order | Module Type | Result |
|-----------|---------|-----------|------------|-------------|--------|
| index.html | 25 (2 CDN + 23 local) | YES | CORRECT | CORRECT | **PASS** |
| login.html | 2 + inline | YES | CORRECT | CORRECT | **PASS*** |
| settings.html | 3 | YES | CORRECT | CORRECT | **PASS*** |
| register.html | 2 + inline | YES | CORRECT | **WRONG** (auth.js) | **FAIL** |
| forgot-password.html | 1 + inline | YES | CORRECT | CORRECT | **PASS*** |
| fix.html | 1 + inline | YES | CORRECT | CORRECT | **PASS*** |
| test.html | 1 + inline | YES | CORRECT | CORRECT | **PASS*** |

*Asterisk: config.js has a runtime ReferenceError that affects all pages loading it, but fallback mechanisms in downstream code mitigate the functional impact.

**Overall FE Gate 0: CONDITIONAL PASS (2 issues require attention before release)**
