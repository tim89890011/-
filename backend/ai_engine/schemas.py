"""
AI 信号输出的 Pydantic Schema 定义

所有从 json_parser 输出的信号数据必须经过此 Schema 验证，
确保字段类型/范围一致，杜绝裸 dict 透传导致的下游崩溃。
"""

import logging
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    SHORT = "SHORT"
    COVER = "COVER"
    HOLD = "HOLD"


class SignalOutput(BaseModel):
    """AI 分析师输出的信号结构"""

    signal: SignalType
    confidence: int = Field(ge=0, le=100)
    reason: str = Field(default="")
    risk_level: str = Field(default="中")
    risk_assessment: str = Field(default="")
    daily_quote: str = Field(default="")

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v):
        """确保 confidence 在 0-100 范围内"""
        if isinstance(v, (int, float)):
            return max(0, min(100, int(v)))
        return v

    @field_validator("signal", mode="before")
    @classmethod
    def normalize_signal(cls, v):
        """标准化信号值"""
        if isinstance(v, str):
            return v.upper().strip()
        return v


def validate_signal_output(raw: Optional[dict], source: str = "") -> Optional[SignalOutput]:
    """
    验证并转换裸 dict 为 SignalOutput。

    - 成功: 返回 SignalOutput 实例
    - 输入为 None: 返回 None（合法的"无信号"）
    - 验证失败: 记录错误日志并返回 None
    """
    if raw is None:
        return None

    try:
        return SignalOutput.model_validate(raw)
    except Exception as e:
        logger.error(
            "[Schema] 信号验证失败: %s | source=%s | raw=%s",
            str(e),
            source,
            str(raw)[:500],
        )
        return None
