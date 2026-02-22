"""
钢子出击 - 健康检查端点
提供系统和各组件的健康状态检查
"""
# pyright: reportMissingImports=false

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from ..auth.jwt_utils import get_current_user
from ..database.db import async_session
from ..market.binance_ws import get_live_prices

logger = logging.getLogger(__name__)

router = APIRouter(tags=["健康检查"])

# 健康检查超时（秒）
HEALTH_CHECK_TIMEOUT = 5


async def _run_health_check() -> dict:
    """内部健康检查逻辑，供多个端点复用"""
    checks = {}
    overall_status = "healthy"
    started_at = time.time()

    # 检查数据库
    try:
        db_result = await asyncio.wait_for(
            _check_database(), timeout=HEALTH_CHECK_TIMEOUT
        )
        checks["database"] = db_result
        if db_result["status"] != "healthy":
            overall_status = "degraded"
    except asyncio.TimeoutError:
        checks["database"] = {"status": "unhealthy", "error": "检查超时"}
        overall_status = "unhealthy"
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}
        overall_status = "unhealthy"

    # 检查 AI 服务
    try:
        ai_result = await asyncio.wait_for(
            _check_ai_service(), timeout=HEALTH_CHECK_TIMEOUT
        )
        checks["ai_service"] = ai_result
        if ai_result["status"] != "healthy" and overall_status != "unhealthy":
            overall_status = "degraded"
    except asyncio.TimeoutError:
        checks["ai_service"] = {"status": "unhealthy", "error": "检查超时"}
        overall_status = "degraded"
    except Exception as e:
        checks["ai_service"] = {"status": "unhealthy", "error": str(e)}
        overall_status = "degraded"

    # 检查 Binance WebSocket
    try:
        ws_result = await asyncio.wait_for(
            _check_binance_ws(), timeout=HEALTH_CHECK_TIMEOUT
        )
        checks["binance_ws"] = ws_result
        if ws_result["status"] != "healthy" and overall_status != "unhealthy":
            overall_status = "degraded"
    except asyncio.TimeoutError:
        checks["binance_ws"] = {"status": "unhealthy", "error": "检查超时"}
        overall_status = "degraded"
    except Exception as e:
        checks["binance_ws"] = {"status": "unhealthy", "error": str(e)}
        overall_status = "degraded"

    try:
        quota_result = await asyncio.wait_for(
            _check_quota_service(), timeout=HEALTH_CHECK_TIMEOUT
        )
        checks["quota"] = quota_result
        if quota_result["status"] != "healthy" and overall_status != "unhealthy":
            overall_status = "degraded"
    except asyncio.TimeoutError:
        checks["quota"] = {"status": "unhealthy", "error": "检查超时"}
        overall_status = "degraded"
    except Exception as e:
        checks["quota"] = {"status": "unhealthy", "error": str(e)}
        overall_status = "degraded"

    return {
        "status": overall_status,
        "checks": checks,
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "response_time_ms": round((time.time() - started_at) * 1000, 2),
    }


@router.get("/api/health")
async def health_check(username: str = Depends(get_current_user)):
    """整体健康状态检查（需要认证）"""
    return await _run_health_check()


@router.get("/api/health/db")
async def health_db(username: str = Depends(get_current_user)):
    """数据库连接状态检查"""
    result = await _check_database()
    return {
        "status": result["status"],
        "details": result,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/api/health/ws")
async def health_ws(username: str = Depends(get_current_user)):
    """WebSocket 连接状态检查"""
    result = await _check_binance_ws()
    return {
        "status": result["status"],
        "details": result,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/api/health/ai")
async def health_ai(username: str = Depends(get_current_user)):
    """AI 服务状态检查"""
    result = await _check_ai_service()
    return {
        "status": result["status"],
        "details": result,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/api/health/detailed")
async def health_detailed(username: str = Depends(get_current_user)):
    """
    详细健康状态（需要认证）

    返回完整的系统和组件健康信息
    """
    basic = await _run_health_check()

    # 添加详细指标
    from .metrics import metrics_collector
    from ..utils.quota import quota_manager

    # 配额状态
    quota_snapshot = quota_manager.get_snapshot()

    return {
        **basic,
        "metrics": metrics_collector.get_all_stats(),
        "quota": quota_snapshot.to_dict(),
    }


async def _check_database() -> Dict[str, Any]:
    """检查数据库连接状态"""
    start_time = time.time()

    try:
        from ..config import settings, BASE_DIR

        db_url = settings.DATABASE_URL
        if db_url.startswith("sqlite+aiosqlite:///./"):
            db_path = db_url.replace("sqlite+aiosqlite:///./", "")
            db_path = f"{BASE_DIR}/{db_path}".replace("//", "/")
        else:
            db_path = db_url

        async with async_session() as session:
            # 执行简单查询
            result = await session.execute(text("SELECT 1"))
            result.scalar()

            # 检查表数量
            table_result = await session.execute(
                text("SELECT count(*) FROM sqlite_master WHERE type='table'")
            )
            table_count = table_result.scalar()

            latency_ms = (time.time() - start_time) * 1000

            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "tables": table_count,
                "db_path": db_path,
            }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "latency_ms": round((time.time() - start_time) * 1000, 2),
        }


async def _check_ai_service() -> Dict[str, Any]:
    """检查 AI 服务状态"""
    from ..config import settings
    from ..ai_engine.deepseek_client import deepseek_client

    # 检查 API Key 是否配置
    api_key = settings.DEEPSEEK_API_KEY
    if not api_key or api_key == "sk-xxx":
        return {
            "status": "unhealthy",
            "error": "DeepSeek API Key 未配置",
        }

    # 检查 API Key 格式
    if not api_key.startswith("sk-"):
        return {
            "status": "unhealthy",
            "error": "DeepSeek API Key 格式不正确",
        }

    # 检查 HTTP 客户端状态
    client = deepseek_client._client
    if client and client.is_closed:
        return {
            "status": "degraded",
            "warning": "HTTP 客户端已关闭，可能需要重启",
        }

    return {
        "status": "healthy",
        "api_key_configured": True,
        "base_url": settings.DEEPSEEK_BASE_URL,
    }


async def _check_binance_ws() -> Dict[str, Any]:
    """检查 Binance WebSocket 连接状态"""
    prices = get_live_prices()

    # 检查是否有价格数据
    if not prices:
        return {
            "status": "unhealthy",
            "error": "无实时价格数据，WebSocket 可能未连接",
            "symbols_tracked": 0,
        }

    # 检查数据新鲜度（假设价格在 60 秒内更新过）
    # 实际 price 数据中没有 timestamp，这里只检查数量
    expected_symbols = 10  # 预期监控的币种数量
    actual_symbols = len(prices)
    tracked_symbols = sorted(list(prices.keys()))[:10]

    if actual_symbols < expected_symbols / 2:
        return {
            "status": "degraded",
            "warning": f"价格数据不完整 ({actual_symbols}/{expected_symbols})",
            "symbols_tracked": actual_symbols,
            "tracked_symbols": tracked_symbols,
        }

    # 检查 BTC 和 ETH 价格（主要交易对）
    critical_symbols = ["BTCUSDT", "ETHUSDT"]
    missing_critical = [s for s in critical_symbols if s not in prices]

    if missing_critical:
        return {
            "status": "degraded",
            "warning": f"缺少关键币种数据: {', '.join(missing_critical)}",
            "symbols_tracked": actual_symbols,
            "tracked_symbols": tracked_symbols,
        }

    return {
        "status": "healthy",
        "symbols_tracked": actual_symbols,
        "critical_symbols_available": True,
        "tracked_symbols": tracked_symbols,
    }


async def _check_quota_service() -> Dict[str, Any]:
    from ..utils.quota import quota_manager

    snapshot = quota_manager.get_snapshot().to_dict()
    status = "healthy"
    if snapshot["status"] in ("warning", "critical", "exceeded"):
        status = "degraded"

    return {
        "status": status,
        "quota_status": snapshot["status"],
        "usage_percent": snapshot["usage_percent"],
        "remaining": snapshot["remaining"],
    }


@router.get("/api/health/live")
async def liveness_probe():
    """
    Kubernetes 存活探针

    简单检查应用是否还活着
    """
    return {"status": "alive", "timestamp": datetime.now().isoformat()}


@router.get("/api/health/ready")
async def readiness_probe():
    """
    Kubernetes 就绪探针

    检查应用是否准备好接收流量
    """
    try:
        # 检查数据库
        async with async_session() as session:
            await session.execute(text("SELECT 1"))

        # 检查价格数据
        prices = get_live_prices()
        if not prices:
            return {
                "status": "not_ready",
                "reason": "价格数据未就绪",
            }

        return {"status": "ready", "timestamp": datetime.now().isoformat()}

    except Exception as e:
        return {
            "status": "not_ready",
            "reason": str(e),
        }
