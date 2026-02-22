"""
钢子出击 - AI 角色定义与并发分析
5 个分析师角色：千问 qwen3-max + DeepSeek V3 混合调用，制造模型多样性
"""
import re
import asyncio
import logging
from typing import Optional

from backend.ai_engine.deepseek_client import deepseek_client
from backend.ai_engine.prompts import (
    build_tech_wang_prompt,
    build_trend_li_prompt,
    build_sentiment_zhang_prompt,
    build_fund_zhao_prompt,
    build_risk_chen_prompt,
)

logger = logging.getLogger(__name__)

# 5 个 AI 角色定义
ROLES = [
    {
        "id": "tech_wang",
        "name": "技术老王",
        "title": "技术面分析师",
        "emoji": "📊",
        "color": "#00d4ff",
        "model": "deepseek-v3",
        "prompt_builder": build_tech_wang_prompt,
    },
    {
        "id": "trend_li",
        "name": "趋势老李",
        "title": "趋势跟踪分析师",
        "emoji": "📈",
        "color": "#00ff88",
        "model": "qwen",
        "prompt_builder": build_trend_li_prompt,
    },
    {
        "id": "sentiment_zhang",
        "name": "情绪小张",
        "title": "市场情绪分析师",
        "emoji": "🧠",
        "color": "#ff6b6b",
        "model": "deepseek-v3",
        "prompt_builder": build_sentiment_zhang_prompt,
    },
    {
        "id": "fund_zhao",
        "name": "资金老赵",
        "title": "资金流向分析师",
        "emoji": "💰",
        "color": "#ffd700",
        "model": "qwen",
        "prompt_builder": build_fund_zhao_prompt,
    },
    {
        "id": "risk_chen",
        "name": "风控老陈",
        "title": "风险控制分析师",
        "emoji": "🛡️",
        "color": "#9b59b6",
        "model": "qwen",
        "prompt_builder": build_risk_chen_prompt,
    },
]


def _parse_signal_from_text(text: str) -> str:
    """从 AI 回复中提取信号（BUY/SELL/SHORT/COVER/HOLD）"""
    text_upper = text.upper()
    # #30 修复：加词边界，避免从 HOUSEHOLD/BUYBACK/SHORTAGE 等单词误匹配
    # 优先匹配精确标记格式，SHORT/COVER 放在 SELL 前面避免被 SHORT 中的 S 干扰
    patterns = [
        r'信号[：:]\s*\b(BUY|SHORT|SELL|COVER|HOLD)\b',
        r'\b(SHORT|COVER)\b',  # 优先匹配新信号
        r'\b(BUY|SELL|HOLD)\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, text_upper)
        if match:
            return match.group(1)
    return "HOLD"


def _parse_confidence_from_text(text: str) -> int:
    """从 AI 回复中提取置信度"""
    # #31 修复：优先匹配明确标记，宽泛百分比模式放最后且限制 0-100
    patterns = [
        r'置信度[：:]\s*(\d+)',
        r'信心[：:]\s*(\d+)',
        r'置信度.*?(\d+)\s*%',
        r'(?<!\d)(\d{1,2})\s*%',  # 只匹配 1-2 位数的百分比
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            val = int(match.group(1))
            if 0 <= val <= 100:
                return val
    return 50


async def analyze_single_role(
    role: dict,
    symbol: str,
    price: float,
    indicators_text: str,
    market_data_text: str,
    pre_filter_context: Optional[str] = None,
) -> dict:
    """
    单个角色分析
    返回 {"role_id", "name", "title", "emoji", "color", "model_label", "signal", "confidence", "analysis", "input_messages"}
    """
    try:
        # 构建该角色的 prompt
        messages = role["prompt_builder"](
            symbol, price, indicators_text, market_data_text, pre_filter_context
        )

        # 模型显示名称映射
        model_label = "DeepSeek V3" if role.get("model") == "deepseek-v3" else "Qwen3-Max"

        # 根据角色特性分配温度
        _role_temperature = {
            "tech_wang": 0.5,       # 技术面需要确定性
            "trend_li": 0.6,        # 趋势判断需稳定
            "sentiment_zhang": 0.8,  # 情绪感知需要多样性
            "fund_zhao": 0.6,       # 资金流数据需准确
            "risk_chen": 0.3,       # 风控必须保守
        }
        temp = _role_temperature.get(role["id"], 0.7)

        # 根据角色 model 字段分流：deepseek-v3 走 V3，其余走千问
        if role.get("model") == "deepseek-v3":
            response = await deepseek_client.chat_v3(messages, temperature=temp, symbol=symbol)
        else:
            response = await deepseek_client.chat(messages, temperature=temp, symbol=symbol)

        # 解析信号和置信度
        signal = _parse_signal_from_text(response)
        confidence = _parse_confidence_from_text(response)

        return {
            "role_id": role["id"],
            "name": role["name"],
            "title": role["title"],
            "emoji": role["emoji"],
            "color": role["color"],
            "model_label": model_label,
            "signal": signal,
            "confidence": confidence,
            "analysis": response,
            "input_messages": messages,
        }

    except Exception as e:
        logger.error(f"[AI角色] {role['name']} 分析异常: {e}")
        model_label = "DeepSeek V3" if role.get("model") == "deepseek-v3" else "Qwen3-Max"
        return {
            "role_id": role["id"],
            "name": role["name"],
            "title": role["title"],
            "emoji": role["emoji"],
            "color": role["color"],
            "model_label": model_label,
            "signal": "HOLD",
            "confidence": 0,
            "analysis": f"[分析失败] {str(e)}",
            "input_messages": [],
        }


async def analyze_all_roles(
    symbol: str,
    price: float,
    indicators_text: str,
    market_data_text: str,
    pre_filter_context: Optional[str] = None,
) -> list:
    """
    并发调用 5 个角色进行分析
    返回 5 个角色的分析结果列表
    """
    logger.info(f"[AI角色] 开始 5 角色并发分析 {symbol}...")

    tasks = [
        analyze_single_role(
            role, symbol, price, indicators_text, market_data_text, pre_filter_context
        )
        for role in ROLES
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 处理异常结果
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[AI角色] {ROLES[i]['name']} 异常: {result}")
            final_results.append({
                "role_id": ROLES[i]["id"],
                "name": ROLES[i]["name"],
                "title": ROLES[i]["title"],
                "emoji": ROLES[i]["emoji"],
                "color": ROLES[i]["color"],
                "signal": "HOLD",
                "confidence": 0,
                "analysis": f"[异常] {str(result)}",
            })
        else:
            final_results.append(result)

    logger.info(f"[AI角色] {symbol} 分析完成，5 个角色结果已收集")
    return final_results
