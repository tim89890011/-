"""
钢子出击 - DeepSeek API 客户端
支持 Chat V3（角色分析/聊天）和 Reasoner R1（最终裁决）
集成配额管理和指标采集
"""
import logging
import asyncio
import time
from typing import Optional
import httpx

from backend.config import settings
from backend.utils.quota import quota_manager, CallType
from backend.monitoring.metrics import metrics_collector

logger = logging.getLogger(__name__)



from backend.ai_engine.json_parser import extract_json_from_reasoning as _extract_json_from_reasoning


class DeepSeekClient:
    """OpenAI 兼容接口异步客户端（千问 + DeepSeek 配合）

    .. deprecated::
        此类名及模块名 (deepseek_client) 具有历史局限性——实际同时调用
        千问 Qwen 和 DeepSeek。新代码请使用统一命名：

            from backend.ai_engine.ai_client import AIClient, ai_client

        旧导入路径仍可正常工作，无需立即迁移。
    """

    def __init__(self):
        # 注意：运行时会从 settings 读取最新 key；这里仅做 base_url 规范化
        self.deepseek_base_url = settings.DEEPSEEK_BASE_URL.rstrip("/")
        self.qwen_base_url = settings.QWEN_BASE_URL.rstrip("/")
        self.timeout = 30.0        # Chat V3 超时
        self.r1_timeout = 120.0    # Reasoner R1 超时（推理耗时更长）
        self.max_retries = 2
        # #66 修复：复用 httpx 客户端，避免每次请求重建 SSL 连接
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """获取或创建复用的 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=max(self.timeout, self.r1_timeout),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _get_headers(self, api_key: str) -> dict:
        """获取请求头"""
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def _request(
        self, 
        *,
        base_url: str,
        api_key: str,
        model: str, 
        messages: list, 
        temperature: Optional[float] = 0.7,
        call_type: CallType = CallType.OTHER,
        symbol: str = ""
    ) -> str:
        """
        通用请求方法（带重试和配额检查）
        返回 AI 回复文本，失败返回错误描述
        """
        # 检查配额
        allowed, message = await quota_manager.check_quota(call_type)
        if not allowed:
            logger.warning(f"[DeepSeek] 配额检查失败: {message}")
            return f"[配额不足] {message}"
        
        if not api_key or api_key == "sk-xxx":
            return "[错误] API Key 未配置，请检查 .env（QWEN_API_KEY 或 DEEPSEEK_API_KEY）"
        
        # 记录开始时间
        start_time = time.time()

        url = f"{base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 2000,
        }

        # #55 修复：R1 不支持 temperature 参数，只给 Chat 模型设置
        if temperature is not None and "reasoner" not in model:
            payload["temperature"] = temperature

        # R1 模型使用更长超时
        req_timeout = self.r1_timeout if "reasoner" in model else self.timeout
        client = self._get_client()

        for attempt in range(self.max_retries + 1):
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(api_key),
                    timeout=req_timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                
                # 计算耗时
                duration_ms = (time.time() - start_time) * 1000
                
                # 提取 token 使用情况
                usage = data.get("usage", {})
                tokens_in = usage.get("prompt_tokens", 0)
                tokens_out = usage.get("completion_tokens", 0)
                
                # 记录指标
                await metrics_collector.record_api_call(
                    model=model,
                    duration_ms=duration_ms,
                    success=True,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    endpoint="chat/completions",
                )
                
                # 记录配额（失败不影响主流程）
                try:
                    await quota_manager.record_call(
                        call_type=call_type,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        success=True,
                        symbol=symbol,
                        detail=f"model={model}",
                    )
                except Exception as qe:
                    logger.warning(f"[DeepSeek] 配额记录失败（已忽略）: {qe}")

                # 提取回复
                choices = data.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    content = msg.get("content", "") or ""
                    # DeepSeek R1 有时把结果放在 reasoning_content 而 content 为空
                    if not content.strip() and "reasoner" in model:
                        reasoning = msg.get("reasoning_content", "") or ""
                        if reasoning:
                            # 尝试从 reasoning_content 中提取 JSON 块
                            _extracted = _extract_json_from_reasoning(reasoning)
                            if _extracted:
                                logger.info(f"[DeepSeek] R1 content 为空，从 reasoning_content 提取到 JSON（长度{len(_extracted)}）")
                                return _extracted
                            logger.info(f"[DeepSeek] R1 content 为空，使用 reasoning_content 原文（长度{len(reasoning)}）")
                            return reasoning
                    if content:
                        return content

                return "[错误] API 返回空回复"

            except httpx.TimeoutException:
                duration_ms = (time.time() - start_time) * 1000
                logger.warning(f"[DeepSeek] 超时 (尝试 {attempt + 1}/{self.max_retries + 1})")
                
                # 记录失败指标
                await metrics_collector.record_api_call(
                    model=model,
                    duration_ms=duration_ms,
                    success=False,
                    error="timeout",
                    endpoint="chat/completions",
                )
                
                if attempt < self.max_retries:
                    await asyncio.sleep(2)
                    continue
                    
                # 最后一次失败，记录配额（失败也计配额）
                try:
                    await quota_manager.record_call(
                        call_type=call_type,
                        success=False,
                        symbol=symbol,
                        detail="timeout",
                    )
                except Exception as qe:
                    logger.warning(f"[DeepSeek] 配额记录失败（已忽略）: {qe}")
                return "[超时] DeepSeek API 请求超时，请稍后重试"

            except httpx.HTTPStatusError as e:
                duration_ms = (time.time() - start_time) * 1000
                try:
                    resp_text = (e.response.text or "")[:200]
                except Exception as e:
                    logger.debug("[DeepSeek] 读取错误响应体失败: %s", e)
                    resp_text = "<response text unavailable>"
                logger.error(f"[DeepSeek] HTTP 错误: {e.response.status_code} - {resp_text}")
                
                # 记录失败指标
                await metrics_collector.record_api_call(
                    model=model,
                    duration_ms=duration_ms,
                    success=False,
                    error=f"http_{e.response.status_code}",
                    endpoint="chat/completions",
                )
                
                # 记录配额（失败也计配额）
                try:
                    await quota_manager.record_call(
                        call_type=call_type,
                        success=False,
                        symbol=symbol,
                        detail=f"http_{e.response.status_code}",
                    )
                except Exception as qe:
                    logger.warning(f"[DeepSeek] 配额记录失败（已忽略）: {qe}")
                return f"[错误] DeepSeek API 返回 {e.response.status_code}"

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(f"[DeepSeek] 请求异常: {e}")
                
                # 记录失败指标
                await metrics_collector.record_api_call(
                    model=model,
                    duration_ms=duration_ms,
                    success=False,
                    error=str(e),
                    endpoint="chat/completions",
                )
                
                if attempt < self.max_retries:
                    await asyncio.sleep(2)
                    continue
                    
                # 最后一次失败，记录配额
                try:
                    await quota_manager.record_call(
                        call_type=call_type,
                        success=False,
                        symbol=symbol,
                        detail=str(e)[:100],
                    )
                except Exception as qe:
                    logger.warning(f"[DeepSeek] 配额记录失败（已忽略）: {qe}")
                return f"[错误] DeepSeek 调用失败: {str(e)}"

        # 所有重试失败
        duration_ms = (time.time() - start_time) * 1000
        await metrics_collector.record_api_call(
            model=model,
            duration_ms=duration_ms,
            success=False,
            error="max_retries_exceeded",
            endpoint="chat/completions",
        )
        try:
            await quota_manager.record_call(
                call_type=call_type,
                success=False,
                symbol=symbol,
                detail="max_retries_exceeded",
            )
        except Exception as qe:
            logger.warning(f"[DeepSeek] 配额记录失败（已忽略）: {qe}")
        return "[错误] DeepSeek 调用失败（已达最大重试次数）"

    async def chat(self, messages: list, temperature: float = 0.7, symbol: str = "") -> str:
        """
        调用千问 qwen3-max（角色分析/聊天）
        用于：角色分析、日常聊天
        """
        qwen_key = settings.QWEN_API_KEY
        if not qwen_key:
            return "[错误] QWEN_API_KEY 未配置，无法调用千问进行角色分析/聊天"
        return await self._request(
            base_url=settings.QWEN_BASE_URL,
            api_key=qwen_key,
            model="qwen3-max",
            messages=messages,
            temperature=temperature,
            call_type=CallType.CHAT,
            symbol=symbol,
        )

    async def chat_v3(self, messages: list, temperature: float = 0.7, symbol: str = "") -> str:
        """
        调用 DeepSeek Chat V3（角色分析 — 数据驱动型角色）
        与千问 qwen3-max 形成模型多样性，提升辩论质量
        """
        deepseek_key = settings.DEEPSEEK_API_KEY
        if not deepseek_key or deepseek_key == "sk-xxx":
            return "[错误] DEEPSEEK_API_KEY 未配置，无法调用 DeepSeek V3"
        return await self._request(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=deepseek_key,
            model="deepseek-chat",
            messages=messages,
            temperature=temperature,
            call_type=CallType.CHAT,
            symbol=symbol,
        )

    async def reason(self, messages: list, symbol: str = "") -> str:
        """
        调用 DeepSeek Reasoner R1 模型
        用于：最终裁决、深度推理
        注意：R1 不支持 temperature 参数
        """
        deepseek_key = settings.DEEPSEEK_API_KEY
        if not deepseek_key or deepseek_key == "sk-xxx":
            return "[错误] DEEPSEEK_API_KEY 未配置，无法调用 DeepSeek reasoner 进行最终裁决"
        return await self._request(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=deepseek_key,
            model="deepseek-reasoner",
            messages=messages,
            temperature=None,  # #55 修复：R1 不传 temperature
            call_type=CallType.REASONER,
            symbol=symbol,
        )


# 全局客户端实例
deepseek_client = DeepSeekClient()
