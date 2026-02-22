"""
统一 AIClient 命名（兼容层）。

历史上 deepseek_client.py 内部同时调用 DeepSeek + Qwen（OpenAI兼容），
文件名/类名容易误导。本文件提供更准确的命名，同时保持旧导入可用。
"""

from __future__ import annotations

from backend.ai_engine.deepseek_client import DeepSeekClient, deepseek_client


AIClient = DeepSeekClient
# 复用历史单例，避免重复创建 httpx client/配额计数
ai_client = deepseek_client

