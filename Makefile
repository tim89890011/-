# 钢子出击 - 开发 Makefile
.PHONY: setup lint test ci run-backend run-frontend clean

# 安装开发依赖
setup:
	pip install -r requirements.txt
	pip install pytest pytest-asyncio ruff
	mkdir -p data logs
	@echo "✓ 依赖安装完成"

# Ruff lint — fatal errors only (CI gate)
lint:
	ruff check backend/ --select E9,F63,F7,F82 --ignore E501

# Ruff lint — full check (advisory, not CI-blocking)
lint-full:
	ruff check backend/ --select E,W,F --ignore E501,W293,W291

# 自动修复 lint 问题（安全修复）
lint-fix:
	ruff check backend/ --select E,W,F --ignore E501 --fix

# 运行测试
test:
	python3 -m pytest tests/ -v --tb=short

# 完整 CI 流水线
ci:
	bash scripts/ci.sh

# 启动后端
run-backend:
	python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 用默认浏览器打开前端（由后端 StaticFiles 提供）
run-frontend:
	@echo "前端由后端 StaticFiles 提供，访问 http://localhost:8000"
	@echo "如需独立开发，可用: python3 -m http.server 3000 -d frontend/"

# 清理缓存
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ 缓存清理完成"
