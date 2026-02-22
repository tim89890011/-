# Release Readiness Verification Plan

**Project:** 钢子出击 (gangzi-trading) - AI-Driven Crypto Trading Signal System
**Git HEAD:** 689d663
**Git Status:** Clean
**Date:** 2026-02-23
**Plan Author:** TL (Tech Lead)

---

## 1. Project Overview

| Attribute | Value |
|-----------|-------|
| Backend | FastAPI + SQLAlchemy (async) + aiosqlite, Python 3.13 |
| Frontend | Static HTML/JS/CSS served by FastAPI StaticFiles (no build toolchain) |
| Database | SQLite (via aiosqlite), Alembic migrations |
| External APIs | Binance Testnet (ccxt), DeepSeek AI, Qwen AI |
| CI | `scripts/ci.sh` (ruff + pytest + security grep), `.github/workflows/ci.yml` |
| Container | Dockerfile (python:3.13-slim) + docker-compose.yml, port 9998 |
| Tests | 8 pytest modules in `tests/`, async mode, conftest with fixtures |
| E2E | Not present (no Playwright, no e2e directory) |

---

## 2. Team Roles and Responsibilities

| # | Role | Agent | Scope |
|---|------|-------|-------|
| 1 | **TL** | Coordinator | Write this plan, aggregate results, issue final GO/NO-GO |
| 2 | **SDET** | Quality | Gate 0 (CI pipeline), Gate 1 (static analysis + security), Gate 2 (pytest), Gate 2.5 (history regression) |
| 3 | **BE** | Backend | Gate 3 (backend smoke: import, startup, health endpoint, API routes) |
| 4 | **FE** | Frontend | FE Gate (HTML reference integrity, static asset validation, runtime sanity) |
| 5 | **Release** | Release Eng | Gate 4 (repo safety), final report compilation |

---

## 3. Execution Sequence

### Phase A: Independent Gates (PARALLEL)

The following four workstreams launch simultaneously. No dependencies between them.

```
Time ──────────────────────────────────────────────────────────►

  SDET:    [Gate 0: CI] → [Gate 1: Static+Security] → [Gate 2: Pytest] → [Gate 2.5: History]
  BE:      [Gate 3: Backend Smoke]
  FE:      [FE Gate: Frontend Checks]
  Release: [Gate 4: Repo Safety]
```

### Phase B: Report Compilation (SEQUENTIAL, after Phase A)

```
  Release: Collects all gate reports → Compiles final report
  TL:      Reviews final report → Issues GO/NO-GO
```

### Dependency Rules

1. Gates 0, 1, 2, 2.5 run sequentially within SDET (each depends on prior pass).
2. Gate 3 (BE), FE Gate (FE), Gate 4 (Release) are independent of each other and of SDET.
3. Phase B starts only after ALL Phase A workstreams complete.
4. TL GO/NO-GO is the last action. Any single gate failure triggers NO-GO.

---

## 4. Gate Definitions

### Gate 0: CI Pipeline Execution (SDET)

**What:** Run the existing CI script end-to-end.

**Commands:**
```bash
bash scripts/ci.sh
```

**Pass Criteria:**
- [ ] Exit code is 0
- [ ] All steps (ruff lint, pytest, hardcoded-secret scan, testnet-URL scan) print green checkmarks
- [ ] No skipped steps (ruff and pytest must both be installed and executed)

**Fail Criteria:**
- Exit code non-zero
- Any step prints a red cross or is skipped due to missing tool

**Deliverable:** `artifacts/gate0_ci.log` (full stdout/stderr capture)

---

### Gate 1: Static Analysis + Security Scan (SDET)

**What:** Deeper static analysis and security checks beyond the CI script.

**Commands:**
```bash
# 1a. Full ruff lint (advisory-level, captures all warnings)
ruff check backend/ --select E,W,F --ignore E501,W293,W291 --output-format json > artifacts/gate1_ruff_full.json 2>&1; echo "EXIT=$?"

# 1b. Fatal-only ruff (must pass)
ruff check backend/ --select E9,F63,F7,F82 --ignore E501

# 1c. Hardcoded secrets (broader pattern)
grep -rn "sk-[a-zA-Z0-9]\{20,\}\|AKIA[A-Z0-9]\{16\}\|ghp_[a-zA-Z0-9]\{36\}" backend/ --include="*.py"

# 1d. Mainnet URL leak (trading + market modules)
grep -rn "fstream\.binance\.com\|fapi\.binance\.com\|stream\.binancefuture\.com" backend/trading/ backend/market/ --include="*.py" | grep -v testnet | grep -v "#"

# 1e. Silent exception audit
grep -rn "except.*:$" backend/ --include="*.py" -A1 | grep "pass$"

# 1f. Secrets directory contents
ls -la secrets/

# 1g. .env existence check (must NOT be committed)
git ls-files -- '.env'
```

**Pass Criteria:**
- [ ] 1b (fatal ruff) exits 0
- [ ] 1c returns no matches
- [ ] 1d returns no matches
- [ ] 1e returns zero silent exception swallows in `backend/trading/executor.py` and `backend/risk/gate.py`
- [ ] 1f shows only expected files (no actual API keys with real values)
- [ ] 1g returns empty (no .env in git)

**Acceptable Warnings (non-blocking):**
- 1a may produce E/W warnings -- these are advisory. Count and record but do not block.

**Fail Criteria:**
- Any of 1b through 1g fails

**Deliverable:** `artifacts/gate1_static_security.log`

---

### Gate 2: Pytest Full Suite (SDET)

**What:** Run all test modules with verbose output and failure details.

**Commands:**
```bash
python3 -m pytest tests/ -v --tb=long 2>&1 | tee artifacts/gate2_pytest.log
```

**Test modules expected (8 files):**
1. `tests/test_callback_wiring.py`
2. `tests/test_executor_core.py`
3. `tests/test_json_parser.py`
4. `tests/test_pnl.py`
5. `tests/test_regime.py`
6. `tests/test_signal_schema.py`
7. `tests/test_symbol.py`
8. `tests/test_websocket.py`

**Pass Criteria:**
- [ ] Exit code is 0
- [ ] 0 FAILED, 0 ERROR
- [ ] All 8 test files are collected and executed (no collection errors)
- [ ] Total test count > 0 (no empty suite)

**Fail Criteria:**
- Any test FAILED or ERROR
- Any test file fails to collect
- Exit code non-zero

**Deliverable:** `artifacts/gate2_pytest.log`

---

### Gate 2.5: History Regression Check (SDET)

**What:** Verify no known-bad patterns were reintroduced.

**Commands:**
```bash
# 2.5a. Verify SignalOutput Pydantic model exists (P1 acceptance)
grep -rn "class SignalOutput" backend/ai_engine/ --include="*.py"

# 2.5b. Verify json_parser uses schema validation, not raw dict return
grep -n "SignalOutput\|model_validate\|parse_obj" backend/ai_engine/json_parser.py

# 2.5c. Verify scheduler lock module exists and is importable
python3 -c "from backend.scheduler.lock import acquire_lock, release_lock; print('OK')"

# 2.5d. Verify PNL module exports
python3 -c "from backend.trading.pnl import calc_pnl_pct, pair_trades; print('OK')"

# 2.5e. Verify no bare 'except:' (without Exception type) in critical paths
grep -rn "except:" backend/trading/ backend/risk/ --include="*.py"
```

**Pass Criteria:**
- [ ] 2.5a returns at least 1 match
- [ ] 2.5b returns at least 1 match
- [ ] 2.5c prints "OK"
- [ ] 2.5d prints "OK"
- [ ] 2.5e returns no matches (no bare except in trading/risk)

**Fail Criteria:**
- Any check fails

**Deliverable:** `artifacts/gate2_5_regression.log`

---

### Gate 3: Backend Smoke Test (BE)

**What:** Verify the backend application can start, serve health checks, and respond on API routes.

**Commands:**
```bash
# 3a. Syntax check on all core backend files
python3 -c "
import sys, pathlib
root = pathlib.Path('backend')
errors = []
for f in sorted(root.rglob('*.py')):
    try:
        compile(f.read_text(), str(f), 'exec')
    except SyntaxError as e:
        errors.append(f'{f}:{e.lineno}: {e.msg}')
if errors:
    print('\n'.join(errors))
    sys.exit(1)
print(f'OK: {len(list(root.rglob(\"*.py\")))} files checked')
"

# 3b. Import smoke test (all routers)
python3 -c "
from backend.auth.router import router as r1
from backend.market.router import router as r2
from backend.ai_engine.router import router as r3
from backend.chat.router import router as r4
from backend.trading.router import router as r5
from backend.settings.router import router as r6
from backend.analytics.router import router as r7
from backend.monitoring.health import router as r8
from backend.monitoring.metrics_exporter import router as r9
from backend.websocket.routes import router as r10
from backend.reports.router import router as r11
print(f'OK: 11 routers imported')
"

# 3c. App object creation (does NOT trigger lifespan)
python3 -c "
from backend.main import app
routes = [r.path for r in app.routes if hasattr(r, 'path')]
print(f'OK: {len(routes)} routes registered')
for r in sorted(routes):
    print(f'  {r}')
"

# 3d. Start server and hit health endpoint (timeout 15s)
timeout 15 bash -c '
    uvicorn backend.main:app --host 127.0.0.1 --port 19998 &
    PID=$!
    sleep 8
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:19998/ 2>/dev/null || echo "000")
    echo "Root endpoint status: $STATUS"
    kill $PID 2>/dev/null
    wait $PID 2>/dev/null
    if [ "$STATUS" = "200" ]; then echo "PASS"; else echo "FAIL: status=$STATUS"; fi
'
```

**Pass Criteria:**
- [ ] 3a: 0 syntax errors across all `.py` files in `backend/`
- [ ] 3b: All 11 routers import without error
- [ ] 3c: App object creates, lists registered routes
- [ ] 3d: Server starts and root endpoint returns HTTP 200 (or startup completes without crash even if external services are unavailable)

**Acceptable Degradations (non-blocking):**
- 3d may fail due to missing `.env` or unavailable external services (Binance, AI APIs). If the server starts but health sub-checks show degraded external services, this is acceptable. A Python crash or import error is NOT acceptable.

**Fail Criteria:**
- Syntax error in any backend file
- Import error on any router module
- App object fails to create
- Server crashes on startup with ImportError/SyntaxError/TypeError

**Deliverable:** `artifacts/gate3_backend_smoke.log`

---

### FE Gate: Frontend Integrity (FE)

**What:** Verify frontend static files are complete, internally consistent, and free of broken references.

**Commands:**
```bash
# FE-a. All HTML files exist and are non-empty
for f in frontend/index.html frontend/login.html frontend/settings.html frontend/register.html frontend/forgot-password.html; do
    if [ ! -s "$f" ]; then echo "FAIL: $f missing or empty"; fi
done

# FE-b. All JS files referenced in HTML exist on disk
grep -roh 'src="js/[^"]*"' frontend/*.html | sed 's/src="//;s/"//' | sort -u | while read js; do
    if [ ! -f "frontend/$js" ]; then echo "FAIL: frontend/$js missing"; fi
done

# FE-c. All CSS files referenced in HTML exist on disk
grep -roh 'href="css/[^"]*"' frontend/*.html | sed 's/href="//;s/"//' | sort -u | while read css; do
    if [ ! -f "frontend/$css" ]; then echo "FAIL: frontend/$css missing"; fi
done

# FE-d. JS files have no syntax errors (Node.js check)
for f in frontend/js/*.js; do
    node --check "$f" 2>&1 || echo "SYNTAX_ERROR: $f"
done
for f in frontend/js/trading/*.js; do
    node --check "$f" 2>&1 || echo "SYNTAX_ERROR: $f"
done

# FE-e. API endpoint consistency: extract frontend API calls and list them
grep -roh "fetch(['\"][^'\"]*['\"]" frontend/js/ | sed "s/fetch(['\"]//;s/['\"]$//" | sort -u

# FE-f. No hardcoded API keys or secrets in JS
grep -rn "sk-\|api_key.*=.*['\"]" frontend/js/ --include="*.js" | grep -v "apiKey\|API_KEY\|config\|localStorage\|getItem"

# FE-g. Large binary audit (no files > 1MB that should not be there)
find frontend/ -type f -size +1M ! -name "*.tar.gz" -exec ls -lh {} \;
```

**Pass Criteria:**
- [ ] FE-a: All 5 HTML files exist and are non-empty
- [ ] FE-b: Every JS `src=` reference resolves to an existing file
- [ ] FE-c: Every CSS `href=` reference resolves to an existing file
- [ ] FE-d: All JS files pass `node --check` with no syntax errors
- [ ] FE-f: No hardcoded secrets found in JS files

**Acceptable Warnings (non-blocking):**
- FE-e: API endpoint list is informational -- record for cross-reference with Gate 3 route list
- FE-g: `frontend/钢子出击_20260220.tar.gz` (148MB) is known; flag for Release team to assess if it should be in the repo

**Fail Criteria:**
- Missing/empty HTML file
- Broken JS or CSS reference from HTML
- JS syntax error
- Hardcoded secrets in JS

**Deliverable:** `artifacts/fe_gate_frontend.log`

---

### E2E Gate: Playwright (FE)

**Status: SKIPPED**

No Playwright installation, no `e2e/` directory, no E2E configuration detected. This gate is not executable for this release.

**Action Item:** Record as a known gap. Recommend adding E2E tests in a future sprint.

**Deliverable:** Note in final report: "E2E Gate SKIPPED -- no Playwright infrastructure."

---

### Gate 4: Repository Safety (Release)

**What:** Verify the repository is clean, no secrets are tracked, ignore files are correct, and deployment artifacts are valid.

**Commands:**
```bash
# 4a. Git status is clean
git status --porcelain

# 4b. No secrets tracked in git
git ls-files -- '.env' '.env.*' 'secrets/' | grep -v '.gitignore'

# 4c. .gitignore covers critical exclusions
for pattern in ".env" "data/" "venv/" "__pycache__/" "*.bak.*" "secrets/*" "backups/" "logs/*.log"; do
    if ! grep -qF "$pattern" .gitignore; then echo "MISSING: $pattern"; fi
done

# 4d. .dockerignore exists and covers essentials
for pattern in ".env" "data/" "venv/" "tests/"; do
    if ! grep -qF "$pattern" .dockerignore; then echo "MISSING: $pattern"; fi
done

# 4e. Dockerfile builds (syntax validation only, no actual build)
python3 -c "
lines = open('Dockerfile').readlines()
instructions = [l.split()[0] for l in lines if l.strip() and not l.strip().startswith('#')]
required = {'FROM', 'WORKDIR', 'COPY', 'RUN', 'EXPOSE', 'CMD'}
found = set(instructions)
missing = required - found
if missing:
    print(f'FAIL: Missing Dockerfile instructions: {missing}')
else:
    print(f'OK: All required instructions present ({len(instructions)} total)')
"

# 4f. docker-compose.yml syntax check
python3 -c "
import yaml  # pyyaml may not be available; fallback below
" 2>/dev/null && python3 -c "
import yaml
with open('docker-compose.yml') as f:
    data = yaml.safe_load(f)
print(f'OK: {len(data.get(\"services\", {}))} service(s) defined')
" || python3 -c "
# Fallback: basic YAML structure check
content = open('docker-compose.yml').read()
if 'services:' in content and 'app:' in content:
    print('OK: docker-compose.yml has services.app (basic check)')
else:
    print('FAIL: docker-compose.yml missing expected structure')
"

# 4g. No large tracked files (>10MB)
git ls-files -z | xargs -0 -I{} sh -c 'sz=$(wc -c < "{}"); if [ "$sz" -gt 10485760 ]; then echo "LARGE: {} ($(echo "$sz/1048576" | bc)MB)"; fi'

# 4h. Alembic migration directory exists and has versions
ls alembic/versions/*.py 2>/dev/null | wc -l

# 4i. requirements.txt matches pyproject.toml (spot check top 5 deps)
for dep in fastapi uvicorn sqlalchemy httpx pydantic; do
    if ! grep -qi "$dep" requirements.txt; then echo "MISSING in requirements.txt: $dep"; fi
done

# 4j. CI workflow file exists and references correct Python versions
grep "python-version" .github/workflows/ci.yml
```

**Pass Criteria:**
- [ ] 4a: Empty output (clean working tree)
- [ ] 4b: No secret files tracked
- [ ] 4c: All critical patterns present in `.gitignore`
- [ ] 4d: `.dockerignore` covers essentials
- [ ] 4e: Dockerfile has all required instructions
- [ ] 4f: docker-compose.yml is valid
- [ ] 4g: No files >10MB tracked in git
- [ ] 4h: At least 1 Alembic migration version exists
- [ ] 4i: Top 5 dependencies present in `requirements.txt`
- [ ] 4j: CI workflow references Python 3.12 and 3.13

**Fail Criteria:**
- Dirty working tree (unexpected uncommitted changes)
- Secrets tracked in git
- Missing critical `.gitignore` entries
- Invalid Dockerfile or docker-compose.yml
- Large binary files tracked in git

**Deliverable:** `artifacts/gate4_repo_safety.log`

---

## 5. NO-GO Triggers

Any of the following conditions triggers an immediate **NO-GO** decision:

| # | Condition | Severity |
|---|-----------|----------|
| N1 | Gate 0 CI script exits non-zero | CRITICAL |
| N2 | Gate 1 fatal ruff errors (E9/F63/F7/F82) | CRITICAL |
| N3 | Hardcoded secrets detected in backend Python files | CRITICAL |
| N4 | Mainnet trading URLs found in trading/market code | CRITICAL |
| N5 | Any pytest test FAILED or ERROR | CRITICAL |
| N6 | Backend cannot import all router modules | HIGH |
| N7 | Backend app object fails to create | HIGH |
| N8 | Frontend HTML/JS/CSS reference integrity broken | HIGH |
| N9 | JS syntax errors in frontend | HIGH |
| N10 | Secrets tracked in git (`.env`, API keys) | CRITICAL |
| N11 | SignalOutput schema or scheduler lock module missing (regression) | HIGH |

**Policy:** A single CRITICAL triggers NO-GO. Two or more HIGH triggers also trigger NO-GO. A single HIGH is a conditional GO with mandatory fix-before-deploy.

---

## 6. Expected Deliverables Per Role

### SDET Deliverables
| File | Content |
|------|---------|
| `artifacts/gate0_ci.log` | Full CI script output |
| `artifacts/gate1_static_security.log` | Ruff full report, security scan results |
| `artifacts/gate1_ruff_full.json` | Machine-readable ruff output |
| `artifacts/gate2_pytest.log` | Full pytest verbose output |
| `artifacts/gate2_5_regression.log` | History regression check results |

### BE Deliverables
| File | Content |
|------|---------|
| `artifacts/gate3_backend_smoke.log` | Syntax check, import check, route list, startup test |

### FE Deliverables
| File | Content |
|------|---------|
| `artifacts/fe_gate_frontend.log` | HTML/JS/CSS integrity, syntax check, API endpoint list |

### Release Deliverables
| File | Content |
|------|---------|
| `artifacts/gate4_repo_safety.log` | Repo cleanliness, Docker validation, dependency check |
| `artifacts/FINAL_REPORT.md` | Aggregated pass/fail for all gates, GO/NO-GO recommendation |

### TL Deliverables
| File | Content |
|------|---------|
| `artifacts/GO_NOGO_DECISION.md` | Final decision with rationale, any conditional requirements |

---

## 7. Gate Summary Matrix

| Gate | Owner | Blocking | Depends On |
|------|-------|----------|------------|
| Gate 0: CI Pipeline | SDET | YES | None |
| Gate 1: Static + Security | SDET | YES (fatal subset) | Gate 0 |
| Gate 2: Pytest | SDET | YES | Gate 1 |
| Gate 2.5: History Regression | SDET | YES | Gate 2 |
| Gate 3: Backend Smoke | BE | YES | None |
| FE Gate: Frontend Integrity | FE | YES | None |
| E2E Gate: Playwright | FE | SKIPPED | N/A |
| Gate 4: Repo Safety | Release | YES | None |
| Final Report | Release | N/A | All gates |
| GO/NO-GO | TL | N/A | Final report |

---

## 8. Known Gaps and Risks

| # | Item | Severity | Mitigation |
|---|------|----------|------------|
| R1 | No E2E tests (Playwright) | MEDIUM | Manual smoke test of login flow recommended before production deploy |
| R2 | 148MB tar.gz in `frontend/` | LOW | Not tracked by git (in `.gitignore`); verify with Gate 4g |
| R3 | Single commit history (history rebuilt) | INFO | Cannot do deep git bisect; acceptance based on current state |
| R4 | `secrets/qwen_api_key` file exists on disk | HIGH | Verify via Gate 4b that it is NOT tracked in git |
| R5 | No pre-commit hooks detected (`.pre-commit-config.yaml` may be missing) | LOW | CI script provides equivalent checks; recommend adding pre-commit in next sprint |
| R6 | `ALLOW_DEFAULT_JWT_SECRET=true` in CI env | INFO | Acceptable for test env only; production must set unique JWT_SECRET |

---

## 9. Execution Checklist

```
Phase A (parallel):
  [ ] SDET: Gate 0 started
  [ ] SDET: Gate 0 PASS/FAIL → artifacts/gate0_ci.log
  [ ] SDET: Gate 1 started
  [ ] SDET: Gate 1 PASS/FAIL → artifacts/gate1_static_security.log
  [ ] SDET: Gate 2 started
  [ ] SDET: Gate 2 PASS/FAIL → artifacts/gate2_pytest.log
  [ ] SDET: Gate 2.5 started
  [ ] SDET: Gate 2.5 PASS/FAIL → artifacts/gate2_5_regression.log
  [ ] BE:   Gate 3 started
  [ ] BE:   Gate 3 PASS/FAIL → artifacts/gate3_backend_smoke.log
  [ ] FE:   FE Gate started
  [ ] FE:   FE Gate PASS/FAIL → artifacts/fe_gate_frontend.log
  [ ] FE:   E2E Gate SKIPPED (recorded)
  [ ] Release: Gate 4 started
  [ ] Release: Gate 4 PASS/FAIL → artifacts/gate4_repo_safety.log

Phase B (sequential):
  [ ] Release: All gate logs collected
  [ ] Release: FINAL_REPORT.md written → artifacts/FINAL_REPORT.md
  [ ] TL: Final report reviewed
  [ ] TL: GO/NO-GO decision issued → artifacts/GO_NOGO_DECISION.md
```
