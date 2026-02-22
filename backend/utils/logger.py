"""
钢子出击 - 结构化日志配置
提供 JSON 格式的结构化日志，支持请求上下文追踪
"""

import json
import logging
import logging.handlers
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from contextvars import ContextVar

from backend.config import BASE_DIR


# ============ 请求上下文变量 ============
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_var: ContextVar[str] = ContextVar("user", default="anonymous")


# ============ 日志目录配置 ============
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


# ============ JSON 格式化器 ============
class JSONFormatter(logging.Formatter):
    """JSON 格式日志格式化器"""

    def __init__(self, include_exception: bool = True):
        super().__init__()
        self.include_exception = include_exception

    def format(self, record: logging.LogRecord) -> str:
        """将日志记录格式化为 JSON"""
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 添加请求上下文
        request_id = request_id_var.get()
        if request_id:
            log_data["request_id"] = request_id

        user = user_var.get()
        if user and user != "anonymous":
            log_data["user"] = user

        # 添加额外上下文（通过 extra 参数传入）
        if hasattr(record, "context") and record.context:
            log_data["context"] = record.context

        # 添加异常信息
        if self.include_exception and record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # 添加其他额外字段
        for key, value in record.__dict__.items():
            if key not in (
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "getMessage",
                "context",
                "timestamp",
                "message",
                "logger",
                "request_id",
                "user",
            ):
                log_data[key] = value

        return json.dumps(log_data, ensure_ascii=False, default=str)


class ColoredFormatter(logging.Formatter):
    """带颜色的控制台日志格式化器（开发环境使用）"""

    # ANSI 颜色代码
    COLORS = {
        "DEBUG": "\033[36m",  # 青色
        "INFO": "\033[32m",  # 绿色
        "WARNING": "\033[33m",  # 黄色
        "ERROR": "\033[31m",  # 红色
        "CRITICAL": "\033[35m",  # 紫色
        "RESET": "\033[0m",  # 重置
    }

    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None):
        super().__init__(fmt, datefmt)

    def format(self, record: logging.LogRecord) -> str:
        """添加颜色到日志级别"""
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = (
                f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"
            )

        # 添加请求 ID 到日志消息
        request_id = request_id_var.get()
        if request_id:
            record.msg = f"[{request_id[:8]}] {record.msg}"

        return super().format(record)


# ============ 日志配置类 ============
class LoggerConfig:
    """日志配置管理"""

    # 日志级别映射
    LEVELS = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    @classmethod
    def setup_logging(
        cls,
        level: str = "INFO",
        enable_json: bool = False,
        log_dir: Optional[str] = None,
    ) -> None:
        """
        配置全局日志

        Args:
            level: 日志级别
            enable_json: 是否启用 JSON 格式（生产环境建议开启）
            log_dir: 日志目录，默认使用 BASE_DIR/logs
        """
        log_dir = log_dir or LOG_DIR
        log_level = cls.LEVELS.get(level.upper(), logging.INFO)

        # 根日志配置
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)

        # 清除现有处理器
        root_logger.handlers.clear()

        # 控制台处理器（带颜色）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)

        if enable_json:
            console_handler.setFormatter(JSONFormatter())
        else:
            console_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            console_handler.setFormatter(ColoredFormatter(console_format))

        root_logger.addHandler(console_handler)

        # 按日期分割的日志文件处理器
        info_handler = logging.handlers.TimedRotatingFileHandler(
            filename=os.path.join(log_dir, "app.log"),
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        )
        info_handler.setLevel(logging.INFO)
        info_handler.setFormatter(JSONFormatter())
        info_handler.suffix = "%Y-%m-%d"
        root_logger.addHandler(info_handler)

        # 错误日志单独存储
        error_handler = logging.handlers.TimedRotatingFileHandler(
            filename=os.path.join(log_dir, "error.log"),
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(JSONFormatter())
        error_handler.suffix = "%Y-%m-%d"
        root_logger.addHandler(error_handler)

        # 设置第三方库的日志级别
        logging.getLogger("uvicorn").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("apscheduler").setLevel(logging.WARNING)

        # 记录启动信息
        logger = logging.getLogger(__name__)
        logger.info(
            "日志系统初始化完成",
            extra={"context": {"level": level, "json_format": enable_json}},
        )


# ============ 便捷的日志函数 ============
def get_logger(name: str) -> logging.Logger:
    """获取命名日志器"""
    return logging.getLogger(name)


def set_request_id(request_id: Optional[str] = None) -> str:
    """
    设置请求 ID

    Args:
        request_id: 请求 ID，如果不提供则自动生成

    Returns:
        设置的请求 ID
    """
    if request_id is None:
        request_id = f"req_{uuid.uuid4().hex[:16]}"
    request_id_var.set(request_id)
    return request_id


def get_request_id() -> str:
    """获取当前请求 ID"""
    return request_id_var.get()


def set_user(user: str) -> None:
    """设置当前用户"""
    user_var.set(user)


def get_user() -> str:
    """获取当前用户"""
    return user_var.get()


def mask_username(username: str) -> str:
    value = str(username or "")
    if len(value) <= 2:
        return "*" * len(value)
    if len(value) <= 4:
        return f"{value[0]}**{value[-1]}"
    return f"{value[:2]}***{value[-2:]}"


def mask_ip(ip: str) -> str:
    value = str(ip or "")
    parts = value.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.*.*"
    return "*"


def clear_context() -> None:
    """清除请求上下文"""
    request_id_var.set("")
    user_var.set("anonymous")


def log_with_context(
    logger: logging.Logger,
    level: str,
    message: str,
    context: Optional[dict[str, Any]] = None,
    exc_info: bool = False,
) -> None:
    """
    带上下文的日志记录

    Args:
        logger: 日志器
        level: 日志级别
        message: 日志消息
        context: 额外上下文信息
        exc_info: 是否包含异常信息
    """
    extra = {"context": context or {}}
    log_func = getattr(logger, level.lower())
    log_func(message, extra=extra, exc_info=exc_info)


# ============ 性能日志装饰器 ============
def log_execution_time(logger: Optional[logging.Logger] = None):
    """
    记录函数执行时间的装饰器

    Usage:
        @log_execution_time()
        async def my_function():
            pass
    """
    import functools
    import time

    def decorator(func):
        nonlocal logger
        if logger is None:
            logger = get_logger(func.__module__)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                logger.debug(
                    f"{func.__name__} 执行完成",
                    extra={"context": {"duration_ms": round(duration_ms, 2)}},
                )
                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"{func.__name__} 执行失败",
                    extra={
                        "context": {
                            "duration_ms": round(duration_ms, 2),
                            "error": str(e),
                        }
                    },
                    exc_info=True,
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                logger.debug(
                    f"{func.__name__} 执行完成",
                    extra={"context": {"duration_ms": round(duration_ms, 2)}},
                )
                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"{func.__name__} 执行失败",
                    extra={
                        "context": {
                            "duration_ms": round(duration_ms, 2),
                            "error": str(e),
                        }
                    },
                    exc_info=True,
                )
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# 导入 asyncio 用于判断协程函数
import asyncio


# ============ 初始化默认日志配置 ============
def init_logging():
    """初始化默认日志配置（应用启动时调用）"""
    # 从环境变量读取配置
    log_level = os.getenv("LOG_LEVEL", "INFO")
    enable_json = os.getenv("LOG_JSON_FORMAT", "false").lower() == "true"

    LoggerConfig.setup_logging(
        level=log_level,
        enable_json=enable_json,
    )


# 兼容性：保持原有接口
logger = get_logger("backend")
