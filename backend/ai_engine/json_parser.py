"""
统一 JSON 解析模块

从 AI 回复文本中提取 JSON 的唯一来源，
替代散落在 debate.py 和 deepseek_client.py 中的重复实现。
"""

import json
import logging
import re
from typing import Optional

from backend.ai_engine.schemas import SignalOutput, validate_signal_output

logger = logging.getLogger(__name__)


def parse_signal_from_text(text: str, source: str = "") -> Optional[SignalOutput]:
    """
    从 AI 回复中提取信号并进行 Schema 验证。

    返回 SignalOutput（Pydantic 模型）或 None。
    - 解析成功但验证失败: 记录 error 日志并返回 None
    - 解析失败: 记录 warning 日志并返回 None
    """
    raw = parse_json_from_text(text)
    if raw is None:
        if text and text.strip():
            logger.warning("[JSON解析] 无法从文本中提取信号 | source=%s | text=%s", source, text[:200])
        return None
    validated = validate_signal_output(raw, source=source)
    if validated is None:
        logger.error("[JSON解析] Schema 验证失败 | source=%s | raw=%s", source, str(raw)[:500])
    return validated


def parse_json_from_text(text: str) -> Optional[dict]:
    """
    从 AI 回复中提取 JSON（增强版：处理 DeepSeek R1 的 <think> 标签和各种格式问题）

    按优先级尝试 5 种策略：
    1. 直接 JSON 解析
    2. Markdown 代码块提取
    3. 花括号范围提取（含尾逗号/注释清理）
    4. 正则逐字段提取
    5. 中文推理文本提取
    """
    if not text or not isinstance(text, str) or not text.strip():
        return None

    # 剥离 DeepSeek R1 的 <think>...</think> 推理过程
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if not cleaned:
        cleaned = text

    # 按优先级尝试多种解析策略
    for candidate in [cleaned, text]:
        # 策略 1：直接解析
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            pass

        # 策略 2：从 markdown 代码块提取
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", candidate, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except (json.JSONDecodeError, ValueError):
                pass

        # 策略 3：找第一个 { 到最后一个 }
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw_json = candidate[start : end + 1]
            try:
                return json.loads(raw_json)
            except (json.JSONDecodeError, ValueError):
                pass
            # 策略 3b：清理常见格式问题后重试
            fixed = re.sub(r",\s*([}\]])", r"\1", raw_json)  # 去尾逗号
            fixed = re.sub(r"//[^\n]*", "", fixed)  # 去行注释
            fixed = re.sub(r"/\*.*?\*/", "", fixed, flags=re.DOTALL)  # 去块注释
            try:
                return json.loads(fixed)
            except (json.JSONDecodeError, ValueError):
                pass

    # 策略 4（兜底）：用正则逐字段提取关键信息
    for src in [cleaned, text]:
        try:
            sig_m = re.search(r'"signal"\s*:\s*"(BUY|SELL|SHORT|COVER|HOLD)"', src, re.IGNORECASE)
            conf_m = re.search(r'"confidence"\s*:\s*(\d+)', src)
            reason_m = re.search(r'"reason"\s*:\s*"((?:[^"\\]|\\.)*)"', src, re.DOTALL)
            risk_m = re.search(r'"risk_level"\s*:\s*"((?:[^"\\]|\\.)*)"', src)
            if sig_m and conf_m:
                return {
                    "signal": sig_m.group(1).upper(),
                    "confidence": int(conf_m.group(1)),
                    "reason": reason_m.group(1) if reason_m else "R1 字段级提取",
                    "risk_level": risk_m.group(1) if risk_m else "中",
                    "risk_assessment": "R1 返回格式异常，已通过字段级提取恢复。",
                    "daily_quote": "数据虽不完美，方向才是关键。",
                }
        except Exception as e:
            logger.debug("[JSON解析] 策略4正则字段提取异常: %s", e)

    # 策略 5（终极兜底）：从中文推理文本中提取决策意图
    try:
        full = cleaned + " " + text
        sig_patterns = [
            (r'(?:最终|综合|决定|建议|给出|输出|信号[为是])\s*[:：]?\s*(BUY|SELL|SHORT|COVER|HOLD)', None),
            (r'(?:给出|发出|建议)\s*(做多|开多|买入)', "BUY"),
            (r'(?:给出|发出|建议)\s*(做空|开空)', "SHORT"),
            (r'(?:给出|发出|建议)\s*(平多|卖出)', "SELL"),
            (r'(?:给出|发出|建议)\s*(平空)', "COVER"),
            (r'(?:给出|保持|维持)\s*(观望|HOLD|持仓观望)', "HOLD"),
            (r'信号[为是]\s*(BUY|SELL|SHORT|COVER|HOLD)', None),
        ]
        conf_patterns = [
            r'(?:置信度|confidence)\s*[:：]?\s*(\d{1,3})\s*%?',
            r'(\d{2,3})\s*%?\s*(?:的置信度|置信度|confidence)',
        ]
        found_signal = None
        for pat, override in sig_patterns:
            m = re.search(pat, full, re.IGNORECASE)
            if m:
                found_signal = override or m.group(1).upper()
                break
        found_conf = 65
        for pat in conf_patterns:
            m = re.search(pat, full, re.IGNORECASE)
            if m:
                found_conf = min(int(m.group(1)), 100)
                break
        if found_signal:
            return {
                "signal": found_signal,
                "confidence": found_conf,
                "reason": "R1 推理文本提取（非 JSON 格式）",
                "risk_level": "中",
                "risk_assessment": "R1 未返回 JSON，从推理文本中提取了决策意图。",
                "daily_quote": "理解比格式更重要。",
            }
    except Exception as e:
        logger.debug("[JSON解析] 策略5中文文本提取异常: %s", e)

    return None


def extract_json_from_reasoning(text: str) -> Optional[str]:
    """
    从 R1 的 reasoning_content 中提取最可能的 JSON 决策块

    返回 JSON 字符串（非 dict），供调用方进一步处理。
    """
    if not text or not isinstance(text, str):
        return None

    # 策略 1: 找 ```json ... ``` 代码块
    m = re.search(r'```json\s*\n?(\{[\s\S]*?\})\s*```', text)
    if m:
        try:
            obj = json.loads(m.group(1))
            if 'signal' in obj:
                return m.group(1)
        except Exception as e:
            logger.debug("[JSON推理提取] markdown JSON 解析失败: %s", e)

    # 策略 2: 找最大的 {...} 块，且包含 "signal" 键
    candidates = []
    for m in re.finditer(r'\{[\s\S]*?\}', text):
        s = m.group(0)
        if len(s) > 50 and '"signal"' in s:
            candidates.append(s)
    for c in sorted(candidates, key=len, reverse=True):
        try:
            obj = json.loads(c)
            if 'signal' in obj and 'confidence' in obj:
                return c
        except Exception:
            continue

    return None
