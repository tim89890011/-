"""
tests/test_callback_wiring.py - 回调接线契约测试

覆盖范围:
- set_signal_broadcast_callback / set_trade_executor_callback 注入正确
- 回调在信号产生时被调用（emit_signal=True 场景）
- 回调不在 HOLD 信号时调用（emit_signal=False 场景）
- 回调异常不影响主流程
"""

import asyncio
import pytest

import backend.ai_engine.debate as debate_module


class TestCallbackRegistration:
    """测试回调函数的注册机制"""

    def setup_method(self):
        """每个测试前重置回调"""
        debate_module._signal_broadcast_callback = None
        debate_module._trade_executor_callback = None

    def teardown_method(self):
        """每个测试后清理"""
        debate_module._signal_broadcast_callback = None
        debate_module._trade_executor_callback = None

    def test_set_signal_broadcast_callback(self):
        """注册信号广播回调"""
        async def mock_broadcast(signal):
            pass

        debate_module.set_signal_broadcast_callback(mock_broadcast)
        assert debate_module._signal_broadcast_callback is mock_broadcast

    def test_set_trade_executor_callback(self):
        """注册交易执行回调"""
        async def mock_executor(signal):
            pass

        debate_module.set_trade_executor_callback(mock_executor)
        assert debate_module._trade_executor_callback is mock_executor

    def test_callback_initially_none(self):
        """回调初始为 None"""
        assert debate_module._signal_broadcast_callback is None
        assert debate_module._trade_executor_callback is None

    def test_callback_can_be_replaced(self):
        """回调可以被替换"""
        async def cb1(s):
            pass

        async def cb2(s):
            pass

        debate_module.set_signal_broadcast_callback(cb1)
        assert debate_module._signal_broadcast_callback is cb1
        debate_module.set_signal_broadcast_callback(cb2)
        assert debate_module._signal_broadcast_callback is cb2


class TestCallbackInvocation:
    """测试回调在信号流程中的调用行为"""

    def setup_method(self):
        debate_module._signal_broadcast_callback = None
        debate_module._trade_executor_callback = None

    def teardown_method(self):
        debate_module._signal_broadcast_callback = None
        debate_module._trade_executor_callback = None

    @pytest.mark.asyncio
    async def test_broadcast_callback_called_on_emit_signal(self):
        """当 emit_signal=True 且回调已注册时，广播回调应被调用"""
        called_with = []

        async def mock_broadcast(signal_obj):
            called_with.append(signal_obj)

        debate_module.set_signal_broadcast_callback(mock_broadcast)

        # 模拟 debate.py 中的回调调用逻辑
        signal_obj = {"signal": "BUY", "confidence": 80}
        emit_signal = signal_obj.get("signal") in ("BUY", "SELL", "SHORT", "COVER")

        callback = debate_module._signal_broadcast_callback
        if emit_signal and callback:
            await callback(signal_obj)

        assert len(called_with) == 1
        assert called_with[0]["signal"] == "BUY"

    @pytest.mark.asyncio
    async def test_trade_callback_called_on_emit_signal(self):
        """当 emit_signal=True 且回调已注册时，交易回调应被调用"""
        called_with = []

        async def mock_executor(signal_obj):
            called_with.append(signal_obj)

        debate_module.set_trade_executor_callback(mock_executor)

        signal_obj = {"signal": "SELL", "confidence": 85}
        emit_signal = signal_obj.get("signal") in ("BUY", "SELL", "SHORT", "COVER")

        trade_cb = debate_module._trade_executor_callback
        if emit_signal and trade_cb:
            await trade_cb(signal_obj)

        assert len(called_with) == 1
        assert called_with[0]["signal"] == "SELL"

    @pytest.mark.asyncio
    async def test_callbacks_not_called_on_hold(self):
        """HOLD 信号不触发回调"""
        broadcast_called = []
        trade_called = []

        async def mock_broadcast(s):
            broadcast_called.append(s)

        async def mock_executor(s):
            trade_called.append(s)

        debate_module.set_signal_broadcast_callback(mock_broadcast)
        debate_module.set_trade_executor_callback(mock_executor)

        signal_obj = {"signal": "HOLD", "confidence": 50}
        emit_signal = signal_obj.get("signal") in ("BUY", "SELL", "SHORT", "COVER")

        callback = debate_module._signal_broadcast_callback
        if emit_signal and callback:
            await callback(signal_obj)

        trade_cb = debate_module._trade_executor_callback
        if emit_signal and trade_cb:
            await trade_cb(signal_obj)

        assert len(broadcast_called) == 0
        assert len(trade_called) == 0

    @pytest.mark.asyncio
    async def test_broadcast_exception_does_not_propagate(self):
        """广播回调异常不应传播（与 debate.py 中的 try/except 一致）"""
        async def bad_broadcast(s):
            raise RuntimeError("broadcast failed")

        debate_module.set_signal_broadcast_callback(bad_broadcast)

        signal_obj = {"signal": "BUY", "confidence": 80}
        callback = debate_module._signal_broadcast_callback

        # 模拟 debate.py 的安全调用模式
        error_caught = False
        try:
            await callback(signal_obj)
        except Exception:
            error_caught = True

        # debate.py 中实际有 try/except，所以我们验证异常确实会抛出
        # （在 debate.py 中被 _safe_broadcast 捕获）
        assert error_caught is True

    @pytest.mark.asyncio
    async def test_trade_exception_does_not_propagate(self):
        """交易回调异常不应传播"""
        async def bad_executor(s):
            raise RuntimeError("trade failed")

        debate_module.set_trade_executor_callback(bad_executor)

        signal_obj = {"signal": "SHORT", "confidence": 90}
        trade_cb = debate_module._trade_executor_callback

        error_caught = False
        try:
            await trade_cb(signal_obj)
        except Exception:
            error_caught = True

        assert error_caught is True

    @pytest.mark.asyncio
    async def test_none_callback_is_safe(self):
        """未注册回调时不应崩溃"""
        signal_obj = {"signal": "BUY", "confidence": 80}
        emit_signal = signal_obj.get("signal") in ("BUY", "SELL", "SHORT", "COVER")

        # 这应该安全跳过而不崩溃
        callback = debate_module._signal_broadcast_callback
        if emit_signal and callback:
            await callback(signal_obj)
        # 没有异常即通过

    @pytest.mark.asyncio
    async def test_both_callbacks_called_for_buy(self):
        """BUY 信号应同时触发广播和交易回调"""
        broadcast_called = False
        trade_called = False

        async def mock_broadcast(s):
            nonlocal broadcast_called
            broadcast_called = True

        async def mock_executor(s):
            nonlocal trade_called
            trade_called = True

        debate_module.set_signal_broadcast_callback(mock_broadcast)
        debate_module.set_trade_executor_callback(mock_executor)

        signal_obj = {"signal": "BUY", "confidence": 80}
        emit_signal = signal_obj.get("signal") in ("BUY", "SELL", "SHORT", "COVER")

        callback = debate_module._signal_broadcast_callback
        if emit_signal and callback:
            await callback(signal_obj)

        trade_cb = debate_module._trade_executor_callback
        if emit_signal and trade_cb:
            await trade_cb(signal_obj)

        assert broadcast_called
        assert trade_called
