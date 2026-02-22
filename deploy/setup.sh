#!/bin/bash
# 钢子出击 - 一键部署脚本
# 使用方法: chmod +x setup.sh && ./setup.sh

set -e

echo "====================================="
echo "  钢子出击 - 一键部署"
echo "====================================="

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "[1/5] 检查 Python..."
if ! command -v python3 &> /dev/null; then
    echo "错误：未找到 Python3，请先安装"
    exit 1
fi
python3 --version

echo "[2/5] 创建虚拟环境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "虚拟环境已创建"
else
    echo "虚拟环境已存在"
fi

echo "[3/5] 安装依赖..."
source venv/bin/activate
pip install -r requirements.txt

echo "[4/5] 初始化..."
mkdir -p data logs
# 检查 .env
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "已创建 .env 文件，请编辑填写真实配置"
fi

echo "[5/5] 启动服务..."
echo ""
echo "====================================="
echo "  部署完成！"
echo "====================================="
echo ""
echo "启动命令："
echo "  cd $PROJECT_DIR"
echo "  source venv/bin/activate"
echo "  uvicorn backend.main:app --host 0.0.0.0 --port 9998 --timeout-graceful-shutdown 30"
echo ""
echo "后台启动（推荐）："
echo "  nohup uvicorn backend.main:app --host 0.0.0.0 --port 9998 --timeout-graceful-shutdown 30 > logs/server.log 2>&1 &"
echo ""
echo "访问地址: http://localhost:9998"
echo "默认账号: admin / admin123"
echo ""
echo "重要提醒："
echo "  1. 编辑 .env 文件填写 DEEPSEEK_API_KEY"
echo "  2. 修改默认管理员密码"
echo "  3. 生产环境请配置 Nginx 反向代理"
echo "  4. 生产环境请安装 deploy/logrotate.conf 进行日志轮转"
