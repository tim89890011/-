#!/usr/bin/env bash
# scripts/ci.sh — 一键 CI 流水线（lint + test + security check）
# 用法: bash scripts/ci.sh
# 退出码: 非0 表示任一步骤失败
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

step=0
fail=0

run_step() {
    step=$((step + 1))
    local desc="$1"; shift
    echo ""
    echo -e "${YELLOW}=== Step $step: $desc ===${NC}"
    if "$@"; then
        echo -e "${GREEN}✓ $desc${NC}"
    else
        echo -e "${RED}✗ $desc${NC}"
        fail=$((fail + 1))
    fi
}

# 确保目录存在
mkdir -p data logs

# 如果没有 .env 且有 .env.example，创建最小测试 .env
if [ ! -f .env ]; then
    echo "创建最小 .env 用于测试..."
    cat > .env << 'ENVEOF'
DEEPSEEK_API_KEY=test-key-ci
QWEN_API_KEY=test-key-ci
JWT_SECRET=ci-test-secret-not-for-production
ALLOW_DEFAULT_JWT_SECRET=true
ALLOW_WEAK_ADMIN_PASSWORD=true
DATABASE_URL=sqlite+aiosqlite:///./data/test.db
TRADE_ENABLED=false
BINANCE_TESTNET_API_KEY=
BINANCE_TESTNET_API_SECRET=
ENVEOF
fi

# Step 1: Ruff lint
if command -v ruff &>/dev/null; then
    run_step "Ruff lint (fatal errors)" ruff check backend/ --select E9,F63,F7,F82 --ignore E501
else
    echo -e "${YELLOW}⚠ ruff 未安装，跳过 lint${NC}"
fi

# Step 2: Pytest
if command -v pytest &>/dev/null; then
    run_step "Pytest" python3 -m pytest tests/ -v --tb=short -q
elif python3 -c "import pytest" 2>/dev/null; then
    run_step "Pytest (module)" python3 -m pytest tests/ -v --tb=short -q
else
    echo -e "${YELLOW}⚠ pytest 未安装，跳过测试${NC}"
fi

# Step 3: Security — hardcoded secrets
run_step "Security: no hardcoded API keys" bash -c '
    if grep -rn "sk-[a-zA-Z0-9]\{20,\}" backend/ --include="*.py" 2>/dev/null; then
        echo "发现硬编码 API key！"
        exit 1
    fi
    echo "未发现硬编码密钥"
'

# Step 4: Security — no mainnet URLs in trading
run_step "Security: testnet only" bash -c '
    if grep -rn "fstream\.binance\.com\|fapi\.binance\.com" backend/trading/ --include="*.py" 2>/dev/null | grep -v testnet | grep -v "#" | grep -v "^$"; then
        echo "发现主网 URL！"
        exit 1
    fi
    echo "所有交易 URL 指向测试网"
'

# Summary
echo ""
echo "========================================"
if [ "$fail" -eq 0 ]; then
    echo -e "${GREEN}CI 通过: $step 步全部成功${NC}"
    exit 0
else
    echo -e "${RED}CI 失败: $fail/$step 步失败${NC}"
    exit 1
fi
