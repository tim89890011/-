"""
钢子出击 - Prometheus 指标导出
提供 Prometheus 格式的监控指标
"""
import logging
from typing import Dict, Any, List
from datetime import datetime

from fastapi import APIRouter, Depends, Response

from backend.auth.jwt_utils import get_current_user
from backend.monitoring.metrics import metrics_collector
from backend.utils.quota import quota_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["监控指标"])


@router.get("/api/metrics")
async def metrics_endpoint(username: str = Depends(get_current_user)):
    """
    Prometheus 格式的监控指标端点
    
    可被 Prometheus 抓取，用于长期存储和告警
    """
    prometheus_data = metrics_collector.get_prometheus_metrics()
    return Response(content=prometheus_data, media_type="text/plain")


@router.get("/api/metrics/json")
async def metrics_json(username: str = Depends(get_current_user)):
    """
    JSON 格式的完整监控指标（需要认证）
    
    用于前端监控面板展示
    """
    return {
        "timestamp": datetime.now().isoformat(),
        "metrics": metrics_collector.get_all_stats(),
        "quota": quota_manager.get_snapshot().to_dict(),
    }


@router.get("/api/metrics/summary")
async def metrics_summary(username: str = Depends(get_current_user)):
    """
    简化的指标摘要（无需认证）
    
    用于快速查看系统状态
    """
    ws_stats = metrics_collector.get_ws_stats()
    system_stats = metrics_collector.get_system_stats()
    api_stats = metrics_collector.get_api_stats()
    quota_snapshot = quota_manager.get_snapshot()
    
    return {
        "uptime": system_stats["uptime_formatted"],
        "websocket": {
            "market_connections": ws_stats["market_connections"],
            "signal_connections": ws_stats["signal_connections"],
            "total": ws_stats["total_connections"],
        },
        "api": {
            "total_calls": api_stats["total_calls"],
            "recent_5min_calls": api_stats["recent_5min"]["calls"],
            "success_rate": api_stats["recent_5min"]["success_rate"],
        },
        "quota": {
            "usage_percent": quota_snapshot.usage_percent,
            "status": quota_snapshot.status,
            "estimated_cost": quota_snapshot.estimated_cost,
        },
    }


@router.get("/api/metrics/api-calls")
async def api_calls_metrics(
    hours: int = 24,
    username: str = Depends(get_current_user),
):
    """
    API 调用详细指标（需要认证）
    
    参数:
    - hours: 查询最近 N 小时的数据
    """
    api_stats = metrics_collector.get_api_stats()
    quota_history = quota_manager.get_history(days=min(hours // 24 + 1, 7))
    
    return {
        "current_stats": api_stats,
        "quota_history": [q.to_dict() for q in quota_history],
        "by_model": api_stats["by_model"],
    }


@router.get("/api/metrics/signals")
async def signal_metrics(
    hours: int = 24,
    username: str = Depends(get_current_user),
):
    """
    信号生成指标（需要认证）
    
    参数:
    - hours: 查询最近 N 小时的数据
    """
    from backend.database.db import async_session
    from backend.database.models import AISignal
    from sqlalchemy import select, func, desc
    from datetime import datetime, timedelta
    
    async with async_session() as session:
        # 计算时间范围
        since = datetime.now() - timedelta(hours=hours)
        
        # 总信号数
        total_result = await session.execute(
            select(func.count(AISignal.id)).where(AISignal.created_at >= since)
        )
        total_count = total_result.scalar() or 0
        
        # 按信号类型统计
        signal_types = await session.execute(
            select(AISignal.signal, func.count(AISignal.id))
            .where(AISignal.created_at >= since)
            .group_by(AISignal.signal)
        )
        by_signal = {s: c for s, c in signal_types.all()}
        
        # 按币种统计
        symbol_stats = await session.execute(
            select(AISignal.symbol, func.count(AISignal.id), func.avg(AISignal.confidence))
            .where(AISignal.created_at >= since)
            .group_by(AISignal.symbol)
            .order_by(desc(func.count(AISignal.id)))
        )
        by_symbol = [
            {"symbol": s, "count": c, "avg_confidence": round(float(avg), 2) if avg else 0}
            for s, c, avg in symbol_stats.all()
        ]
        
        # 最近信号
        recent_result = await session.execute(
            select(AISignal)
            .order_by(desc(AISignal.created_at))
            .limit(10)
        )
        recent_signals = [
            {
                "id": s.id,
                "symbol": s.symbol,
                "signal": s.signal,
                "confidence": s.confidence,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in recent_result.scalars().all()
        ]
    
    return {
        "period_hours": hours,
        "total_signals": total_count,
        "by_signal_type": by_signal,
        "by_symbol": by_symbol,
        "recent_signals": recent_signals,
    }


@router.get("/api/metrics/performance")
async def performance_metrics(username: str = Depends(get_current_user)):
    """
    性能指标（需要认证）
    
    包含 API 响应时间、数据库查询耗时等
    """
    api_stats = metrics_collector.get_api_stats()
    http_stats = metrics_collector.get_http_stats()
    
    # 获取信号生成性能
    signal_stats = metrics_collector.get_signal_stats()
    
    return {
        "api_performance": {
            "recent_5min": api_stats["recent_5min"],
            "by_model": {
                model: {
                    "avg_duration_ms": stats["avg_duration_ms"],
                    "success_rate": stats["success_rate"],
                }
                for model, stats in api_stats["by_model"].items()
            },
        },
        "http_performance": http_stats["recent_5min"] if "recent_5min" in http_stats else {},
        "signal_performance": {
            "avg_confidence": signal_stats["recent_1h"]["avg_confidence"] 
                if "recent_1h" in signal_stats and "avg_confidence" in signal_stats["recent_1h"] 
                else 0,
        },
    }


@router.get("/api/metrics/cost")
async def cost_metrics(username: str = Depends(get_current_user)):
    """
    成本指标（需要认证）
    
    包含 API 调用成本估算
    """
    api_stats = metrics_collector.get_api_stats()
    quota_snapshot = quota_manager.get_snapshot()
    cost_estimate = quota_manager.estimate_daily_cost()
    
    # 按模型计算成本
    by_model_cost = {}
    for model, stats in api_stats["by_model"].items():
        by_model_cost[model] = {
            "total_calls": stats["total"],
            "tokens_in": stats["total_tokens_in"],
            "tokens_out": stats["total_tokens_out"],
            "estimated_cost_cny": stats["estimated_cost_cny"],
        }
    
    return {
        "today": {
            "api_calls": quota_snapshot.total_calls,
            "estimated_cost_cny": quota_snapshot.estimated_cost,
            "by_model": by_model_cost,
        },
        "projected": {
            "daily_cost": cost_estimate["projected_daily_cost"],
            "monthly_estimate": cost_estimate["monthly_estimate"],
        },
        "quota": {
            "limit": quota_snapshot.quota_limit,
            "used": quota_snapshot.total_calls,
            "remaining": quota_snapshot.remaining,
            "usage_percent": quota_snapshot.usage_percent,
        },
    }


# Prometheus 指标收集器类（用于 future 扩展）
class PrometheusCollector:
    """
    Prometheus 指标收集器
    
    支持计数器、仪表盘、直方图等多种指标类型
    """
    
    def __init__(self):
        self.counters: Dict[str, Dict[str, Any]] = {}
        self.gauges: Dict[str, Dict[str, Any]] = {}
        self.histograms: Dict[str, Dict[str, Any]] = {}
    
    def counter(self, name: str, description: str, labels: List[str] = None):
        """创建或获取计数器"""
        if name not in self.counters:
            self.counters[name] = {
                "description": description,
                "labels": labels or [],
                "values": {},
            }
        return self.counters[name]
    
    def gauge(self, name: str, description: str, labels: List[str] = None):
        """创建或获取仪表盘"""
        if name not in self.gauges:
            self.gauges[name] = {
                "description": description,
                "labels": labels or [],
                "values": {},
            }
        return self.gauges[name]
    
    def increment_counter(self, name: str, labels: Dict[str, str] = None, value: float = 1):
        """增加计数器值"""
        counter = self.counters.get(name)
        if not counter:
            return
        
        key = self._labels_key(labels)
        counter["values"][key] = counter["values"].get(key, 0) + value
    
    def set_gauge(self, name: str, labels: Dict[str, str] = None, value: float = 0):
        """设置仪表盘值"""
        gauge = self.gauges.get(name)
        if not gauge:
            return
        
        key = self._labels_key(labels)
        gauge["values"][key] = value
    
    def _labels_key(self, labels: Dict[str, str] = None) -> str:
        """将标签字典转换为字符串键"""
        if not labels:
            return ""
        return ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    
    def generate_prometheus_format(self) -> str:
        """生成 Prometheus 格式的指标文本"""
        lines = []
        
        # 计数器
        for name, counter in self.counters.items():
            lines.append(f"# HELP {name} {counter['description']}")
            lines.append(f"# TYPE {name} counter")
            for key, value in counter["values"].items():
                if key:
                    lines.append(f'{name}{{{key}}} {value}')
                else:
                    lines.append(f'{name} {value}')
        
        # 仪表盘
        for name, gauge in self.gauges.items():
            lines.append(f"# HELP {name} {gauge['description']}")
            lines.append(f"# TYPE {name} gauge")
            for key, value in gauge["values"].items():
                if key:
                    lines.append(f'{name}{{{key}}} {value}')
                else:
                    lines.append(f'{name} {value}')
        
        return "\n".join(lines) + "\n"


# 全局 Prometheus 收集器实例
prometheus_collector = PrometheusCollector()
