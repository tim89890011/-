"""
分布式定时任务锁
多实例部署时，保证同一任务只在一个实例上执行。
基于 SQLite 行锁 + 过期时间实现。
"""

import time
import logging
from sqlalchemy import text

from backend.database.db import async_session

logger = logging.getLogger(__name__)

# 锁的默认过期时间（秒），超过该时间视为死锁自动释放
DEFAULT_LOCK_TTL = 300


async def _ensure_lock_table():
    """确保 scheduler_locks 表存在"""
    async with async_session() as db:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS scheduler_locks (
                job_id   TEXT PRIMARY KEY,
                holder   TEXT NOT NULL,
                acquired_at REAL NOT NULL,
                ttl      REAL NOT NULL DEFAULT 300
            )
        """))
        await db.commit()


async def acquire_lock(job_id: str, holder: str = "default", ttl: float = DEFAULT_LOCK_TTL) -> bool:
    """
    尝试获取任务锁。

    Args:
        job_id: 任务唯一标识（如 "analyze_all_symbols"）
        holder: 持有者标识（如主机名或进程 ID）
        ttl: 锁的有效时间（秒），超过自动释放

    Returns:
        True 如果成功获取锁，False 如果锁已被其他实例持有
    """
    now = time.time()
    try:
        async with async_session() as db:
            # 尝试清理过期锁
            await db.execute(
                text("DELETE FROM scheduler_locks WHERE job_id = :jid AND (acquired_at + ttl) < :now"),
                {"jid": job_id, "now": now},
            )

            # 尝试插入锁（如果已存在则忽略）
            result = await db.execute(
                text("""
                    INSERT OR IGNORE INTO scheduler_locks (job_id, holder, acquired_at, ttl)
                    VALUES (:jid, :holder, :now, :ttl)
                """),
                {"jid": job_id, "holder": holder, "now": now, "ttl": ttl},
            )
            await db.commit()

            # rowcount == 1 表示插入成功（获取到锁）
            if result.rowcount == 1:
                return True

            # 锁已存在，检查是不是自己持有的
            row = await db.execute(
                text("SELECT holder FROM scheduler_locks WHERE job_id = :jid"),
                {"jid": job_id},
            )
            existing = row.scalar_one_or_none()
            return existing == holder

    except Exception as e:
        logger.warning(f"[调度锁] 获取锁 {job_id} 失败: {e}")
        # 获取锁失败时，允许执行（单实例场景下不阻塞）
        return True


async def release_lock(job_id: str, holder: str = "default") -> None:
    """释放任务锁"""
    try:
        async with async_session() as db:
            await db.execute(
                text("DELETE FROM scheduler_locks WHERE job_id = :jid AND holder = :holder"),
                {"jid": job_id, "holder": holder},
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"[调度锁] 释放锁 {job_id} 失败: {e}")


async def init_scheduler_locks():
    """初始化锁表（启动时调用）"""
    await _ensure_lock_table()
    # 清理所有旧锁（重启后旧实例的锁都无效）
    try:
        async with async_session() as db:
            await db.execute(text("DELETE FROM scheduler_locks"))
            await db.commit()
        logger.info("[调度锁] 锁表已初始化")
    except Exception as e:
        logger.warning(f"[调度锁] 初始化失败（不影响功能）: {e}")
