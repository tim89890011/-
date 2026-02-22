# Backend Smoke Test Report

**Project:** 钢子出击 - 量化交易信号系统
**Date:** 2026-02-23
**Tester:** Backend Engineer (automated)
**Overall Result:** **PASS**

---

## 1. Startup Attempt Result

| Item | Result |
|------|--------|
| Server startup | PASS - Full startup in ~6 seconds |
| Database init | PASS - SQLite WAL mode, tables confirmed |
| Binance testnet connection | PASS - Connected, balance fetched |
| WebSocket connections | PASS - Market data + User data streams connected |
| Scheduler | PASS - 8 scheduled tasks registered |
| Uvicorn listening | PASS - Accepting HTTP on port 8899 |

**Startup log summary:**
The application completes its full lifecycle startup including database initialization, quota restoration from DB, admin account verification, Binance Futures testnet connection (10 trading pairs configured at 5x leverage), WebSocket streams (market data + mark price + user data), price trigger injection, and scheduler with 8 recurring tasks.

**Non-fatal warnings during startup:**
- 10x margin mode set failures ("可能已是 isolated") -- expected when open orders exist on testnet
- 1x dual position mode set failure -- expected when already in that mode

These are benign warnings and do not affect functionality.

---

## 2. Health Endpoint Results

| Endpoint | Auth Required | HTTP Status | Response | Verdict |
|----------|:------------:|:-----------:|----------|:-------:|
| `GET /api/health/live` | No | 200 | `{"status":"alive"}` | PASS |
| `GET /api/health/ready` | No | 200 | `{"status":"ready"}` | PASS |
| `GET /api/health` | Yes | 401 | Correctly rejects | PASS |
| `GET /api/health/db` | Yes | 401 | Correctly rejects | PASS |
| `GET /api/health/ws` | Yes | 401 | Correctly rejects | PASS |
| `GET /api/health/ai` | Yes | 401 | Correctly rejects | PASS |
| `GET /api/health/detailed` | Yes | 401 | Correctly rejects | PASS |

The liveness probe (`/api/health/live`) and readiness probe (`/api/health/ready`) both respond correctly without authentication, suitable for Kubernetes or load balancer health checks.

---

## 3. API Endpoint Results

### Unauthenticated Endpoints (all PASS)

| Endpoint | HTTP Status | Response Summary |
|----------|:-----------:|-----------------|
| `GET /api/settings/presets` | 200 | Full JSON with "steady" + "aggressive" presets |
| `GET /api/auth/register-status` | 200 | `{"enabled":false}` |
| `GET /api/auth/captcha` | 200 | Captcha ID + math question |
| `GET /docs` | 200 | OpenAPI Swagger UI |

### Authenticated Endpoints (correctly reject without token)

| Endpoint | HTTP Status | Response |
|----------|:-----------:|---------|
| `GET /api/market/prices` | 401 | `"未提供认证凭据，请先登录"` |
| `GET /api/metrics/summary` | 401 | `"未提供认证凭据，请先登录"` |

### Login Flow

Login attempt with default credentials (`admin/admin123`) returned 401. This is expected because:
1. The admin username has been customized in the deployed `.env` (current admin is `'a'`)
2. The login endpoint likely requires `captcha_id` + `captcha_answer` fields

Authentication middleware is functioning correctly: all protected endpoints return structured 401 responses with `request_id` for traceability.

### Route Inventory

**Total routes:** 80
**Endpoint groups:** 11 (auth, market, ai, chat, trade, settings, analytics, reports, health, metrics, websocket)

---

## 4. Import Validation Result

| Check | Result |
|-------|--------|
| `from backend.main import app` | PASS |
| App title | `钢子出击 - 量化交易系统` |
| Routes registered | 80 |
| All import chains valid | Yes (no ImportError) |

The FastAPI application object can be imported cleanly. All module-level imports in `backend/main.py` resolve successfully, including:
- All 11 routers (auth, market, ai, chat, trade, settings, analytics, reports, health, metrics, websocket)
- Middleware (RequestContext, ErrorHandler, CORS)
- Exception handlers (Business, Validation, HTTP, Global)
- Background services (Binance WS, user data stream, scheduler, price trigger)
- Trading executor and signal engine

---

## 5. PASS/FAIL Determination

### Overall: **PASS**

| Gate | Status | Notes |
|------|:------:|-------|
| Import validation | PASS | All 80 routes register without error |
| Server startup | PASS | Full lifecycle startup completes (~6s) |
| Liveness probe | PASS | `GET /api/health/live` returns 200 |
| Readiness probe | PASS | `GET /api/health/ready` returns 200 |
| Public endpoints | PASS | 4/4 unauthenticated endpoints respond correctly |
| Auth enforcement | PASS | Protected endpoints correctly return 401 |
| Structured errors | PASS | Error responses include `success`, `code`, `message`, `request_id` |
| External connectivity | PASS | Binance testnet API + WebSocket connected |

---

## 6. Known Blockers / Notes

### Not Blockers (informational)

1. **Port 8000 occupied** -- Another process was using port 8000 during testing. Used port 8899 instead. The `.env` configures `PORT=9998` for production.

2. **Customized admin credentials** -- The deployed `.env` uses username `'a'` instead of the default `'admin'`. Login requires captcha (math challenge). This prevented testing authenticated endpoints via curl but is not a bug.

3. **Margin mode warnings** -- 10 symbols report "Position side cannot be changed if there exists open orders" during startup. This is a known Binance API behavior when open orders exist on testnet and does not affect functionality.

4. **Login requires captcha** -- The `/api/auth/login` endpoint requires `captcha_id` and `captcha_answer` fields. This is a security feature, not a blocker.

### External Dependencies

| Dependency | Status | Impact if Unavailable |
|------------|--------|----------------------|
| Binance Futures Testnet API | Connected | Trading features degraded |
| Binance WebSocket | Connected | Real-time prices unavailable |
| DeepSeek API | Key configured | AI analysis unavailable |
| Qwen/DashScope API | Key configured | AI chat/role analysis unavailable |
| Telegram Bot | Optional | Notifications disabled |

### Production Readiness Checklist

- [x] Application starts and binds to port
- [x] Database initializes with WAL mode
- [x] Health probes respond (for k8s/load balancer)
- [x] Authentication middleware enforces JWT on protected routes
- [x] Error responses are structured and include request IDs
- [x] CORS configured with allowlist
- [x] Scheduler registers all recurring tasks
- [x] Trading module connects to Binance testnet
- [x] WebSocket streams establish connections
- [ ] Authenticated endpoint round-trip not tested (requires captcha + custom credentials)

---

## Raw Logs

Full raw test output saved to: `artifacts/backend_smoke.log`
