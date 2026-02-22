"""
钢子出击 - FastAPI 主入口
量化交易信号系统核心服务
"""

import os
import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

# ============ 初始化日志系统（必须在其他导入之前） ============
from backend.utils.logger import init_logging, get_logger

init_logging()
logger = get_logger(__name__)

# ============ 导入应用模块 ============
from backend.config import settings, BASE_DIR, validate_runtime_settings
from backend.database.db import init_db, close_db, async_session
from backend.auth.router import router as auth_router, ensure_admin_exists
from backend.market.router import router as market_router
from backend.market.binance_ws import (
    start_binance_ws,
    stop_binance_ws,
    set_price_trigger_callback,
)
from backend.market.data_collector import close_client as close_market_client
from backend.ai_engine.router import router as ai_router
from backend.ai_engine.debate import set_signal_broadcast_callback, set_trade_executor_callback
from backend.chat.router import router as chat_router
from backend.scheduler.tasks import start_scheduler, stop_scheduler
from backend.monitoring import health_router, metrics_router
from backend.monitoring.metrics import metrics_collector
from backend.reports.router import router as backtest_reports_router
from backend.trading.router import router as trade_router
from backend.trading.executor import auto_trader
from backend.trading.user_data_stream import (
    start_user_data_stream,
    stop_user_data_stream,
    set_callbacks as set_uds_callbacks,
)
from backend.settings.router import router as settings_router
from backend.analytics.router import router as analytics_router
from backend.signal_engine.price_trigger import PriceTrigger, TriggerConfig
from backend.signal_engine.engine import generate_signal
from backend.websocket import (
    broadcast_signal,
    broadcast_trade_status,
    broadcast_prices,
    health_check_logger,
    broadcast_order_update,
    broadcast_position_update,
    broadcast_balance_update,
    ws_router,
)

# ============ 导入错误处理 ============
from backend.middleware import RequestContextMiddleware, ErrorHandlerMiddleware
from backend.exceptions import BusinessException
from backend.middleware.error_handler import (
    business_exception_handler,
    validation_exception_handler,
    http_exception_handler,
    global_exception_handler,
)

# ============ 定时任务间隔 ============
ORPHAN_CLEANUP_INITIAL_DELAY_SECONDS = 5
ORPHAN_CLEANUP_INTERVAL_SECONDS = 300


# ============ 应用生命周期 ============
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的操作"""
    logger.info("=" * 50)
    logger.info("[钢子出击] 系统启动中...")

    background_tasks: list[asyncio.Task] = []

    try:
        # 0. 启动前配置校验（统一走日志系统输出）
        validate_runtime_settings(logger)

        # 1. 初始化数据库
        await init_db()
        logger.info("数据库初始化完成")

        # 1.5 从 DB 恢复当日配额计数（避免重启后归零）
        from backend.utils.quota import quota_manager
        await quota_manager.load_from_db()

        # 2. 创建管理员账号
        async with async_session() as db:
            await ensure_admin_exists(db)
        logger.info("管理员账号检查完成")

        # 3. 注入信号广播回调
        set_signal_broadcast_callback(broadcast_signal)
        logger.info("信号广播回调注入完成")

        # 3.5 初始化自动交易 & 注入交易回调
        await auto_trader.initialize()
        await auto_trader.restore_position_meta()
        set_trade_executor_callback(auto_trader.execute_signal)
        auto_trader._trade_status_broadcast_cb = broadcast_trade_status
        logger.info("自动交易模块初始化完成")

        # 4. 启动 Binance WebSocket
        await start_binance_ws()
        logger.info("Binance WebSocket 启动完成")

        # 4.1 启动 User Data Stream（持仓/余额/订单推送）
        async def _on_order_update(event: dict):
            """订单成交事件 → 广播给前端 + 通知 executor 匹配条件单"""
            await broadcast_order_update(event)
            try:
                await auto_trader.on_exchange_order_update(event)
            except Exception as e:
                logger.warning(f"[OrderUpdate] executor 处理订单事件异常: {e}")

        set_uds_callbacks(
            on_position=broadcast_position_update,
            on_balance=broadcast_balance_update,
            on_order=_on_order_update,
        )
        await start_user_data_stream()
        logger.info("User Data Stream 启动完成")

        # 4.5 注入价格波动触发器（可选补充触发）
        async def _analyze_from_trigger(symbol: str, reason: str) -> None:
            try:
                async with async_session() as db:
                    await generate_signal(symbol, db)
                logger.info(f"[触发器] {symbol} 触发分析 ({reason}) 完成")
            except Exception as e:
                logger.warning(f"[触发器] {symbol} 触发分析失败 ({reason}): {e}")

        _pt = PriceTrigger(_analyze_from_trigger, cfg=TriggerConfig())

        async def _pt_cb(symbol: str, price: float) -> None:
            await _pt.on_price(symbol, float(price))

        set_price_trigger_callback(_pt_cb)
        logger.info("价格波动触发器注入完成")

        # 5. 启动定时任务
        start_scheduler()
        logger.info("定时任务调度器启动完成")

        # 5.5 启动时清理孤儿条件单 + 定期巡检
        async def _orphan_cleanup_loop():
            await asyncio.sleep(ORPHAN_CLEANUP_INITIAL_DELAY_SECONDS)
            try:
                n = await auto_trader.cleanup_orphan_orders()
                logger.info(f"[启动清理] 孤儿条件单清理完成，取消 {n} 个")
            except Exception as e:
                logger.warning(f"[启动清理] 孤儿条件单清理异常: {e}")
            while True:
                await asyncio.sleep(ORPHAN_CLEANUP_INTERVAL_SECONDS)
                try:
                    await auto_trader.cleanup_orphan_orders()
                except Exception as e:
                    logger.warning(f"[定期清理] 孤儿条件单清理异常: {e}")

        background_tasks.append(asyncio.create_task(
            _orphan_cleanup_loop(), name="orphan_cleanup"
        ))

        # 6. 启动价格推送任务
        background_tasks.append(asyncio.create_task(
            broadcast_prices(), name="price_broadcast"
        ))

        # 7. 启动健康检查日志任务
        background_tasks.append(asyncio.create_task(
            health_check_logger(), name="health_check"
        ))

        logger.info("[钢子出击] 系统启动完成！")
        logger.info(f"[钢子出击] 访问 http://localhost:{settings.PORT}")
        logger.info("=" * 50)

        yield

    except Exception as e:
        logger.critical(f"系统启动失败: {e}", exc_info=True)
        raise

    finally:
        # 关闭
        logger.info("[钢子出击] 系统关闭中...")
        for task in background_tasks:
            task.cancel()
        if background_tasks:
            results = await asyncio.gather(*background_tasks, return_exceptions=True)
            for task, result in zip(background_tasks, results):
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    logger.warning("后台任务 %s 关闭异常: %s", task.get_name(), result)

        stop_scheduler()
        await stop_user_data_stream()
        await stop_binance_ws()
        await close_market_client()

        try:
            from backend.ai_engine.deepseek_client import deepseek_client

            await deepseek_client.close()
        except Exception as e:
            logger.warning(f"关闭 DeepSeek 客户端失败: {e}")

        try:
            from backend.notification.telegram_bot import close_tg_client

            await close_tg_client()
        except Exception as e:
            logger.warning(f"关闭 Telegram 客户端失败: {e}")

        try:
            await auto_trader.close()
        except Exception as e:
            logger.warning(f"关闭自动交易模块失败: {e}")

        await close_db()
        logger.info("[钢子出击] 系统已关闭")


# ============ 创建 FastAPI 应用 ============
app = FastAPI(
    title="钢子出击 - 量化交易系统",
    description="AI 驱动的加密货币量化交易信号平台",
    version="1.0.0",
    lifespan=lifespan,
)

# ============ 注册错误处理器（必须在其他中间件之前） ============
app.add_exception_handler(BusinessException, business_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# ============ 注册中间件（按执行顺序，自下而上） ============
# 1. 请求上下文中间件（最先执行）
app.add_middleware(RequestContextMiddleware)

# 2. 错误处理中间件
app.add_middleware(ErrorHandlerMiddleware)

# 3. CORS 中间件
_allowed_origins = [
    f"http://localhost:{settings.PORT}",
    f"http://127.0.0.1:{settings.PORT}",
    "http://localhost:3000",
]
if settings.ALLOWED_ORIGIN:
    _allowed_origins.append(settings.ALLOWED_ORIGIN)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ============ 注册 API 路由 ============
app.include_router(auth_router)
app.include_router(market_router)
app.include_router(ai_router)
app.include_router(chat_router)
app.include_router(trade_router)
app.include_router(settings_router)
app.include_router(analytics_router)
app.include_router(backtest_reports_router)
app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(ws_router)


# ============ 请求耗时中间件 ============
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """记录请求耗时和状态码"""
    start_time = time.time()

    # 跳过静态文件请求
    if request.url.path.startswith(
        ("/css/", "/js/", "/images/", "/assets/", "/favicon")
    ):
        return await call_next(request)

    try:
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000

        # 记录指标
        await metrics_collector.record_http_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            client_ip=request.client.host if request.client else "",
        )

        return response
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        # 记录异常请求
        await metrics_collector.record_http_request(
            method=request.method,
            path=request.url.path,
            status_code=500,
            duration_ms=duration_ms,
            client_ip=request.client.host if request.client else "",
        )
        raise


# ============ 静态文件挂载（必须最后） ============
frontend_dir = os.path.join(BASE_DIR, "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
