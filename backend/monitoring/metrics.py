"""
钢子出击 - 指标采集器
用于收集 AI 分析、WebSocket、API 调用等业务的指标数据
"""
import asyncio
import time
import logging
from datetime import datetime
from typing import Dict, List, Any
from dataclasses import dataclass
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


@dataclass
class APICallMetrics:
    """API 调用指标"""
    timestamp: float
    model: str
    duration_ms: float
    success: bool
    tokens_in: int = 0
    tokens_out: int = 0
    endpoint: str = ""
    error: str = ""


@dataclass
class SignalMetrics:
    """信号生成指标"""
    timestamp: float
    symbol: str
    signal: str
    confidence: float
    duration_ms: float
    success: bool


@dataclass
class RequestMetrics:
    """HTTP 请求指标"""
    timestamp: float
    method: str
    path: str
    status_code: int
    duration_ms: float
    client_ip: str = ""


class MetricsCollector:
    """
    指标采集器
    
    功能：
    1. API 调用耗时和成功率统计
    2. WebSocket 连接数追踪
    3. 信号生成频率统计
    4. Token 使用量和成本估算
    5. HTTP 请求性能指标
    """
    
    # 历史数据保留数量
    MAX_HISTORY_SIZE = 10000
    
    def __init__(self):
        self._lock = asyncio.Lock()
        
        # API 调用统计
        self._api_calls: deque[APICallMetrics] = deque(maxlen=self.MAX_HISTORY_SIZE)
        self._api_calls_by_model: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "total": 0,
            "success": 0,
            "failed": 0,
            "total_duration_ms": 0.0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
        })
        
        # 信号统计
        self._signals: deque[SignalMetrics] = deque(maxlen=self.MAX_HISTORY_SIZE)
        self._signals_by_symbol: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "total": 0,
            "buy": 0,
            "sell": 0,
            "hold": 0,
            "total_duration_ms": 0.0,
        })
        
        # HTTP 请求统计
        self._http_requests: deque[RequestMetrics] = deque(maxlen=self.MAX_HISTORY_SIZE)
        self._http_stats: Dict[str, Any] = {
            "total": 0,
            "2xx": 0,
            "4xx": 0,
            "5xx": 0,
            "total_duration_ms": 0.0,
        }
        
        # WebSocket 连接数（由外部更新）
        self._ws_market_connections = 0
        self._ws_signal_connections = 0
        self._ws_peak_connections = 0
        
        # 启动时间
        self._start_time = time.time()
        
        # DeepSeek 价格配置（元/千 token）
        self._cost_per_1k = {
            "deepseek-chat": 0.001,
            "deepseek-chat-output": 0.002,
            "deepseek-reasoner": 0.003,
            "deepseek-reasoner-output": 0.006,
        }
    
    async def record_api_call(
        self,
        model: str,
        duration_ms: float,
        success: bool,
        tokens_in: int = 0,
        tokens_out: int = 0,
        endpoint: str = "",
        error: str = "",
    ):
        """记录一次 API 调用"""
        async with self._lock:
            metric = APICallMetrics(
                timestamp=time.time(),
                model=model,
                duration_ms=duration_ms,
                success=success,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                endpoint=endpoint,
                error=error,
            )
            self._api_calls.append(metric)
            
            # 更新模型统计
            stats = self._api_calls_by_model[model]
            stats["total"] += 1
            if success:
                stats["success"] += 1
            else:
                stats["failed"] += 1
            stats["total_duration_ms"] += duration_ms
            stats["total_tokens_in"] += tokens_in
            stats["total_tokens_out"] += tokens_out
    
    async def record_signal(
        self,
        symbol: str,
        signal: str,
        confidence: float,
        duration_ms: float,
        success: bool = True,
    ):
        """记录一次信号生成"""
        async with self._lock:
            metric = SignalMetrics(
                timestamp=time.time(),
                symbol=symbol,
                signal=signal.upper(),
                confidence=confidence,
                duration_ms=duration_ms,
                success=success,
            )
            self._signals.append(metric)
            
            # 更新币种统计
            stats = self._signals_by_symbol[symbol]
            stats["total"] += 1
            stats["total_duration_ms"] += duration_ms
            
            if signal.upper() == "BUY":
                stats["buy"] += 1
            elif signal.upper() == "SELL":
                stats["sell"] += 1
            else:
                stats["hold"] += 1
    
    async def record_debate_analysis(
        self,
        symbol: str,
        num_roles: int,
        duration_ms: float,
        success: bool,
    ):
        """记录辩论分析指标（兼容旧接口）"""
        # 这里可以添加额外的辩论分析指标
        pass
    
    async def record_http_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        client_ip: str = "",
    ):
        """记录一次 HTTP 请求"""
        async with self._lock:
            metric = RequestMetrics(
                timestamp=time.time(),
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
            )
            self._http_requests.append(metric)
            
            # 更新 HTTP 统计
            self._http_stats["total"] += 1
            self._http_stats["total_duration_ms"] += duration_ms
            
            if 200 <= status_code < 300:
                self._http_stats["2xx"] += 1
            elif 400 <= status_code < 500:
                self._http_stats["4xx"] += 1
            elif 500 <= status_code < 600:
                self._http_stats["5xx"] += 1
    
    def update_ws_connections(self, market_count: int, signal_count: int):
        """更新 WebSocket 连接数"""
        self._ws_market_connections = market_count
        self._ws_signal_connections = signal_count
        total = market_count + signal_count
        if total > self._ws_peak_connections:
            self._ws_peak_connections = total
    
    def _calculate_latency_percentiles(self, durations: List[float]) -> Dict[str, float]:
        """计算延迟百分位数"""
        if not durations:
            return {"p50": 0, "p90": 0, "p95": 0, "p99": 0}
        
        sorted_durations = sorted(durations)
        n = len(sorted_durations)
        
        def percentile(p: float) -> float:
            idx = int(n * p / 100)
            return sorted_durations[min(idx, n - 1)]
        
        return {
            "p50": percentile(50),
            "p90": percentile(90),
            "p95": percentile(95),
            "p99": percentile(99),
        }
    
    def _get_recent_metrics(self, metrics_deque: deque, seconds: int = 300) -> list:
        """获取最近 N 秒的指标"""
        cutoff = time.time() - seconds
        return [m for m in metrics_deque if m.timestamp >= cutoff]
    
    def get_api_stats(self) -> Dict[str, Any]:
        """获取 API 调用统计"""
        total_calls = len(self._api_calls)
        recent_calls = self._get_recent_metrics(self._api_calls, 300)
        
        if not recent_calls:
            return {
                "total_calls": total_calls,
                "recent_5min": {"calls": 0, "success_rate": 0, "avg_duration_ms": 0},
                "by_model": {},
            }
        
        # 计算最近 5 分钟的统计
        recent_success = sum(1 for c in recent_calls if c.success)
        recent_durations = [c.duration_ms for c in recent_calls]
        
        # 按模型统计
        by_model = {}
        for model, stats in self._api_calls_by_model.items():
            total = stats["total"]
            by_model[model] = {
                "total": total,
                "success": stats["success"],
                "failed": stats["failed"],
                "success_rate": round(stats["success"] / total * 100, 2) if total > 0 else 0,
                "avg_duration_ms": round(stats["total_duration_ms"] / total, 2) if total > 0 else 0,
                "total_tokens_in": stats["total_tokens_in"],
                "total_tokens_out": stats["total_tokens_out"],
                "estimated_cost_cny": round(
                    (stats["total_tokens_in"] / 1000 * self._cost_per_1k.get(model, 0.001)) +
                    (stats["total_tokens_out"] / 1000 * self._cost_per_1k.get(f"{model}-output", 0.002)),
                    4
                ),
            }
        
        return {
            "total_calls": total_calls,
            "recent_5min": {
                "calls": len(recent_calls),
                "success_rate": round(recent_success / len(recent_calls) * 100, 2),
                "avg_duration_ms": round(sum(recent_durations) / len(recent_durations), 2),
                "latency_percentiles_ms": self._calculate_latency_percentiles(recent_durations),
            },
            "by_model": by_model,
        }
    
    def get_signal_stats(self) -> Dict[str, Any]:
        """获取信号生成统计"""
        total_signals = len(self._signals)
        recent_signals = self._get_recent_metrics(self._signals, 3600)  # 最近 1 小时
        
        if not recent_signals:
            return {
                "total_signals": total_signals,
                "recent_1h": {"count": 0, "by_type": {}},
                "by_symbol": {},
            }
        
        # 按信号类型统计
        by_type = {"BUY": 0, "SELL": 0, "HOLD": 0}
        for s in recent_signals:
            by_type[s.signal] = by_type.get(s.signal, 0) + 1
        
        # 按币种统计
        by_symbol = {}
        for symbol, stats in self._signals_by_symbol.items():
            total = stats["total"]
            by_symbol[symbol] = {
                "total": total,
                "buy": stats["buy"],
                "sell": stats["sell"],
                "hold": stats["hold"],
                "avg_duration_ms": round(stats["total_duration_ms"] / total, 2) if total > 0 else 0,
            }
        
        return {
            "total_signals": total_signals,
            "recent_1h": {
                "count": len(recent_signals),
                "by_type": by_type,
                "avg_confidence": round(
                    sum(s.confidence for s in recent_signals) / len(recent_signals), 2
                ),
            },
            "by_symbol": by_symbol,
        }
    
    def get_http_stats(self) -> Dict[str, Any]:
        """获取 HTTP 请求统计"""
        recent_requests = self._get_recent_metrics(self._http_requests, 300)
        
        if not recent_requests:
            return {
                "total": self._http_stats["total"],
                "recent_5min": {"count": 0, "rps": 0, "error_rate": 0},
            }
        
        recent_durations = [r.duration_ms for r in recent_requests]
        recent_errors = sum(1 for r in recent_requests if r.status_code >= 500)
        
        return {
            "total": self._http_stats["total"],
            "by_status": {
                "2xx": self._http_stats["2xx"],
                "4xx": self._http_stats["4xx"],
                "5xx": self._http_stats["5xx"],
            },
            "recent_5min": {
                "count": len(recent_requests),
                "rps": round(len(recent_requests) / 300, 2),
                "error_rate": round(recent_errors / len(recent_requests) * 100, 2),
                "latency_percentiles_ms": self._calculate_latency_percentiles(recent_durations),
            },
        }
    
    def get_ws_stats(self) -> Dict[str, Any]:
        """获取 WebSocket 连接统计"""
        return {
            "market_connections": self._ws_market_connections,
            "signal_connections": self._ws_signal_connections,
            "total_connections": self._ws_market_connections + self._ws_signal_connections,
            "peak_connections": self._ws_peak_connections,
        }
    
    def get_system_stats(self) -> Dict[str, Any]:
        """获取系统统计"""
        uptime_seconds = time.time() - self._start_time
        return {
            "uptime_seconds": int(uptime_seconds),
            "uptime_formatted": self._format_duration(uptime_seconds),
            "start_time": datetime.fromtimestamp(self._start_time).isoformat(),
        }
    
    def _format_duration(self, seconds: float) -> str:
        """格式化持续时间"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分钟")
        if secs > 0 or not parts:
            parts.append(f"{secs}秒")
        
        return "".join(parts)
    
    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有统计信息"""
        return {
            "api": self.get_api_stats(),
            "signals": self.get_signal_stats(),
            "http": self.get_http_stats(),
            "websocket": self.get_ws_stats(),
            "system": self.get_system_stats(),
            "timestamp": datetime.now().isoformat(),
        }
    
    def get_prometheus_metrics(self) -> str:
        """生成 Prometheus 格式的指标"""
        lines = []
        
        # HTTP 请求总数
        lines.append("# HELP http_requests_total Total HTTP requests")
        lines.append("# TYPE http_requests_total counter")
        lines.append(f'http_requests_total{{status="2xx"}} {self._http_stats["2xx"]}')
        lines.append(f'http_requests_total{{status="4xx"}} {self._http_stats["4xx"]}')
        lines.append(f'http_requests_total{{status="5xx"}} {self._http_stats["5xx"]}')
        
        # API 调用总数
        lines.append("# HELP ai_analysis_total Total AI analysis calls")
        lines.append("# TYPE ai_analysis_total counter")
        for model, stats in self._api_calls_by_model.items():
            lines.append(f'ai_analysis_total{{model="{model}"}} {stats["total"]}')
        
        # WebSocket 连接数
        lines.append("# HELP websocket_connections Current WebSocket connections")
        lines.append("# TYPE websocket_connections gauge")
        lines.append(f'websocket_connections{{type="market"}} {self._ws_market_connections}')
        lines.append(f'websocket_connections{{type="signal"}} {self._ws_signal_connections}')
        
        # 系统运行时间
        lines.append("# HELP system_uptime_seconds System uptime in seconds")
        lines.append("# TYPE system_uptime_seconds gauge")
        lines.append(f"system_uptime_seconds {int(time.time() - self._start_time)}")
        
        return "\n".join(lines) + "\n"


# 全局指标采集器实例
metrics_collector = MetricsCollector()
