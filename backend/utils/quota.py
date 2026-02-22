import asyncio
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass
from collections import defaultdict

from sqlalchemy import select

from backend.config import settings
from backend.database.db import async_session
from backend.database.models import QuotaDailyStat

logger = logging.getLogger(__name__)


class QuotaStatus(Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    EXCEEDED = "exceeded"


class CallType(Enum):
    ANALYSIS = "analysis"
    CHAT = "chat"
    REASONER = "reasoner"
    OTHER = "other"


@dataclass
class QuotaSnapshot:
    date: str
    total_calls: int = 0
    analysis_calls: int = 0
    chat_calls: int = 0
    reasoner_calls: int = 0
    estimated_cost: float = 0.0
    quota_limit: int = 0
    status: str = "normal"
    remaining: int = 0
    usage_percent: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "total_calls": self.total_calls,
            "analysis_calls": self.analysis_calls,
            "chat_calls": self.chat_calls,
            "reasoner_calls": self.reasoner_calls,
            "estimated_cost": round(self.estimated_cost, 4),
            "quota_limit": self.quota_limit,
            "status": self.status,
            "remaining": self.remaining,
            "usage_percent": round(self.usage_percent, 2),
        }


class QuotaManager:
    DEFAULT_DAILY_QUOTA = 10000
    DEFAULT_WARNING_THRESHOLD = 0.8
    DEFAULT_CRITICAL_THRESHOLD = 0.9

    COST_PER_1K_TOKENS = {
        "deepseek-chat": 0.001,
        "deepseek-chat-output": 0.002,
        "deepseek-reasoner": 0.003,
        "deepseek-reasoner-output": 0.006,
    }

    AVG_INPUT_TOKENS = {
        CallType.ANALYSIS: 2000,
        CallType.CHAT: 500,
        CallType.REASONER: 3000,
    }

    AVG_OUTPUT_TOKENS = {
        CallType.ANALYSIS: 500,
        CallType.CHAT: 300,
        CallType.REASONER: 800,
    }

    def __init__(self):
        self._lock = asyncio.Lock()
        self._daily_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "total_calls": 0,
                "analysis_calls": 0,
                "chat_calls": 0,
                "reasoner_calls": 0,
                "tokens_input": 0,
                "tokens_output": 0,
                "estimated_cost": 0.0,
                "details": [],
            }
        )
        self._current_date = self._get_date_key()
        self._warning_sent = False
        self._critical_sent = False

        self._load_config()
        # Phase E：不再混用 sqlite3，同一套 async SQLAlchemy 引擎持久化
        # 说明：初始化阶段不做 await DB 读取；启动后由 lifespan 调用 load_from_db() 恢复当日数据。

    async def load_from_db(self):
        """从 QuotaDailyStat 表读取当日记录，恢复到 _daily_stats 内存字典。
        应在 lifespan 中 init_db() 之后调用。DB 无记录则保持默认 0，不报错。"""
        date_key = self._get_date_key()
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(QuotaDailyStat).where(QuotaDailyStat.date == date_key)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    logger.info(f"[配额] 当日 ({date_key}) 无历史记录，从 0 开始计数")
                    return
                async with self._lock:
                    stats = self._daily_stats[date_key]
                    stats["total_calls"] = int(row.total_calls or 0)
                    stats["analysis_calls"] = int(row.analysis_calls or 0)
                    stats["chat_calls"] = int(row.chat_calls or 0)
                    stats["reasoner_calls"] = int(row.reasoner_calls or 0)
                    stats["tokens_input"] = int(row.tokens_input or 0)
                    stats["tokens_output"] = int(row.tokens_output or 0)
                    stats["estimated_cost"] = float(row.estimated_cost or 0.0)
                    self._current_date = date_key
                logger.info(
                    f"[配额] 已从 DB 恢复当日配额: "
                    f"total={stats['total_calls']}, "
                    f"analysis={stats['analysis_calls']}, "
                    f"chat={stats['chat_calls']}, "
                    f"reasoner={stats['reasoner_calls']}, "
                    f"cost={stats['estimated_cost']:.4f}"
                )
        except Exception as e:
            logger.warning(f"[配额] 从 DB 加载当日配额失败（不影响功能，从 0 开始）: {e}")

    def _load_config(self):
        self.enabled = getattr(settings, "ENABLE_QUOTA_LIMIT", True)
        self.daily_quota = getattr(
            settings, "DAILY_API_QUOTA", self.DEFAULT_DAILY_QUOTA
        )
        self.warning_threshold = getattr(
            settings, "QUOTA_WARNING_THRESHOLD", self.DEFAULT_WARNING_THRESHOLD
        )
        self.critical_threshold = getattr(
            settings, "QUOTA_CRITICAL_THRESHOLD", self.DEFAULT_CRITICAL_THRESHOLD
        )

        self.cost_chat = getattr(settings, "DEEPSEEK_CHAT_COST_PER_1K", 0.001)
        self.cost_r1 = getattr(settings, "DEEPSEEK_R1_COST_PER_1K", 0.003)

        self.COST_PER_1K_TOKENS["deepseek-chat"] = self.cost_chat
        self.COST_PER_1K_TOKENS["deepseek-reasoner"] = self.cost_r1

    def _get_date_key(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    async def _persist_day(self, date_key: str):
        try:
            stats = self._daily_stats.get(date_key)
            if not stats:
                return
            async with async_session() as db:
                existing = await db.execute(
                    select(QuotaDailyStat).where(QuotaDailyStat.date == date_key)
                )
                row = existing.scalar_one_or_none()
                if row is None:
                    row = QuotaDailyStat(date=date_key)
                    db.add(row)
                row.total_calls = int(stats.get("total_calls", 0) or 0)
                row.analysis_calls = int(stats.get("analysis_calls", 0) or 0)
                row.chat_calls = int(stats.get("chat_calls", 0) or 0)
                row.reasoner_calls = int(stats.get("reasoner_calls", 0) or 0)
                row.tokens_input = int(stats.get("tokens_input", 0) or 0)
                row.tokens_output = int(stats.get("tokens_output", 0) or 0)
                row.estimated_cost = float(stats.get("estimated_cost", 0.0) or 0.0)
                row.updated_at = datetime.now()
                await db.commit()
        except Exception as e:
            logger.warning(f"[配额] 统计数据持久化失败（不影响功能）: {e}")

    def _check_date_reset(self):
        current = self._get_date_key()
        if current != self._current_date:
            logger.info(
                f"[配额] 日期切换: {self._current_date} -> {current}，重置配额计数"
            )
            self._current_date = current
            self._warning_sent = False
            self._critical_sent = False
            # 新的一天从 0 开始，历史会在持久化表中保留

    def _get_status(self, usage_percent: float) -> QuotaStatus:
        if usage_percent >= 1.0:
            return QuotaStatus.EXCEEDED
        if usage_percent >= self.critical_threshold:
            return QuotaStatus.CRITICAL
        if usage_percent >= self.warning_threshold:
            return QuotaStatus.WARNING
        return QuotaStatus.NORMAL

    def _calculate_cost(
        self, call_type: CallType, tokens_in: int = 0, tokens_out: int = 0
    ) -> float:
        if tokens_in == 0 and tokens_out == 0:
            tokens_in = self.AVG_INPUT_TOKENS.get(call_type, 1000)
            tokens_out = self.AVG_OUTPUT_TOKENS.get(call_type, 500)

        model = (
            "deepseek-reasoner" if call_type == CallType.REASONER else "deepseek-chat"
        )
        cost_in = (tokens_in / 1000) * self.COST_PER_1K_TOKENS.get(model, 0.001)
        cost_out = (tokens_out / 1000) * self.COST_PER_1K_TOKENS.get(
            f"{model}-output", 0.002
        )
        return cost_in + cost_out

    async def check_quota(
        self, call_type: CallType = CallType.ANALYSIS
    ) -> tuple[bool, str]:
        if not self.enabled:
            return True, "配额限制已禁用"

        async with self._lock:
            self._check_date_reset()
            stats = self._daily_stats[self._current_date]
            usage_percent = stats["total_calls"] / self.daily_quota
            status = self._get_status(usage_percent)

            if status == QuotaStatus.EXCEEDED:
                return (
                    False,
                    f"API 配额已超限（{stats['total_calls']}/{self.daily_quota}），请明日再试",
                )

            if call_type == CallType.ANALYSIS and status == QuotaStatus.CRITICAL:
                return False, "配额即将耗尽，暂停非必要分析以保留核心功能"

            return True, f"配额充足（{stats['total_calls']}/{self.daily_quota}）"

    async def record_call(
        self,
        call_type: CallType,
        tokens_in: int = 0,
        tokens_out: int = 0,
        success: bool = True,
        symbol: str = "",
        detail: str = "",
    ) -> QuotaSnapshot:
        async with self._lock:
            self._check_date_reset()
            date_key = self._current_date
            stats = self._daily_stats[date_key]

            stats["total_calls"] += 1
            if call_type == CallType.ANALYSIS:
                stats["analysis_calls"] += 1
            elif call_type == CallType.CHAT:
                stats["chat_calls"] += 1
            elif call_type == CallType.REASONER:
                stats["reasoner_calls"] += 1

            stats["tokens_input"] += tokens_in or self.AVG_INPUT_TOKENS.get(
                call_type, 1000
            )
            stats["tokens_output"] += tokens_out or self.AVG_OUTPUT_TOKENS.get(
                call_type, 500
            )

            cost = self._calculate_cost(call_type, tokens_in, tokens_out)
            stats["estimated_cost"] += cost

            stats["details"].append(
                {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "type": call_type.value,
                    "success": success,
                    "symbol": symbol,
                    "detail": detail,
                    "cost": round(cost, 6),
                }
            )
            if len(stats["details"]) > 100:
                stats["details"] = stats["details"][-100:]

            snapshot = self.get_snapshot()

        # 锁外持久化（DB I/O 不阻塞其他协程获取锁）
        try:
            await self._persist_day(date_key)
        except Exception as persist_err:
            logger.warning(f"[配额] record_call 持久化失败（已忽略）: {persist_err}")

        try:
            await self._check_alerts(snapshot)
        except Exception as alert_err:
            logger.warning(f"[配额] 告警检查失败（已忽略）: {alert_err}")
        return snapshot

    async def _check_alerts(self, snapshot: QuotaSnapshot):
        status = snapshot.status
        if status == "critical" and not self._critical_sent:
            logger.warning(
                f"[配额告警] 严重警告！API 配额使用率已达 {snapshot.usage_percent:.1f}% "
                f"({snapshot.total_calls}/{snapshot.quota_limit})"
            )
            self._critical_sent = True
        elif status == "warning" and not self._warning_sent:
            logger.warning(
                f"[配额告警] API 配额使用率已达 {snapshot.usage_percent:.1f}% "
                f"({snapshot.total_calls}/{snapshot.quota_limit})，请注意"
            )
            self._warning_sent = True

    def get_snapshot(self, date: Optional[str] = None) -> QuotaSnapshot:
        if date is None:
            date = self._get_date_key()
        # 说明：此处不做阻塞式 DB 读取；如需历史可通过 get_history 查看（它会走内存快照）。

        stats = self._daily_stats.get(
            date,
            {
                "total_calls": 0,
                "analysis_calls": 0,
                "chat_calls": 0,
                "reasoner_calls": 0,
                "estimated_cost": 0.0,
            },
        )

        usage_percent = (
            stats["total_calls"] / self.daily_quota if self.daily_quota > 0 else 0
        )
        status = self._get_status(usage_percent)

        return QuotaSnapshot(
            date=date,
            total_calls=stats["total_calls"],
            analysis_calls=stats.get("analysis_calls", 0),
            chat_calls=stats.get("chat_calls", 0),
            reasoner_calls=stats.get("reasoner_calls", 0),
            estimated_cost=stats.get("estimated_cost", 0.0),
            quota_limit=self.daily_quota,
            status=status.value,
            remaining=max(0, self.daily_quota - stats["total_calls"]),
            usage_percent=usage_percent * 100,
        )

    def get_history(self, days: int = 7) -> list[QuotaSnapshot]:
        snapshots = []
        today = datetime.now(timezone.utc)
        for i in range(days):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            snapshots.append(self.get_snapshot(date))
        return snapshots

    def get_degradation_strategy(self) -> Dict[str, Any]:
        snapshot = self.get_snapshot()
        usage = snapshot.usage_percent / 100
        strategies = {
            "enabled": self.enabled,
            "current_usage": snapshot.usage_percent,
            "status": snapshot.status,
            "actions": [],
        }

        if usage >= 1.0:
            strategies["actions"] = [
                "暂停所有非必要 AI 分析",
                "仅保留用户主动触发的分析",
                "关闭定时任务中的次要币种分析",
                "启用本地缓存策略",
            ]
        elif usage >= self.critical_threshold:
            strategies["actions"] = [
                "减少次要币种分析频率",
                "限制聊天接口调用",
                "启用结果缓存复用",
                "缩短分析响应长度",
            ]
        elif usage >= self.warning_threshold:
            strategies["actions"] = [
                "监控配额使用趋势",
                "考虑优化提示词减少 token 消耗",
                "准备降级预案",
            ]
        else:
            strategies["actions"] = ["正常运行，持续监控"]

        return strategies

    def estimate_daily_cost(self) -> Dict[str, Any]:
        snapshot = self.get_snapshot()
        now = datetime.now()
        day_progress = (now.hour * 3600 + now.minute * 60 + now.second) / 86400
        projected_total = (
            snapshot.estimated_cost / day_progress
            if day_progress > 0
            else snapshot.estimated_cost
        )
        return {
            "current_cost": round(snapshot.estimated_cost, 4),
            "projected_daily_cost": round(projected_total, 4),
            "monthly_estimate": round(projected_total * 30, 2),
            "cost_per_call": round(
                snapshot.estimated_cost / max(snapshot.total_calls, 1), 6
            ),
            "currency": "CNY",
        }

    def should_skip_secondary_analysis(self) -> bool:
        if not self.enabled:
            return False
        snapshot = self.get_snapshot()
        usage = snapshot.usage_percent / 100
        if usage >= self.critical_threshold:
            logger.info(
                f"[配额] 使用率 {snapshot.usage_percent:.1f}% >= 阈值，跳过次要币种分析"
            )
            return True
        return False

    def should_skip_scheduled_analysis(self) -> bool:
        if not self.enabled:
            return False
        snapshot = self.get_snapshot()
        if snapshot.usage_percent >= 95:
            logger.warning(
                f"[配额] 使用率 {snapshot.usage_percent:.1f}% >= 95%，暂停定时分析任务"
            )
            return True
        return False


quota_manager = QuotaManager()
