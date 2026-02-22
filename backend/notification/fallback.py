"""
钢子出击 - 通知降级机制

当 Telegram 完全失败时：
1. 记录到数据库（NotificationLog 表）
2. 提供接口查询未读通知
3. 支持管理员后台查看和处理
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from sqlalchemy import select, update, and_, desc
from sqlalchemy.exc import SQLAlchemyError

from backend.database.db import get_async_session
from backend.database.models import NotificationLog
from backend.notification.telegram_bot import (
    NotificationType,
    NotificationStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class NotificationSummary:
    """通知摘要"""

    id: int
    type: str
    content_preview: str
    status: str
    retry_count: int
    created_at: datetime
    error_msg: str = ""


@dataclass
class NotificationDetail:
    """通知详情"""

    id: int
    type: str
    content: str
    status: str
    error_msg: str
    retry_count: int
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: Optional[datetime]


class NotificationFallbackManager:
    """
    通知降级管理器

    功能：
    - 管理失败的通知记录
    - 提供重试接口
    - 支持批量操作
    - 统计和报表
    """

    def __init__(self):
        self._max_content_preview = 100

    async def get_pending_notifications(
        self,
        notification_type: Optional[NotificationType] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[NotificationSummary]:
        """
        获取待处理的通知

        Args:
            notification_type: 筛选特定类型
            limit: 返回数量限制
            offset: 分页偏移

        Returns:
            通知摘要列表
        """
        try:
            async for session in get_async_session():
                query = (
                    select(NotificationLog)
                    .where(
                        NotificationLog.status.in_(
                            [
                                NotificationStatus.PENDING.value,
                                NotificationStatus.FAILED.value,
                            ]
                        )
                    )
                    .order_by(desc(NotificationLog.created_at))
                )

                if notification_type:
                    query = query.where(NotificationLog.type == notification_type.value)

                query = query.limit(limit).offset(offset)
                result = await session.execute(query)
                logs = result.scalars().all()

                return [
                    NotificationSummary(
                        id=log.id,
                        type=log.type,
                        content_preview=self._truncate_content(log.content),
                        status=log.status,
                        retry_count=log.retry_count,
                        created_at=log.created_at,
                        error_msg=log.error_msg,
                    )
                    for log in logs
                ]
        except SQLAlchemyError as e:
            logger.error(f"[Fallback] 查询待处理通知失败: {e}")
            return []

    async def get_notification_detail(
        self, notification_id: int
    ) -> Optional[NotificationDetail]:
        """
        获取通知详情

        Args:
            notification_id: 通知 ID

        Returns:
            通知详情，不存在则返回 None
        """
        try:
            async for session in get_async_session():
                result = await session.execute(
                    select(NotificationLog).where(NotificationLog.id == notification_id)
                )
                log = result.scalar_one_or_none()

                if not log:
                    return None

                return NotificationDetail(
                    id=log.id,
                    type=log.type,
                    content=log.content,
                    status=log.status,
                    error_msg=log.error_msg,
                    retry_count=log.retry_count,
                    metadata=self._parse_metadata(log.metadata_json),
                    created_at=log.created_at,
                    updated_at=log.updated_at,
                )
        except SQLAlchemyError as e:
            logger.error(f"[Fallback] 查询通知详情失败: {e}")
            return None

    async def mark_as_read(
        self,
        notification_id: int,
        new_status: NotificationStatus = NotificationStatus.SENT,
    ) -> bool:
        """
        标记通知为已处理

        Args:
            notification_id: 通知 ID
            new_status: 新状态

        Returns:
            是否成功
        """
        try:
            async for session in get_async_session():
                result = await session.execute(
                    update(NotificationLog)
                    .where(NotificationLog.id == notification_id)
                    .values(
                        status=new_status.value,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()
                return result.rowcount > 0
        except SQLAlchemyError as e:
            logger.error(f"[Fallback] 标记通知状态失败: {e}")
            return False

    async def mark_all_as_read(
        self, notification_type: Optional[NotificationType] = None
    ) -> int:
        """
        批量标记通知为已处理

        Args:
            notification_type: 仅标记特定类型，None 则标记所有

        Returns:
            更新的记录数
        """
        try:
            async for session in get_async_session():
                conditions = [
                    NotificationLog.status.in_(
                        [
                            NotificationStatus.PENDING.value,
                            NotificationStatus.FAILED.value,
                        ]
                    )
                ]

                if notification_type:
                    conditions.append(NotificationLog.type == notification_type.value)

                result = await session.execute(
                    update(NotificationLog)
                    .where(and_(*conditions))
                    .values(
                        status=NotificationStatus.SENT.value,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()
                return result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"[Fallback] 批量标记失败: {e}")
            return 0

    async def retry_notification(
        self, notification_id: int, send_func: callable
    ) -> Dict[str, Any]:
        """
        重试发送通知

        Args:
            notification_id: 通知 ID
            send_func: 发送函数，接收 content 返回发送结果

        Returns:
            重试结果
        """
        detail = await self.get_notification_detail(notification_id)
        if not detail:
            return {
                "success": False,
                "error": "通知不存在",
                "notification_id": notification_id,
            }

        if detail.status == NotificationStatus.SENT.value:
            return {
                "success": False,
                "error": "通知已发送",
                "notification_id": notification_id,
            }

        try:
            result = await send_func(detail.content)

            if result.get("success"):
                await self.mark_as_read(notification_id, NotificationStatus.SENT)
                logger.info(f"[Fallback] 通知 {notification_id} 重试成功")
            else:
                # 更新重试次数
                async for session in get_async_session():
                    await session.execute(
                        update(NotificationLog)
                        .where(NotificationLog.id == notification_id)
                        .values(
                            retry_count=detail.retry_count + 1,
                            error_msg=result.get("error", "Unknown"),
                            updated_at=datetime.now(timezone.utc),
                        )
                    )
                    await session.commit()

            return {
                "success": result.get("success"),
                "error": result.get("error"),
                "notification_id": notification_id,
                "retry_count": detail.retry_count + 1,
            }

        except Exception as e:
            logger.error(f"[Fallback] 重试发送失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "notification_id": notification_id,
            }

    async def get_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        获取通知统计

        Args:
            days: 统计天数

        Returns:
            统计信息
        """
        try:
            async for session in get_async_session():
                since = datetime.now(timezone.utc) - timedelta(days=days)

                # 总数量
                total_result = await session.execute(
                    select(NotificationLog).where(NotificationLog.created_at >= since)
                )
                total = len(total_result.scalars().all())

                # 按状态统计
                status_counts = {}
                for status in NotificationStatus:
                    result = await session.execute(
                        select(NotificationLog).where(
                            and_(
                                NotificationLog.status == status.value,
                                NotificationLog.created_at >= since,
                            )
                        )
                    )
                    status_counts[status.value] = len(result.scalars().all())

                # 按类型统计
                type_counts = {}
                for ntype in NotificationType:
                    result = await session.execute(
                        select(NotificationLog).where(
                            and_(
                                NotificationLog.type == ntype.value,
                                NotificationLog.created_at >= since,
                            )
                        )
                    )
                    type_counts[ntype.value] = len(result.scalars().all())

                # 高重试次数的通知
                high_retry_result = await session.execute(
                    select(NotificationLog).where(
                        and_(
                            NotificationLog.retry_count >= 3,
                            NotificationLog.created_at >= since,
                        )
                    )
                )
                high_retry = len(high_retry_result.scalars().all())

                return {
                    "period_days": days,
                    "total": total,
                    "by_status": status_counts,
                    "by_type": type_counts,
                    "high_retry_count": high_retry,
                    "failure_rate": (
                        status_counts.get(NotificationStatus.FAILED.value, 0) / total
                        if total > 0
                        else 0
                    ),
                }

        except SQLAlchemyError as e:
            logger.error(f"[Fallback] 统计失败: {e}")
            return {"error": str(e)}

    async def cleanup_old_records(
        self, days: int = 30, keep_failed: bool = True
    ) -> int:
        """
        清理旧记录

        Args:
            days: 保留天数
            keep_failed: 是否保留失败记录

        Returns:
            删除的记录数
        """
        try:
            async for session in get_async_session():
                cutoff = datetime.now(timezone.utc) - timedelta(days=days)

                conditions = [NotificationLog.created_at < cutoff]

                if keep_failed:
                    conditions.append(
                        NotificationLog.status != NotificationStatus.FAILED.value
                    )

                result = await session.execute(
                    select(NotificationLog).where(and_(*conditions))
                )
                old_records = result.scalars().all()

                count = 0
                for record in old_records:
                    await session.delete(record)
                    count += 1

                await session.commit()
                logger.info(f"[Fallback] 清理了 {count} 条旧记录")
                return count

        except SQLAlchemyError as e:
            logger.error(f"[Fallback] 清理旧记录失败: {e}")
            return 0

    def _truncate_content(self, content: str) -> str:
        """截断内容用于预览"""
        if len(content) <= self._max_content_preview:
            return content
        return content[: self._max_content_preview - 3] + "..."

    def _parse_metadata(self, metadata_str: str) -> Dict[str, Any]:
        """解析元数据字符串"""
        if not metadata_str:
            return {}
        try:
            import json

            return json.loads(metadata_str.replace("'", '"'))
        except Exception as e:
            logger.debug("[降级] 元数据 JSON 解析失败: %s", e)
            return {"raw": metadata_str}


# 全局管理器实例
_fallback_manager: Optional[NotificationFallbackManager] = None


def get_fallback_manager() -> NotificationFallbackManager:
    """获取降级管理器实例"""
    global _fallback_manager
    if _fallback_manager is None:
        _fallback_manager = NotificationFallbackManager()
    return _fallback_manager


# 便捷函数


async def get_pending_notifications(
    notification_type: Optional[NotificationType] = None, limit: int = 50
) -> List[NotificationSummary]:
    """获取待处理通知"""
    manager = get_fallback_manager()
    return await manager.get_pending_notifications(notification_type, limit)


async def retry_failed_notification(
    notification_id: int, send_func: callable
) -> Dict[str, Any]:
    """重试失败的通知"""
    manager = get_fallback_manager()
    return await manager.retry_notification(notification_id, send_func)


async def get_notification_stats(days: int = 7) -> Dict[str, Any]:
    """获取通知统计"""
    manager = get_fallback_manager()
    return await manager.get_statistics(days)


async def log_notification_failure(
    content: str,
    error: str,
    notification_type: NotificationType = NotificationType.INFO,
    retry_count: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    手动记录通知失败（供外部使用）

    注意：telegram_bot.py 中已内置此功能，一般不需要直接调用
    """
    try:
        async for session in get_async_session():
            log = NotificationLog(
                type=notification_type.value,
                content=content[:2000] if content else "",
                status=NotificationStatus.FAILED.value,
                error_msg=error[:1000] if error else "",
                retry_count=retry_count,
                metadata=str(metadata) if metadata else "",
                created_at=datetime.now(timezone.utc),
            )
            session.add(log)
            await session.commit()
            return True
    except Exception as e:
        logger.error(f"[Fallback] 手动记录失败: {e}")
        return False
