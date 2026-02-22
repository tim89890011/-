"""
钢子出击 - 通知模块

提供多种通知渠道：
- Telegram（带重试机制）
- 语音通知
- 降级记录（数据库）

使用示例:
    from backend.notification import send_message, send_trade_signal
    
    # 发送普通消息
    result = await send_message("系统启动成功")
    
    # 发送交易信号
    result = await send_trade_signal(
        symbol="BTCUSDT",
        signal="BUY",
        confidence=85.5,
        price=45000.0,
        reason="突破阻力位"
    )
    
    # 检查发送结果
    if result["success"]:
        print(f"消息已发送，ID: {result['message_id']}")
    elif result["fallback"]:
        print(f"发送失败，已降级到数据库: {result['error']}")
"""

# 核心发送函数
from backend.notification.telegram_bot import (
    # 基础发送
    send_message,
    send_telegram_message,
    
    # 便捷方法
    send_trade_signal,
    send_price_alert,
    send_system_alert,
    
    # 类型定义
    NotificationType,
    NotificationStatus,
    RetryableError,
    NonRetryableError,
    
    # 生命周期管理
    start_notification_service,
    stop_notification_service,
    close_tg_client,
)

# 降级机制
from backend.notification.fallback import (
    # 管理器
    NotificationFallbackManager,
    get_fallback_manager,
    
    # 数据类
    NotificationSummary,
    NotificationDetail,
    
    # 便捷函数
    get_pending_notifications,
    retry_failed_notification,
    get_notification_stats,
    log_notification_failure,
)

# 语音通知（保持向后兼容）
try:
    from backend.notification.voice import play_voice, speak_text
except ImportError:
    # 语音依赖可能未安装
    pass

__all__ = [
    # 发送函数
    "send_message",
    "send_telegram_message",
    "send_trade_signal",
    "send_price_alert",
    "send_system_alert",
    
    # 类型
    "NotificationType",
    "NotificationStatus",
    "RetryableError",
    "NonRetryableError",
    
    # 服务管理
    "start_notification_service",
    "stop_notification_service",
    "close_tg_client",
    
    # 降级机制
    "NotificationFallbackManager",
    "get_fallback_manager",
    "NotificationSummary",
    "NotificationDetail",
    "get_pending_notifications",
    "retry_failed_notification",
    "get_notification_stats",
    "log_notification_failure",
    
    # 语音
    "play_voice",
    "speak_text",
]
