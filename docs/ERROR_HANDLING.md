# 钢子出击 - 错误处理文档

## 目录

1. [错误码定义](#错误码定义)
2. [异常类说明](#异常类说明)
3. [错误响应格式](#错误响应格式)
4. [使用示例](#使用示例)
5. [日志系统](#日志系统)
6. [最佳实践](#最佳实践)

---

## 错误码定义

### 系统错误 (1000-1099)

| 错误码 | 名称 | 说明 | HTTP 状态码 |
|--------|------|------|-------------|
| 1000 | `INTERNAL_ERROR` | 服务器内部错误 | 500 |
| 1001 | `SERVICE_UNAVAILABLE` | 服务暂时不可用 | 503 |

### 参数错误 (2000-2099)

| 错误码 | 名称 | 说明 | HTTP 状态码 |
|--------|------|------|-------------|
| 2000 | `INVALID_PARAMS` | 请求参数无效 | 400 |
| 2001 | `MISSING_PARAMS` | 缺少必要的请求参数 | 400 |

### 认证错误 (3000-3099)

| 错误码 | 名称 | 说明 | HTTP 状态码 |
|--------|------|------|-------------|
| 3000 | `UNAUTHORIZED` | 未授权，请先登录 | 401 |
| 3001 | `FORBIDDEN` | 无权访问该资源 | 403 |
| 3002 | `TOKEN_EXPIRED` | 登录已过期，请重新登录 | 401 |

### 业务错误 (4000-4099)

| 错误码 | 名称 | 说明 | HTTP 状态码 |
|--------|------|------|-------------|
| 4000 | `RATE_LIMITED` | 请求过于频繁，请稍后重试 | 429 |
| 4001 | `QUOTA_EXCEEDED` | API 配额已用完，请联系管理员 | 429 |
| 4002 | `ANALYSIS_FAILED` | AI 分析失败，请稍后重试 | 422 |

### 外部服务错误 (5000-5099)

| 错误码 | 名称 | 说明 | HTTP 状态码 |
|--------|------|------|-------------|
| 5000 | `EXTERNAL_API_ERROR` | 外部服务调用失败 | 502 |
| 5001 | `BINANCE_WS_ERROR` | 币安行情服务异常 | 502 |
| 5002 | `DEEPSEEK_ERROR` | DeepSeek AI 服务异常 | 502 |

---

## 异常类说明

### BusinessException

业务异常基类，所有自定义异常的父类。

```python
from backend.exceptions import BusinessException, ErrorCode

# 基本用法
raise BusinessException(
    code=ErrorCode.INTERNAL_ERROR,
    message="业务处理失败",
    context={"order_id": "12345"}  # 额外上下文信息
)
```

**特性：**
- 自动映射错误码到 HTTP 状态码
- 支持敏感信息自动过滤（password, token, secret 等）
- 提供统一的错误响应格式

### ValidationException

参数校验异常，用于处理请求参数错误。

```python
from backend.exceptions import ValidationException

raise ValidationException(
    message="参数校验失败",
    field_errors={
        "symbol": "交易对不能为空",
        "amount": "金额必须大于0"
    },
    context={"received_params": params}
)
```

### ExternalServiceException

外部服务调用异常。

```python
from backend.exceptions import ExternalServiceException, ErrorCode

raise ExternalServiceException(
    service_name="Binance API",
    code=ErrorCode.BINANCE_WS_ERROR,
    message="无法获取行情数据",
    context={"symbol": "BTCUSDT"},
    original_error=original_exception
)
```

### QuotaExceededException

API 配额超限异常。

```python
from backend.exceptions import QuotaExceededException

raise QuotaExceededException(
    quota_type="api",
    current_usage=10000,
    limit=10000
)
```

### 其他异常类

- `UnauthorizedException` - 未授权异常
- `ForbiddenException` - 禁止访问异常
- `RateLimitException` - 请求频率限制异常
- `AIAnalysisException` - AI 分析异常
- `DatabaseException` - 数据库操作异常

---

## 错误响应格式

### 标准错误响应

```json
{
  "success": false,
  "code": 4001,
  "message": "API 配额已用完 (10000/10000)",
  "request_id": "req_abc123def456"
}
```

### 带字段错误的响应（验证错误）

```json
{
  "success": false,
  "code": 2000,
  "message": "请求参数无效: symbol: 交易对不能为空",
  "field_errors": {
    "symbol": "交易对不能为空",
    "amount": "金额必须大于0"
  },
  "request_id": "req_def789ghi012"
}
```

### 服务器内部错误响应

```json
{
  "success": false,
  "code": 1000,
  "message": "服务器内部错误，请稍后重试。错误追踪 ID: err_req_xxx",
  "request_id": "req_xxx"
}
```

**注意：** 生产环境中，500 错误不会返回具体的异常详情，而是提供一个追踪 ID 用于问题排查。

---

## 使用示例

### 1. 在路由中抛出业务异常

```python
from fastapi import APIRouter, Depends
from backend.exceptions import (
    BusinessException, 
    ErrorCode,
    ValidationException,
    UnauthorizedException
)

router = APIRouter()

@router.post("/api/analyze")
async def analyze_symbol(
    symbol: str,
    current_user: User = Depends(get_current_user)
):
    # 参数校验
    if not symbol:
        raise ValidationException(
            message="交易对不能为空",
            field_errors={"symbol": "交易对不能为空"}
        )
    
    # 权限检查
    if not current_user.can_analyze:
        raise UnauthorizedException(
            message="您没有分析权限"
        )
    
    # 业务处理
    result = await perform_analysis(symbol)
    if not result:
        raise BusinessException(
            code=ErrorCode.ANALYSIS_FAILED,
            message="AI 分析失败，请稍后重试",
            context={"symbol": symbol}
        )
    
    return {"success": True, "data": result}
```

### 2. 使用 try-except 包装外部调用

```python
from backend.exceptions import ExternalServiceException, ErrorCode

async def fetch_binance_price(symbol: str):
    try:
        response = await http_client.get(f"https://api.binance.com/ticker/price?symbol={symbol}")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        raise ExternalServiceException(
            service_name="Binance API",
            code=ErrorCode.BINANCE_WS_ERROR,
            message=f"获取 {symbol} 价格失败",
            context={"symbol": symbol},
            original_error=e
        )
```

### 3. 检查配额

```python
from backend.exceptions import QuotaExceededException
from backend.utils.quota import quota_manager

async def check_quota_before_analysis(user_id: str):
    usage = await quota_manager.get_daily_usage(user_id)
    limit = await quota_manager.get_user_limit(user_id)
    
    if usage >= limit:
        raise QuotaExceededException(
            quota_type="analysis",
            current_usage=usage,
            limit=limit
        )
```

---

## 日志系统

### 日志配置

日志配置通过环境变量控制：

```bash
# 设置日志级别
LOG_LEVEL=INFO

# 启用 JSON 格式（生产环境建议开启）
LOG_JSON_FORMAT=true
```

### 日志文件结构

```
logs/
├── app.log          # 应用日志（按日期轮转）
├── app.log.2026-02-14  # 历史日志
├── error.log        # 错误日志（仅 ERROR 级别以上）
└── .gitignore       # 确保日志不提交到 Git
```

### 日志格式

#### 开发环境（控制台）

```
2026-02-15 10:30:00 [INFO] backend.ai_engine.debate: [req_abc123] AI 分析完成
```

#### 生产环境（JSON）

```json
{
  "timestamp": "2026-02-15T10:30:00+08:00",
  "level": "ERROR",
  "logger": "backend.ai_engine.debate",
  "request_id": "req_abc123def456",
  "user": "admin",
  "message": "AI analysis failed",
  "exception": "Traceback (most recent call last):...",
  "context": {
    "symbol": "BTCUSDT",
    "duration_ms": 5000
  }
}
```

### 使用日志器

```python
from backend.utils.logger import get_logger, log_with_context

# 获取日志器
logger = get_logger("backend.ai_engine")

# 基本用法
logger.info("处理开始")
logger.error("处理失败", exc_info=True)

# 带上下文的日志
logger.info(
    "AI 分析完成",
    extra={"context": {"symbol": "BTCUSDT", "duration_ms": 3000}}
)

# 使用便捷函数
log_with_context(
    logger,
    "warning",
    "配额即将用完",
    context={"usage": 8000, "limit": 10000}
)
```

### 请求上下文

```python
from backend.utils.logger import (
    set_request_id, 
    get_request_id,
    set_user,
    get_user,
    clear_context
)

# 设置请求 ID（通常在中间件中）
request_id = set_request_id()  # 自动生成
# 或
set_request_id("custom-request-id")

# 设置当前用户
set_user("admin")

# 获取当前上下文
print(get_request_id())  # req_xxx
print(get_user())        # admin

# 清理上下文（请求结束时）
clear_context()
```

### 性能日志装饰器

```python
from backend.utils.logger import get_logger, log_execution_time

logger = get_logger(__name__)

@log_execution_time(logger)
async def expensive_operation():
    # 耗时操作
    await asyncio.sleep(1)
    return result
```

---

## 最佳实践

### 1. 异常处理原则

- **不要捕获所有异常：** 只捕获你能处理的异常
- **不要吞掉异常：** 捕获后至少记录日志，或转换为业务异常
- **提供有用的上下文：** 在异常中包含足够的信息用于问题排查
- **避免暴露内部细节：** 生产环境不要返回堆栈跟踪给客户端

### 2. 日志记录原则

- **使用结构化日志：** 使用 `extra={"context": {...}}` 传递上下文
- **适当的日志级别：**
  - DEBUG：详细的调试信息
  - INFO：正常的业务流程
  - WARNING：需要注意但不会导致失败的情况
  - ERROR：操作失败但系统可以继续运行
  - CRITICAL：系统级错误，需要立即处理
- **不要记录敏感信息：** 密码、token 等会自动过滤

### 3. 错误码使用规范

- **系统错误 (1xxx)：** 服务器内部问题，用户无法解决
- **参数错误 (2xxx)：** 用户请求参数问题，需要修改请求
- **认证错误 (3xxx)：** 登录/权限问题，需要重新认证
- **业务错误 (4xxx)：** 业务规则限制，可以提示用户
- **外部服务错误 (5xxx)：** 依赖服务问题，通常是临时性的

### 4. 响应给客户端的消息

- **简洁明了：** 用户能看懂发生了什么
- **提供解决方案：** 告诉用户下一步可以做什么
- **避免技术术语：** 不要使用异常类名或堆栈跟踪

### 5. 监控和告警

建议配置以下告警：

- 5xx 错误率超过阈值
- 特定错误码（如配额超限）频繁出现
- 外部服务错误（5xxx）持续发生
- 响应时间异常

---

## 更新记录

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-02-15 | 1.0.0 | 初始版本，建立错误处理体系 |
