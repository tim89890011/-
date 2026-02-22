#!/bin/bash
# 钢子出击 - 一键检查脚本
# 用法: bash scripts/verify_all.sh

cd "$(dirname "$0")/.."
PASS=0
FAIL=0
WARN=0

green() { echo -e "\033[32m✅ $1\033[0m"; PASS=$((PASS+1)); }
red()   { echo -e "\033[31m❌ $1\033[0m"; FAIL=$((FAIL+1)); }
yellow(){ echo -e "\033[33m⚠️  $1\033[0m"; WARN=$((WARN+1)); }

echo "======================================"
echo "  钢子出击 - 全面体检"
echo "======================================"
echo ""

# ---- 1. 能不能正常启动 ----
echo "【1/7】检查代码有没有语法错误..."
ERR=$(./venv/bin/python -c "
import sys
files = [
    'backend/main.py',
    'backend/trading/executor.py',
    'backend/trading/pnl.py',
    'backend/ai_engine/debate.py',
    'backend/ai_engine/json_parser.py',
    'backend/risk/gate.py',
    'backend/scheduler/tasks.py',
    'backend/scheduler/lock.py',
    'backend/trading/user_data_stream.py',
    'backend/market/binance_ws.py',
    'backend/ai_engine/deepseek_client.py',
    'backend/ai_engine/router.py',
]
ok = True
for f in files:
    try:
        compile(open(f).read(), f, 'exec')
    except SyntaxError as e:
        print(f'语法错误: {f} 第{e.lineno}行: {e.msg}')
        ok = False
if ok:
    print('ALL_OK')
" 2>&1)

if echo "$ERR" | grep -q "ALL_OK"; then
    green "12 个核心文件语法检查通过"
else
    red "语法错误: $ERR"
fi

# ---- 2. 跑测试 ----
echo ""
echo "【2/7】跑自动化测试..."
TEST_OUT=$(./venv/bin/python -m pytest tests/ -v --tb=short 2>&1)
TEST_PASS=$(echo "$TEST_OUT" | grep -c "PASSED")
TEST_FAIL=$(echo "$TEST_OUT" | grep -c "FAILED")

if [ "$TEST_FAIL" -eq 0 ] && [ "$TEST_PASS" -gt 0 ]; then
    green "$TEST_PASS 个测试全部通过"
else
    red "$TEST_FAIL 个测试失败（$TEST_PASS 个通过）"
    echo "$TEST_OUT" | grep "FAILED"
fi

# ---- 3. import 检查（模块能不能正常加载）----
echo ""
echo "【3/7】检查模块能不能正常加载..."
IMP_ERR=$(./venv/bin/python -c "
try:
    from backend.trading.pnl import calc_pnl_pct, pair_trades
    from backend.ai_engine.json_parser import parse_json_from_text, extract_json_from_reasoning
    from backend.scheduler.lock import acquire_lock, release_lock
    print('ALL_OK')
except Exception as e:
    print(f'导入失败: {e}')
" 2>&1)

if echo "$IMP_ERR" | grep -q "ALL_OK"; then
    green "3 个新模块（PNL / JSON解析 / 调度锁）导入正常"
else
    red "模块导入失败: $IMP_ERR"
fi

# ---- 4. 主网 URL 泄漏检查 ----
echo ""
echo "【4/7】检查交易代码有没有连到真实交易所..."
LEAK=$(grep -rn "fstream\.binance\.com\|stream\.binancefuture\.com" backend/trading/ backend/market/ --include="*.py" | grep -v testnet | grep -v "\.replace\|\.com.*in" | grep -v "#" || true)

if [ -z "$LEAK" ]; then
    green "所有交易连接都指向测试网（不会动真钱）"
else
    red "发现可能连接真实交易所的代码:"
    echo "$LEAK"
fi

# ---- 5. 安全检查 ----
echo ""
echo "【5/7】检查有没有密码/密钥写死在代码里..."
SECRET=$(grep -rn "sk-[a-zA-Z0-9]\{20,\}\|password.*=.*['\"].*['\"]" backend/ --include="*.py" | grep -v "password_hash\|password_reset\|ADMIN_PASSWORD\|__pycache__\|\.pyc\|test_\|example\|comment\|description\|help\|Field(" || true)

if [ -z "$SECRET" ]; then
    green "没有发现硬编码的密码或密钥"
else
    yellow "可能有硬编码密钥（请人工确认）:"
    echo "$SECRET" | head -5
fi

# ---- 6. 静默异常检查 ----
echo ""
echo "【6/7】检查有没有出错了偷偷不说的代码..."
SILENT=$(grep -A1 "except.*Exception" backend/trading/executor.py backend/risk/gate.py | grep "pass$" || true)

if [ -z "$SILENT" ]; then
    green "交易和风控模块没有静默吞掉异常的代码"
else
    red "发现静默异常（出了问题你看不到）:"
    echo "$SILENT"
fi

# ---- 7. 关键文件存在性 ----
echo ""
echo "【7/7】检查关键文件是否齐全..."
ALL_EXIST=true
for f in \
    backend/trading/pnl.py \
    backend/ai_engine/json_parser.py \
    backend/scheduler/lock.py \
    tests/test_pnl.py \
    tests/test_json_parser.py \
    .github/workflows/ci.yml \
    Dockerfile \
    docker-compose.yml \
    .dockerignore; do
    if [ ! -f "$f" ]; then
        red "文件缺失: $f"
        ALL_EXIST=false
    fi
done

if $ALL_EXIST; then
    green "9 个新文件全部存在"
fi

# ---- 总结 ----
echo ""
echo "======================================"
TOTAL=$((PASS + FAIL + WARN))
if [ "$FAIL" -eq 0 ]; then
    echo -e "\033[32m  体检结果: $PASS/$TOTAL 项通过，0 项失败\033[0m"
    if [ "$WARN" -gt 0 ]; then
        echo -e "\033[33m  有 $WARN 项警告，建议人工确认\033[0m"
    fi
    echo -e "\033[32m  系统状态: 健康\033[0m"
else
    echo -e "\033[31m  体检结果: $FAIL 项失败！请检查上面红色的项目\033[0m"
fi
echo "======================================"
