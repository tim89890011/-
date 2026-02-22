"""
钢子出击 - 自定义异常类
统一异常体系，支持错误码、错误消息和上下文信息
"""
from typing import Any, Optional
from fastapi import HTTPException


class ErrorCode:
    """错误码定义"""
    # 系统错误 1000-1099
    INTERNAL_ERROR = 1000
    SERVICE_UNAVAILABLE = 1001
    
    # 参数错误 2000-2099
    INVALID_PARAMS = 2000
    MISSING_PARAMS = 2001
    
    # 认证错误 3000-3099
    UNAUTHORIZED = 3000
    FORBIDDEN = 3001
    TOKEN_EXPIRED = 3002
    
    # 业务错误 4000-4099
    RATE_LIMITED = 4000
    QUOTA_EXCEEDED = 4001
    ANALYSIS_FAILED = 4002
    
    # 外部服务错误 5000-5099
    EXTERNAL_API_ERROR = 5000
    BINANCE_WS_ERROR = 5001
    DEEPSEEK_ERROR = 5002


# 错误码到 HTTP 状态码的映射
ERROR_CODE_TO_HTTP_STATUS = {
    # 系统错误
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.SERVICE_UNAVAILABLE: 503,
    
    # 参数错误
    ErrorCode.INVALID_PARAMS: 400,
    ErrorCode.MISSING_PARAMS: 400,
    
    # 认证错误
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.TOKEN_EXPIRED: 401,
    
    # 业务错误
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.QUOTA_EXCEEDED: 429,
    ErrorCode.ANALYSIS_FAILED: 422,
    
    # 外部服务错误
    ErrorCode.EXTERNAL_API_ERROR: 502,
    ErrorCode.BINANCE_WS_ERROR: 502,
    ErrorCode.DEEPSEEK_ERROR: 502,
}


# 错误码到默认错误消息的映射
ERROR_CODE_TO_MESSAGE = {
    # 系统错误
    ErrorCode.INTERNAL_ERROR: "服务器内部错误，请稍后重试",
    ErrorCode.SERVICE_UNAVAILABLE: "服务暂时不可用，请稍后重试",
    
    # 参数错误
    ErrorCode.INVALID_PARAMS: "请求参数无效",
    ErrorCode.MISSING_PARAMS: "缺少必要的请求参数",
    
    # 认证错误
    ErrorCode.UNAUTHORIZED: "未授权，请先登录",
    ErrorCode.FORBIDDEN: "无权访问该资源",
    ErrorCode.TOKEN_EXPIRED: "登录已过期，请重新登录",
    
    # 业务错误
    ErrorCode.RATE_LIMITED: "请求过于频繁，请稍后重试",
    ErrorCode.QUOTA_EXCEEDED: "API 配额已用完，请联系管理员",
    ErrorCode.ANALYSIS_FAILED: "AI 分析失败，请稍后重试",
    
    # 外部服务错误
    ErrorCode.EXTERNAL_API_ERROR: "外部服务调用失败",
    ErrorCode.BINANCE_WS_ERROR: "币安行情服务异常",
    ErrorCode.DEEPSEEK_ERROR: "DeepSeek AI 服务异常",
}


class BusinessException(HTTPException):
    """
    业务异常基类
    
    特点：
    1. 支持错误码和错误消息
    2. 支持上下文信息（用于日志记录）
    3. 自动映射到 HTTP 状态码
    4. 敏感信息过滤
    """
    
    # 需要过滤的敏感字段
    SENSITIVE_FIELDS = {"password", "token", "secret", "api_key", "apikey", "authorization"}
    
    def __init__(
        self,
        code: int = ErrorCode.INTERNAL_ERROR,
        message: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ):
        self.code = code
        self.message = message or ERROR_CODE_TO_MESSAGE.get(code, "未知错误")
        self.context = self._filter_sensitive(context or {})
        
        # 自动获取 HTTP 状态码
        status_code = ERROR_CODE_TO_HTTP_STATUS.get(code, 500)
        
        super().__init__(
            status_code=status_code,
            detail={
                "code": code,
                "message": self.message,
            },
            headers=headers,
        )
    
    def _filter_sensitive(self, context: dict[str, Any]) -> dict[str, Any]:
        """过滤敏感信息"""
        filtered = {}
        for key, value in context.items():
            if any(sensitive in key.lower() for sensitive in self.SENSITIVE_FIELDS):
                filtered[key] = "***REDACTED***"
            else:
                filtered[key] = value
        return filtered
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式（用于日志）"""
        return {
            "code": self.code,
            "message": self.message,
            "status_code": self.status_code,
            "context": self.context,
        }


class ValidationException(BusinessException):
    """参数校验异常"""
    
    def __init__(
        self,
        message: str = "请求参数无效",
        context: Optional[dict[str, Any]] = None,
        field_errors: Optional[dict[str, str]] = None,
    ):
        super().__init__(
            code=ErrorCode.INVALID_PARAMS,
            message=message,
            context=context,
        )
        self.field_errors = field_errors or {}
    
    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["field_errors"] = self.field_errors
        return result


class ExternalServiceException(BusinessException):
    """外部服务调用异常"""
    
    def __init__(
        self,
        service_name: str,
        message: Optional[str] = None,
        code: int = ErrorCode.EXTERNAL_API_ERROR,
        context: Optional[dict[str, Any]] = None,
        original_error: Optional[Exception] = None,
    ):
        self.service_name = service_name
        self.original_error = original_error
        
        default_message = f"{service_name} 服务调用失败"
        
        super().__init__(
            code=code,
            message=message or default_message,
            context=context,
        )
    
    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["service_name"] = self.service_name
        if self.original_error:
            result["original_error"] = str(self.original_error)
        return result


class QuotaExceededException(BusinessException):
    """配额超限异常"""
    
    def __init__(
        self,
        quota_type: str = "api",
        current_usage: int = 0,
        limit: int = 0,
        context: Optional[dict[str, Any]] = None,
    ):
        self.quota_type = quota_type
        self.current_usage = current_usage
        self.limit = limit
        
        message = f"{quota_type} 配额已用完 ({current_usage}/{limit})"
        
        merged_context = {
            "quota_type": quota_type,
            "current_usage": current_usage,
            "limit": limit,
            **(context or {}),
        }
        
        super().__init__(
            code=ErrorCode.QUOTA_EXCEEDED,
            message=message,
            context=merged_context,
        )


class UnauthorizedException(BusinessException):
    """未授权异常"""
    
    def __init__(
        self,
        message: str = "未授权，请先登录",
        context: Optional[dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.UNAUTHORIZED,
            message=message,
            context=context,
        )


class ForbiddenException(BusinessException):
    """禁止访问异常"""
    
    def __init__(
        self,
        message: str = "无权访问该资源",
        context: Optional[dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.FORBIDDEN,
            message=message,
            context=context,
        )


class RateLimitException(BusinessException):
    """请求频率限制异常"""
    
    def __init__(
        self,
        retry_after: Optional[int] = None,
        message: str = "请求过于频繁，请稍后重试",
        context: Optional[dict[str, Any]] = None,
    ):
        self.retry_after = retry_after
        headers = {}
        if retry_after:
            headers["Retry-After"] = str(retry_after)
        
        merged_context = {
            "retry_after": retry_after,
            **(context or {}),
        }
        
        super().__init__(
            code=ErrorCode.RATE_LIMITED,
            message=message,
            context=merged_context,
            headers=headers,
        )


class AIAnalysisException(BusinessException):
    """AI 分析异常"""
    
    def __init__(
        self,
        message: str = "AI 分析失败",
        symbol: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        original_error: Optional[Exception] = None,
    ):
        self.symbol = symbol
        self.original_error = original_error
        
        merged_context = {
            "symbol": symbol,
            **(context or {}),
        }
        
        super().__init__(
            code=ErrorCode.ANALYSIS_FAILED,
            message=message,
            context=merged_context,
        )


class DatabaseException(BusinessException):
    """数据库操作异常"""
    
    def __init__(
        self,
        operation: str = "query",
        message: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        original_error: Optional[Exception] = None,
    ):
        self.operation = operation
        self.original_error = original_error
        
        default_message = f"数据库{operation}操作失败"
        
        merged_context = {
            "operation": operation,
            **(context or {}),
        }
        
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            message=message or default_message,
            context=merged_context,
        )
