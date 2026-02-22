"""
钢子出击 - AI 聊天处理
管理对话上下文，注入市场数据，调用 DeepSeek V3
"""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from backend.database.models import ChatMessage, AISignal
from backend.ai_engine.deepseek_client import deepseek_client
from backend.market.binance_ws import get_live_prices

logger = logging.getLogger(__name__)

# 系统提示词
CHAT_SYSTEM_PROMPT = """你是"钢子出击"量化交易系统的 AI 助手。你精通加密货币市场分析和交易策略。

你的特点：
- 说话风格：专业但不枯燥，偶尔带点幽默
- 回答长度：简洁有力，通常 2-5 句话
- 当用户问市场情况时，参考提供的实时数据
- 当用户问交易建议时，参考最新 AI 信号
- 不鼓励过度交易，强调风控
- 用中文回复

你可以聊的话题：市场分析、交易策略、技术指标解读、风控建议、加密货币知识科普。
"""


def _build_context(prices: dict, latest_signal: Optional[dict]) -> str:
    """构建实时上下文信息"""
    lines = ["[当前市场数据]"]

    # 价格
    if prices:
        for sym, info in list(prices.items())[:5]:
            price = info.get("price", 0)
            change = info.get("change_24h", 0)
            direction = "↑" if change > 0 else "↓" if change < 0 else "→"
            lines.append(f"{sym}: {price} ({direction}{abs(change):.2f}%)")
    else:
        lines.append("价格数据加载中...")

    # 最新信号
    if latest_signal:
        lines.append(f"\n[最新AI信号] {latest_signal.get('symbol', 'N/A')}: "
                      f"{latest_signal.get('signal', 'N/A')} "
                      f"(置信度 {latest_signal.get('confidence', 0)}%)")

    return "\n".join(lines)


async def chat_with_ai(
    user_id: int,
    message: str,
    db: AsyncSession,
) -> str:
    """
    处理用户聊天消息
    加载上下文 + 市场数据 + 最新信号 -> DeepSeek V3 -> 保存记录
    """
    # 1. 保存用户消息
    user_msg = ChatMessage(user_id=user_id, role="user", content=message)
    db.add(user_msg)
    await db.flush()

    # 2. 加载最近 10 条历史
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .order_by(desc(ChatMessage.id))
        .limit(10)
    )
    history = list(reversed(result.scalars().all()))

    # 3. 获取实时市场数据
    prices = get_live_prices()

    # 4. 获取最新 AI 信号
    sig_result = await db.execute(
        select(AISignal).order_by(desc(AISignal.created_at)).limit(1)
    )
    latest_signal_db = sig_result.scalar_one_or_none()
    latest_signal = None
    if latest_signal_db:
        latest_signal = {
            "symbol": latest_signal_db.symbol,
            "signal": latest_signal_db.signal,
            "confidence": latest_signal_db.confidence,
        }

    # 5. 构建消息列表
    context = _build_context(prices, latest_signal)
    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT + f"\n\n{context}"},
    ]

    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})

    # 6. 调用 DeepSeek V3
    ai_reply = await deepseek_client.chat(messages, temperature=0.8)

    # #10 修复：错误回复不存入数据库，避免污染上下文
    if ai_reply and not ai_reply.startswith("[错误]"):
        ai_msg = ChatMessage(user_id=user_id, role="assistant", content=ai_reply)
        db.add(ai_msg)
        await db.commit()
    else:
        # 回滚用户消息（不保存这轮失败的对话）
        await db.rollback()

    return ai_reply


async def get_chat_history(user_id: int, db: AsyncSession, limit: int = 50) -> list:
    """获取聊天历史"""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.id)
        .limit(limit)
    )
    messages = result.scalars().all()

    return [
        {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else "",
        }
        for msg in messages
    ]


async def clear_chat_history(user_id: int, db: AsyncSession) -> int:
    """清空聊天历史，返回删除条数"""
    from sqlalchemy import delete
    result = await db.execute(
        delete(ChatMessage).where(ChatMessage.user_id == user_id)
    )
    await db.commit()
    return result.rowcount
