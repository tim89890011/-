"""
钢子出击 - Telegram 通知客户端（带指数退避重试机制）

特性：
- 指数退避重试（1s, 2s, 4s, 8s, 16s）
- 区分可重试错误（网络超时）和不可重试错误（Token 无效）
- 失败时降级到日志记录和数据库
- 支持异步消息队列
"""

import asyncio
import logging
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timezone
from enum import Enum
import httpx
from backend.config import settings
from backend.database.db import get_async_session
from backend.database.models import NotificationLog

logger = logging.getLogger(__name__)

# 复用 httpx 客户端，避免每次创建新连接
_tg_client: Optional[httpx.AsyncClient] = None


class RetryableError(Exception):
    """可重试错误（网络超时、服务器错误等临时性问题）"""

    pass


class NonRetryableError(Exception):
    """不可重试错误（配置错误、权限问题等）"""

    pass


class NotificationType(str, Enum):
    """通知类型"""

    TRADE_SIGNAL = "trade_signal"
    PRICE_ALERT = "price_alert"
    SYSTEM_ALERT = "system_alert"
    ERROR = "error"
    INFO = "info"


class NotificationStatus(str, Enum):
    """通知状态"""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    FALLBACK = "fallback"


class TelegramErrorClassifier:
    """Telegram API 错误分类器"""

    # 不可重试的错误码（配置问题、权限问题）
    NON_RETRYABLE_CODES = {
        401: "Unauthorized - Bot token 无效",
        403: "Forbidden - 无权访问 Chat",
        404: "Not Found - Bot 或 Chat 不存在",
        400: "Bad Request - 请求格式错误",
    }

    # 可重试的错误码（服务器错误或临时问题）
    RETRYABLE_CODES = {
        429: "Too Many Requests - 请求频率限制",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
    }

    @classmethod
    def classify(cls, error: Exception, status_code: Optional[int] = None) -> type:
        """
        分类错误类型

        Returns:
            RetryableError: 应该重试的错误
            NonRetryableError: 不应该重试的错误
        """
        # 网络层错误通常是可重试的
        if isinstance(
            error,
            (
                httpx.TimeoutException,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.ConnectError,
                httpx.NetworkError,
                httpx.ReadError,
                httpx.WriteError,
            ),
        ):
            return RetryableError

        # 根据 HTTP 状态码判断
        if status_code:
            if status_code in cls.NON_RETRYABLE_CODES:
                return NonRetryableError
            if status_code in cls.RETRYABLE_CODES:
                return RetryableError
            if status_code >= 500:
                return RetryableError
            if status_code >= 400:
                return NonRetryableError

        # 默认视为可重试
        return RetryableError


class MessageQueue:
    """异步消息队列（用于批量发送和流量控制）"""

    def __init__(self, max_size: int = 1000, rate_limit: float = 1.0):
        """
        Args:
            max_size: 队列最大长度
            rate_limit: 发送间隔（秒），避免触发 Telegram 频率限制
        """
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self.rate_limit = rate_limit
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
        self._handlers: list[Callable] = []

    def add_handler(self, handler: Callable):
        """添加消息处理器"""
        self._handlers.append(handler)

    async def put(self, message: Dict[str, Any]) -> bool:
        """添加消息到队列"""
        try:
            self.queue.put_nowait(message)
            return True
        except asyncio.QueueFull:
            logger.error("[MessageQueue] 队列已满，消息丢弃")
            return False

    async def start(self):
        """启动队列处理器"""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("[MessageQueue] 消息队列已启动")

    async def stop(self):
        """停止队列处理器"""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("[MessageQueue] 消息队列已停止")

    async def _worker(self):
        """队列工作器"""
        while self._running:
            try:
                message = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                for handler in self._handlers:
                    try:
                        await handler(message)
                    except Exception as e:
                        logger.error(f"[MessageQueue] 处理器错误: {e}")
                await asyncio.sleep(self.rate_limit)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[MessageQueue] 工作器错误: {e}")


# 全局消息队列实例
_message_queue: Optional[MessageQueue] = None


def _get_tg_client() -> httpx.AsyncClient:
    """获取或创建 Telegram HTTP 客户端"""
    global _tg_client
    if _tg_client is None or _tg_client.is_closed:
        timeout = httpx.Timeout(
            connect=10.0,  # 连接超时
            read=30.0,  # 读取超时
            write=10.0,  # 写入超时
            pool=5.0,  # 连接池超时
        )
        _tg_client = httpx.AsyncClient(timeout=timeout)
    return _tg_client


def _get_message_queue() -> MessageQueue:
    """获取或创建消息队列"""
    global _message_queue
    if _message_queue is None:
        _message_queue = MessageQueue(
            max_size=settings.TG_QUEUE_MAX_SIZE, rate_limit=settings.TG_RATE_LIMIT
        )
    return _message_queue


def _get_backoff_time(attempt: int, base_delay: float = 1.0) -> float:
    """
    计算指数退避时间

    Args:
        attempt: 当前尝试次数（从 0 开始）
        base_delay: 基础延迟（秒）

    Returns:
        等待时间（秒）
    """
    return base_delay * (2**attempt)


async def _log_to_database(
    content: str,
    notification_type: NotificationType,
    status: NotificationStatus,
    error_msg: str = "",
    retry_count: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    记录通知到数据库

    Args:
        content: 通知内容
        notification_type: 通知类型
        status: 通知状态
        error_msg: 错误信息
        retry_count: 重试次数
        metadata: 附加元数据

    Returns:
        是否记录成功
    """
    try:
        async for session in get_async_session():
            log = NotificationLog(
                type=notification_type.value,
                content=content[:2000] if content else "",  # 限制长度
                status=status.value,
                error_msg=error_msg[:1000] if error_msg else "",
                retry_count=retry_count,
                metadata_json=str(metadata) if metadata else "",
                created_at=datetime.now(timezone.utc),
            )
            session.add(log)
            await session.commit()
            return True
    except Exception as e:
        logger.error(f"[Notification] 数据库记录失败: {e}")
        return False


async def _send_telegram_raw(
    text: str,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML",
    disable_notification: bool = False,
) -> Dict[str, Any]:
    """
    原始 Telegram 发送请求（带分类错误处理）

    Args:
        text: 消息文本
        chat_id: 目标 Chat ID（默认使用配置）
        parse_mode: 解析模式
        disable_notification: 静默发送

    Returns:
        API 响应数据

    Raises:
        RetryableError: 可重试错误
        NonRetryableError: 不可重试错误
    """
    if not settings.TG_BOT_TOKEN:
        raise NonRetryableError("Telegram Bot Token 未配置")

    url = f"https://api.telegram.org/bot{settings.TG_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": chat_id or settings.TG_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_notification": disable_notification,
    }

    try:
        client = _get_tg_client()
        response = await client.post(url, json=payload)

        if response.status_code == 200:
            return response.json()

        # 分类错误
        error_class = TelegramErrorClassifier.classify(
            Exception(f"HTTP {response.status_code}"), response.status_code
        )

        error_text = f"HTTP {response.status_code}: {response.text[:500]}"
        raise error_class(error_text)

    except (RetryableError, NonRetryableError):
        raise
    except Exception as e:
        # 分类未知错误
        error_class = TelegramErrorClassifier.classify(e)
        raise error_class(f"{type(e).__name__}: {str(e)}")


async def send_telegram_message(
    text: str,
    notification_type: NotificationType = NotificationType.INFO,
    max_retries: Optional[int] = None,
    use_queue: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    发送 Telegram 消息（带重试机制）

    Args:
        text: 消息内容
        notification_type: 通知类型
        max_retries: 最大重试次数（默认使用配置）
        use_queue: 是否使用消息队列（批量发送场景）
        metadata: 附加元数据

    Returns:
        发送结果 {
            "success": bool,
            "message_id": Optional[str],
            "error": Optional[str],
            "retry_count": int,
            "fallback": bool,
        }
    """
    max_retries = max_retries or settings.TG_MAX_RETRIES

    # 检查配置
    if not settings.TG_BOT_TOKEN or not settings.TG_CHAT_ID:
        logger.debug("[Telegram] 未配置，跳过发送")
        return {
            "success": False,
            "message_id": None,
            "error": "Telegram 未配置",
            "retry_count": 0,
            "fallback": False,
        }

    # 如果使用队列，直接入队
    if use_queue and settings.TG_ENABLE_QUEUE:
        queue = _get_message_queue()
        await queue.start()
        await queue.put(
            {
                "text": text,
                "type": notification_type,
                "metadata": metadata,
            }
        )
        return {
            "success": True,
            "message_id": None,
            "error": None,
            "retry_count": 0,
            "fallback": False,
            "queued": True,
        }

    # 直接发送，带重试
    last_error = None

    for attempt in range(max_retries):
        try:
            result = await _send_telegram_raw(text)

            # 记录成功
            if settings.TG_LOG_SUCCESS:
                await _log_to_database(
                    content=text,
                    notification_type=notification_type,
                    status=NotificationStatus.SENT,
                    retry_count=attempt,
                    metadata=metadata,
                )

            message_id = result.get("result", {}).get("message_id")
            logger.info(f"[Telegram] 发送成功 (尝试 {attempt + 1}/{max_retries})")

            return {
                "success": True,
                "message_id": str(message_id) if message_id else None,
                "error": None,
                "retry_count": attempt,
                "fallback": False,
            }

        except NonRetryableError as e:
            # 不可重试错误，直接失败
            last_error = str(e)
            logger.error(f"[Telegram] 不可重试错误: {e}")
            break

        except RetryableError as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                wait_time = _get_backoff_time(attempt, settings.TG_RETRY_BASE_DELAY)
                logger.warning(
                    f"[Telegram] 发送失败（尝试 {attempt + 1}/{max_retries}），"
                    f"{wait_time}s 后重试: {e}"
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"[Telegram] 最终失败（已重试 {max_retries} 次）: {e}")

    # 所有重试失败，记录到 fallback
    await _log_to_database(
        content=text,
        notification_type=notification_type,
        status=NotificationStatus.FAILED,
        error_msg=last_error or "Unknown error",
        retry_count=max_retries,
        metadata=metadata,
    )

    # 降级到日志
    logger.error(
        f"[Telegram] 消息发送失败，已记录到数据库\n"
        f"内容: {text[:200]}...\n"
        f"错误: {last_error}"
    )

    return {
        "success": False,
        "message_id": None,
        "error": last_error,
        "retry_count": max_retries,
        "fallback": True,
    }


async def send_trade_signal(
    symbol: str, signal: str, confidence: float, price: float, reason: str = ""
) -> Dict[str, Any]:
    """发送交易信号通知（便捷方法）"""
    text = (
        f"🚀 <b>钢子出击 - 交易信号</b>\n"
        f"\n"
        f"📊 交易对: <code>{symbol}</code>\n"
        f"📈 信号: <b>{signal}</b>\n"
        f"🎯 置信度: {confidence:.1f}%\n"
        f"💰 当前价格: ${price:.2f}\n"
    )
    if reason:
        text += f"\n📝 理由:\n{reason[:500]}"

    return await send_telegram_message(
        text=text,
        notification_type=NotificationType.TRADE_SIGNAL,
        metadata={
            "symbol": symbol,
            "signal": signal,
            "confidence": confidence,
            "price": price,
        },
    )


async def send_price_alert(
    symbol: str,
    alert_type: str,
    current_price: float,
    target_price: float,
) -> Dict[str, Any]:
    """发送价格预警通知（便捷方法）"""
    text = (
        f"⚠️ <b>价格预警 - {symbol}</b>\n"
        f"\n"
        f"类型: {alert_type}\n"
        f"当前价格: ${current_price:.2f}\n"
        f"目标价格: ${target_price:.2f}\n"
    )

    return await send_telegram_message(
        text=text,
        notification_type=NotificationType.PRICE_ALERT,
        metadata={
            "symbol": symbol,
            "alert_type": alert_type,
            "current_price": current_price,
            "target_price": target_price,
        },
    )


async def send_system_alert(
    title: str, message: str, level: str = "warning"
) -> Dict[str, Any]:
    """发送系统预警通知（便捷方法）"""
    icons = {
        "info": "ℹ️",
        "warning": "⚠️",
        "error": "🔴",
        "critical": "🚨",
    }
    icon = icons.get(level, "⚠️")

    text = (
        f"{icon} <b>系统预警 - {title}</b>\n\n级别: {level.upper()}\n\n{message[:1000]}"
    )

    return await send_telegram_message(
        text=text,
        notification_type=NotificationType.SYSTEM_ALERT,
        metadata={"level": level, "title": title},
    )


async def start_notification_service():
    """启动通知服务（包括消息队列）"""
    if settings.TG_ENABLE_QUEUE:
        queue = _get_message_queue()

        # 添加队列处理器
        async def queue_handler(message: Dict[str, Any]):
            await send_telegram_message(
                text=message["text"],
                notification_type=message.get("type", NotificationType.INFO),
                metadata=message.get("metadata"),
            )

        queue.add_handler(queue_handler)
        await queue.start()


async def stop_notification_service():
    """停止通知服务"""
    global _message_queue
    if _message_queue:
        await _message_queue.stop()
        _message_queue = None

    await close_tg_client()


async def close_tg_client():
    """关闭 Telegram HTTP 客户端"""
    global _tg_client
    if _tg_client and not _tg_client.is_closed:
        await _tg_client.aclose()
        _tg_client = None


# 向后兼容的别名
send_message = send_telegram_message
