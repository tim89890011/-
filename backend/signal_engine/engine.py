"""
Phase B: 信号引擎统一入口

测试验证阶段：保持 AI 全量辩论为“决策主线”，pre-filter 仅做影子记录。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession


async def generate_signal(symbol: str, db: Optional[AsyncSession] = None) -> dict:
    # 目前复用现有 debate.run_debate，但它会在内部注入/持久化 pre-filter 字段
    from backend.ai_engine.debate import run_debate

    return await run_debate(symbol, db)

