"""
钢子出击 - AI 聊天路由
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.auth.jwt_utils import get_current_user
from backend.database.db import get_db
from backend.database.models import User
from backend.chat.chat_handler import chat_with_ai, get_chat_history, clear_chat_history

router = APIRouter(prefix="/api/chat", tags=["AI 聊天"])


def _ok(payload: dict) -> dict:
    """统一响应格式：兼容旧字段 + 新增 success/data 包装。"""
    return {"success": True, "data": payload, **payload}


class ChatRequest(BaseModel):
    """聊天请求"""
    # #63 修复：限制消息长度，防止超长消息导致高额 API 费用
    message: str = Field(..., min_length=1, max_length=2000, description="聊天消息")


async def _get_user_id(username: str, db: AsyncSession) -> int:
    """通过 username 获取 user_id"""
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user.id


@router.post("/send")
async def send_message(
    req: ChatRequest,
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发送消息并获取 AI 回复"""
    user_id = await _get_user_id(username, db)

    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    reply = await chat_with_ai(user_id, req.message.strip(), db)
    return _ok({"reply": reply})


@router.get("/history")
async def get_history(
    limit: int = Query(default=50, ge=1, le=200),
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取聊天历史（#25 修复：limit 限制 1-200）"""
    user_id = await _get_user_id(username, db)
    messages = await get_chat_history(user_id, db, limit)
    return _ok({"messages": messages})


@router.delete("/clear")
async def clear_history(
    username: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """清空聊天历史"""
    user_id = await _get_user_id(username, db)
    count = await clear_chat_history(user_id, db)
    return _ok({"message": f"已清空 {count} 条聊天记录"})
