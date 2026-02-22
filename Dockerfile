# 钢子出击 - Docker 镜像
# 多阶段构建：减小最终镜像体积

FROM python:3.13-slim AS base

# 系统依赖（SQLite + 编译工具）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先复制依赖文件，利用 Docker 缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY backend/ backend/
COPY frontend/ frontend/
COPY alembic/ alembic/
COPY alembic.ini .

# 创建数据和日志目录
RUN mkdir -p data logs

# 非 root 用户运行
RUN useradd -m -s /bin/bash gangzi && chown -R gangzi:gangzi /app
USER gangzi

EXPOSE 9998

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9998/')" || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "9998", "--timeout-graceful-shutdown", "30"]
