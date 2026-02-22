"""
钢子出击 - 定时任务
使用 APScheduler 管理所有定期执行的任务
集成配额管理，配额不足时自动降级
"""
import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

import socket

from backend.database.db import async_session
from backend.signal_engine.engine import generate_signal
from backend.ai_engine.signal_history import check_signal_accuracy
from backend.market.binance_ws import SYMBOLS
from backend.utils.quota import quota_manager
from backend.trading.executor import auto_trader
from backend.analytics.daily_snapshot import take_daily_snapshot
from backend.database.models import RevokedToken, RefreshToken, ChatMessage
from backend.scheduler.lock import acquire_lock, release_lock, init_scheduler_locks
from sqlalchemy import delete
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# 全局调度器
scheduler = AsyncIOScheduler()

# Phase B：测试验证阶段全币种 1 分钟，全量 AI 辩论，需并发 + 跳过机制防止堆积
CONCURRENT_LIMIT = 3  # 同时最多分析 N 个币种（可按机器/额度调整）
_in_flight: set[str] = set()
_in_flight_lock = asyncio.Lock()

# 分布式锁持有者标识（主机名:PID）
_LOCK_HOLDER = f"{socket.gethostname()}:{__import__('os').getpid()}"


async def _analyze_single(symbol: str, label: str, semaphore: asyncio.Semaphore):
    """单个币种分析（带信号量控制）"""
    async with _in_flight_lock:
        if symbol in _in_flight:
            logger.info(f"[定时] {label} {symbol} 上轮分析未完成，跳过")
            return
        _in_flight.add(symbol)

    async with semaphore:
        try:
            async with async_session() as db:
                await generate_signal(symbol, db)
                logger.info(f"[定时] {label} {symbol} 分析完成")
        except Exception as e:
            logger.error(f"[定时] {label} {symbol} 分析失败: {e}")
        finally:
            async with _in_flight_lock:
                _in_flight.discard(symbol)


async def _analyze_symbols(symbols: list, label: str):
    """分析一组币种（并发）"""
    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
    tasks = [_analyze_single(sym, label, semaphore) for sym in symbols]
    await asyncio.gather(*tasks, return_exceptions=True)


async def task_analyze_all_symbols():
    """每 1 分钟：分析所有币种（测试验证阶段）"""
    # 分布式锁：多实例部署时只允许一个实例执行
    if not await acquire_lock("analyze_all_symbols", _LOCK_HOLDER, ttl=120):
        logger.debug("[定时] 分析任务被其他实例持有，跳过")
        return
    try:
        # 配额检查
        if quota_manager.should_skip_scheduled_analysis():
            logger.warning("[定时] 配额接近耗尽，跳过所有币种分析")
            return
        await _analyze_symbols(SYMBOLS, "所有币种")
    finally:
        await release_lock("analyze_all_symbols", _LOCK_HOLDER)


async def task_check_1h():
    """每 1 小时：检查 1h 前信号准确性"""
    try:
        async with async_session() as db:
            count = await check_signal_accuracy(db, hours=1)
            logger.info(f"[定时] 1h 信号检查完成，检查了 {count} 条")
    except Exception as e:
        logger.error(f"[定时] 1h 信号检查失败: {e}")


async def task_check_4h():
    """每 4 小时：检查 4h 前信号准确性"""
    try:
        async with async_session() as db:
            count = await check_signal_accuracy(db, hours=4)
            logger.info(f"[定时] 4h 信号检查完成，检查了 {count} 条")
    except Exception as e:
        logger.error(f"[定时] 4h 信号检查失败: {e}")


async def task_check_24h():
    """每 24 小时：检查 24h 前信号准确性"""
    try:
        async with async_session() as db:
            count = await check_signal_accuracy(db, hours=24)
            logger.info(f"[定时] 24h 信号检查完成，检查了 {count} 条")
    except Exception as e:
        logger.error(f"[定时] 24h 信号检查失败: {e}")


async def task_check_tp_sl():
    """每 30 秒：检查止盈止损（含移动止盈）"""
    try:
        await auto_trader.check_stop_loss_take_profit()
    except Exception as e:
        logger.error(f"[定时] 止盈止损检查失败: {e}")


async def task_check_position_timeout():
    """每 10 分钟：检查持仓超时（超过24h无盈利自动平仓）"""
    try:
        await auto_trader.check_position_timeout()
    except Exception as e:
        logger.error(f"[定时] 持仓超时检查失败: {e}")


async def task_daily_snapshot():
    """每日 23:55 UTC：记录 DailyPnL 快照"""
    if not await acquire_lock("daily_snapshot", _LOCK_HOLDER, ttl=600):
        logger.debug("[定时] 快照任务被其他实例持有，跳过")
        return
    try:
        async with async_session() as db:
            row = await take_daily_snapshot(db)
            logger.info(f"[定时] DailyPnL 快照已记录 date={row.date} equity={row.total_equity}")
    except Exception as e:
        logger.error(f"[定时] DailyPnL 快照失败: {e}")
    finally:
        await release_lock("daily_snapshot", _LOCK_HOLDER)


async def task_cleanup_expired_records():
    """每小时：清理过期 token / 过老聊天记录，避免表无限增长"""
    try:
        now = datetime.now(timezone.utc)
        chat_cutoff = now - timedelta(days=90)
        async with async_session() as db:
            await db.execute(delete(RevokedToken).where(RevokedToken.expires_at < now))
            await db.execute(
                delete(RefreshToken).where(RefreshToken.expires_at < now)
            )
            await db.execute(delete(ChatMessage).where(ChatMessage.created_at < chat_cutoff))
            await db.commit()
        logger.info("[定时] 过期记录清理完成")
    except Exception as e:
        logger.error(f"[定时] 过期记录清理失败: {e}")


def start_scheduler():
    """启动定时调度器"""
    from datetime import datetime, timedelta

    # 初始化分布式锁表
    asyncio.get_event_loop().create_task(init_scheduler_locks())

    # #55 修复：首次启动 30 秒后立即执行一次分析
    scheduler.add_job(
        task_analyze_all_symbols,
        IntervalTrigger(minutes=1),
        id="analyze_all_symbols",
        name="分析所有币种",
        replace_existing=True,
        next_run_time=datetime.now() + timedelta(seconds=15),
        max_instances=1,
    )

    # 每 1 小时检查信号准确性
    scheduler.add_job(
        task_check_1h,
        IntervalTrigger(hours=1),
        id="check_1h",
        name="检查1h信号",
        replace_existing=True,
        max_instances=1,
    )

    # 每 4 小时检查信号准确性
    scheduler.add_job(
        task_check_4h,
        IntervalTrigger(hours=4),
        id="check_4h",
        name="检查4h信号",
        replace_existing=True,
        max_instances=1,
    )

    # 每 24 小时检查信号准确性
    scheduler.add_job(
        task_check_24h,
        IntervalTrigger(hours=24),
        id="check_24h",
        name="检查24h信号",
        replace_existing=True,
        max_instances=1,
    )

    # 每 30 秒检查止盈止损（3x 杠杆下价格变动快，需高频检查）
    scheduler.add_job(
        task_check_tp_sl,
        IntervalTrigger(seconds=3),
        id="check_tp_sl",
        name="止盈止损检查",
        replace_existing=True,
        next_run_time=datetime.now() + timedelta(seconds=15),
        max_instances=1,
    )

    # 每 10 分钟检查持仓超时（24h 无盈利自动平仓）
    scheduler.add_job(
        task_check_position_timeout,
        IntervalTrigger(minutes=10),
        id="check_position_timeout",
        name="持仓超时检查",
        replace_existing=True,
        max_instances=1,
    )

    # 每日快照（UTC）
    scheduler.add_job(
        task_daily_snapshot,
        CronTrigger(hour=23, minute=55),
        id="daily_snapshot",
        name="DailyPnL快照",
        replace_existing=True,
        max_instances=1,
    )

    # 过期记录清理
    scheduler.add_job(
        task_cleanup_expired_records,
        IntervalTrigger(hours=1),
        id="cleanup_expired_records",
        name="过期记录清理",
        replace_existing=True,
        next_run_time=datetime.now() + timedelta(seconds=30),
        max_instances=1,
    )

    scheduler.start()
    logger.info(f"[定时] 调度器已启动，已注册 {len(scheduler.get_jobs())} 个定时任务")

    # 打印任务列表
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.name} (ID: {job.id})")


def stop_scheduler():
    """停止定时调度器"""
    if scheduler.running:
        scheduler.shutdown(wait=True)  # #38 修复：等待正在执行的任务完成
        logger.info("[定时] 调度器已停止")
