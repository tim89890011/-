"""
钢子出击 - 全局错误处理中间件
提供统一的错误响应格式、请求上下文追踪和异常处理
"""
# pyright: reportMissingImports=false

import time
from typing import Any, Callable, Awaitable
from fastapi import Request, Response, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Scope, Receive, Send

from ..utils.logger import (
    get_logger,
    set_request_id,
    set_user,
    get_request_id,
    clear_context,
)
from ..exceptions import (
    BusinessException,
    ErrorCode,
)


logger = get_logger("backend.middleware")


async def _noop_asgi(scope: Scope, receive: Receive, send: Send) -> None:
    return None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    请求上下文中间件

    功能：
    1. 为每个请求生成唯一的 request_id
    2. 从请求中提取用户信息
    3. 记录请求耗时
    4. 清理请求上下文
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # 生成或获取请求 ID
        request_id = request.headers.get("X-Request-ID")
        request_id = set_request_id(request_id)

        # 尝试从请求中获取用户信息
        user = "anonymous"
        try:
            # 从 JWT token 中解析用户（如果存在）
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                # 这里可以添加 JWT 解码逻辑获取用户名
                # 暂时使用 token 的前 8 位作为标识
                user = f"token_{token[:8]}"
        except Exception as e:
            logger.debug("[中间件] 请求用户解析失败: %s", e)

        set_user(user)

        # 记录请求开始
        start_time = time.time()
        path = request.url.path
        method = request.method

        # 跳过静态文件的日志
        skip_logging = any(
            path.startswith(prefix)
            for prefix in ["/css/", "/js/", "/images/", "/assets/", "/favicon"]
        )

        if not skip_logging:
            logger.debug(
                f"请求开始: {method} {path}",
                extra={
                    "context": {
                        "client_ip": request.client.host
                        if request.client
                        else "unknown"
                    }
                },
            )

        try:
            response = await call_next(request)

            # 添加请求 ID 到响应头
            response.headers["X-Request-ID"] = request_id

            if not skip_logging:
                duration_ms = (time.time() - start_time) * 1000
                logger.debug(
                    f"请求完成: {method} {path} - {response.status_code}",
                    extra={
                        "context": {
                            "status_code": response.status_code,
                            "duration_ms": round(duration_ms, 2),
                        }
                    },
                )

            return response

        finally:
            # 清理上下文
            clear_context()


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    全局错误处理中间件

    功能：
    1. 捕获所有未处理的异常
    2. 统一错误响应格式
    3. 错误分类和映射
    4. 敏感信息过滤
    5. 详细的错误日志记录
    """

    # 敏感信息字段（会在日志中过滤）
    SENSITIVE_FIELDS = {
        "password",
        "token",
        "secret",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "session",
        "credit_card",
    }

    # 不需要记录详细日志的路径
    SKIP_LOG_PATHS = {"/health", "/metrics"}

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            return await call_next(request)

        except BusinessException as exc:
            # 业务异常已处理好响应格式
            return self._handle_business_exception(request, exc)

        except RequestValidationError as exc:
            # 请求参数验证错误
            return self._handle_validation_error(request, exc)

        except HTTPException as exc:
            # FastAPI HTTP 异常
            return self._handle_http_exception(request, exc)

        except Exception as exc:
            # 未处理的异常
            return self._handle_unknown_exception(request, exc)

    def _handle_business_exception(
        self, request: Request, exc: BusinessException
    ) -> JSONResponse:
        """处理业务异常"""
        path = request.url.path

        # 构建响应
        response_data = {
            "success": False,
            "code": exc.code,
            "message": exc.message,
            "request_id": get_request_id(),
        }

        # 添加字段错误信息（如果有）
        exc_any: Any = exc
        field_errors = getattr(exc_any, "field_errors", None)
        if field_errors:
            response_data["field_errors"] = field_errors

        # 记录日志（根据错误级别）
        log_context = {
            "path": path,
            "code": exc.code,
            **exc.context,
        }

        if exc.status_code >= 500:
            logger.error(
                f"业务异常: {exc.message}",
                extra={"context": log_context},
                exc_info=True,
            )
        elif exc.status_code == 429:  # Rate limit
            logger.warning(
                f"请求限流: {exc.message}",
                extra={"context": log_context},
            )
        else:
            logger.info(
                f"业务异常: {exc.message}",
                extra={"context": log_context},
            )

        headers = getattr(exc, "headers", None) or {}
        return JSONResponse(
            status_code=exc.status_code,
            content=response_data,
            headers=headers,
        )

    def _handle_validation_error(
        self, request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """处理参数验证错误"""
        path = request.url.path

        # 解析验证错误
        field_errors = {}
        error_messages = []

        for error in exc.errors():
            field = ".".join(str(loc) for loc in error.get("loc", []))
            msg = error.get("msg", "")
            error_type = error.get("type", "")

            if field:
                field_errors[field] = msg
            error_messages.append(f"{field}: {msg}" if field else msg)

        message = "请求参数无效"
        if error_messages:
            message = f"请求参数无效: {', '.join(error_messages[:3])}"

        # 记录日志（过滤敏感信息）
        body = self._filter_sensitive_body(exc.body)
        logger.info(
            f"参数验证失败: {message}",
            extra={
                "context": {
                    "path": path,
                    "field_errors": field_errors,
                    "body": body,
                }
            },
        )

        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "code": ErrorCode.INVALID_PARAMS,
                "message": message,
                "field_errors": field_errors,
                "request_id": get_request_id(),
            },
        )

    def _handle_http_exception(
        self, request: Request, exc: HTTPException
    ) -> JSONResponse:
        """处理 FastAPI HTTP 异常"""
        path = request.url.path

        # 将常见 HTTP 状态码映射到错误码
        code_mapping = {
            401: ErrorCode.UNAUTHORIZED,
            403: ErrorCode.FORBIDDEN,
            404: 4040,  # 资源不存在
            405: 4050,  # 方法不允许
            429: ErrorCode.RATE_LIMITED,
        }

        code = code_mapping.get(exc.status_code, ErrorCode.INTERNAL_ERROR)

        # 获取错误消息
        if isinstance(exc.detail, dict):
            message = exc.detail.get("message", exc.detail.get("detail", "请求错误"))
        else:
            message = str(exc.detail) if exc.detail else "请求错误"

        # 记录日志
        log_level = "warning" if exc.status_code < 500 else "error"
        getattr(logger, log_level)(
            f"HTTP 异常 {exc.status_code}: {message}",
            extra={"context": {"path": path, "code": code}},
        )

        response_data = {
            "success": False,
            "code": code,
            "message": message,
            "request_id": get_request_id(),
        }
        if isinstance(exc.detail, dict):
            response_data["detail"] = exc.detail

        return JSONResponse(
            status_code=exc.status_code,
            content=response_data,
            headers=exc.headers if hasattr(exc, "headers") else None,
        )

    def _handle_unknown_exception(
        self, request: Request, exc: Exception
    ) -> JSONResponse:
        """处理未知异常"""
        path = request.url.path
        request_id = get_request_id()

        # 生成错误追踪 ID（用于问题排查）
        error_trace_id = f"err_{request_id}"

        # 记录详细错误日志
        if path not in self.SKIP_LOG_PATHS:
            logger.critical(
                f"未处理异常: {str(exc)}",
                extra={
                    "context": {
                        "path": path,
                        "error_trace_id": error_trace_id,
                        "exception_type": type(exc).__name__,
                    }
                },
                exc_info=True,
            )

        # 返回统一的错误响应（不暴露内部细节）
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "code": ErrorCode.INTERNAL_ERROR,
                "message": f"服务器内部错误，请稍后重试。错误追踪 ID: {error_trace_id}",
                "request_id": request_id,
            },
        )

    def _filter_sensitive_body(self, body: Any) -> Any:
        """过滤请求体中的敏感信息"""
        if not isinstance(body, dict):
            return body

        filtered = {}
        for key, value in body.items():
            if any(sensitive in key.lower() for sensitive in self.SENSITIVE_FIELDS):
                filtered[key] = "***REDACTED***"
            elif isinstance(value, dict):
                filtered[key] = self._filter_sensitive_body(value)
            else:
                filtered[key] = value

        return filtered


# ============ 异常处理器（用于 app.add_exception_handler） ============


async def business_exception_handler(
    request: Request, exc: BusinessException
) -> JSONResponse:
    """业务异常处理器"""
    middleware = ErrorHandlerMiddleware(app=_noop_asgi)
    return middleware._handle_business_exception(request, exc)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """验证错误处理器"""
    middleware = ErrorHandlerMiddleware(app=_noop_asgi)
    return middleware._handle_validation_error(request, exc)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """HTTP 异常处理器"""
    middleware = ErrorHandlerMiddleware(app=_noop_asgi)
    return middleware._handle_http_exception(request, exc)


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局异常处理器"""
    middleware = ErrorHandlerMiddleware(app=_noop_asgi)
    return middleware._handle_unknown_exception(request, exc)
