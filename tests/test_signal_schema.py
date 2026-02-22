"""
tests/test_signal_schema.py - AI 信号 Schema 护栏测试

覆盖范围:
- SignalOutput Pydantic 模型验证
- parse_signal_from_text 端到端验证
- 正常 JSON / markdown 代码块 / 字段缺失 / 非法输入
- 确保非法输入不会静默返回 None（必须有日志）
"""

import logging
import pytest

from backend.ai_engine.schemas import SignalOutput, SignalType, validate_signal_output
from backend.ai_engine.json_parser import parse_signal_from_text


class TestSignalOutputModel:
    """Pydantic 模型直接验证测试"""

    def test_valid_buy_signal(self):
        s = SignalOutput(
            signal="BUY",
            confidence=75,
            reason="趋势向上",
            risk_level="低",
        )
        assert s.signal == SignalType.BUY
        assert s.confidence == 75

    def test_valid_hold_signal(self):
        s = SignalOutput(signal="HOLD", confidence=50)
        assert s.signal == SignalType.HOLD
        assert s.reason == ""

    def test_all_signal_types(self):
        for sig in ["BUY", "SELL", "SHORT", "COVER", "HOLD"]:
            s = SignalOutput(signal=sig, confidence=50)
            assert s.signal.value == sig

    def test_confidence_clamp_over_100(self):
        s = SignalOutput(signal="BUY", confidence=150)
        assert s.confidence == 100

    def test_confidence_clamp_negative(self):
        s = SignalOutput(signal="BUY", confidence=-10)
        assert s.confidence == 0

    def test_invalid_signal_type(self):
        with pytest.raises(Exception):
            SignalOutput(signal="INVALID", confidence=50)

    def test_missing_signal_field(self):
        with pytest.raises(Exception):
            SignalOutput(confidence=50)

    def test_missing_confidence_field(self):
        with pytest.raises(Exception):
            SignalOutput(signal="BUY")

    def test_lowercase_signal_normalized(self):
        s = SignalOutput(signal="buy", confidence=60)
        assert s.signal == SignalType.BUY

    def test_signal_with_whitespace(self):
        s = SignalOutput(signal="  SELL  ", confidence=70)
        assert s.signal == SignalType.SELL

    def test_default_fields(self):
        s = SignalOutput(signal="HOLD", confidence=50)
        assert s.risk_level == "中"
        assert s.reason == ""
        assert s.risk_assessment == ""
        assert s.daily_quote == ""


class TestValidateSignalOutput:
    """validate_signal_output 函数测试"""

    def test_valid_dict(self):
        result = validate_signal_output({"signal": "BUY", "confidence": 75})
        assert result is not None
        assert result.signal == SignalType.BUY

    def test_none_input(self):
        result = validate_signal_output(None)
        assert result is None

    def test_invalid_dict_logs_error(self, caplog):
        with caplog.at_level(logging.ERROR):
            result = validate_signal_output({"signal": "INVALID"}, source="test")
        assert result is None
        assert "信号验证失败" in caplog.text

    def test_extra_fields_ignored(self):
        """额外字段不应导致验证失败"""
        result = validate_signal_output({
            "signal": "BUY",
            "confidence": 80,
            "extra_field": "should be ignored",
            "atr_pct": 1.5,
        })
        assert result is not None
        assert result.signal == SignalType.BUY


class TestParseSignalFromText:
    """parse_signal_from_text 端到端测试"""

    def test_valid_json_string(self):
        result = parse_signal_from_text('{"signal": "BUY", "confidence": 75}')
        assert result is not None
        assert result.signal == SignalType.BUY
        assert result.confidence == 75

    def test_markdown_code_block(self):
        text = 'Some analysis\n```json\n{"signal": "SELL", "confidence": 60}\n```\nMore text'
        result = parse_signal_from_text(text)
        assert result is not None
        assert result.signal == SignalType.SELL

    def test_embedded_json(self):
        text = 'Result: {"signal": "SHORT", "confidence": 80, "reason": "下跌趋势"}'
        result = parse_signal_from_text(text)
        assert result is not None
        assert result.signal == SignalType.SHORT

    def test_think_tag_stripped(self):
        text = '<think>reasoning...</think>{"signal": "HOLD", "confidence": 50}'
        result = parse_signal_from_text(text)
        assert result is not None
        assert result.signal == SignalType.HOLD

    def test_regex_field_extraction(self):
        text = 'The "signal": "BUY" with "confidence": 85 looks good'
        result = parse_signal_from_text(text)
        assert result is not None
        assert result.signal == SignalType.BUY
        assert result.confidence == 85

    def test_chinese_text_extraction(self):
        text = "经过分析，最终信号为 BUY，置信度: 72%"
        result = parse_signal_from_text(text)
        assert result is not None
        assert result.signal == SignalType.BUY
        assert result.confidence == 72

    def test_empty_input_returns_none(self):
        result = parse_signal_from_text("")
        assert result is None

    def test_none_input_returns_none(self):
        result = parse_signal_from_text(None)
        assert result is None

    def test_no_signal_in_text(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = parse_signal_from_text("just some random text", source="test")
        assert result is None
        assert "无法从文本中提取信号" in caplog.text

    def test_invalid_signal_value_in_json(self, caplog):
        """JSON 解析成功但 signal 值非法 → schema 验证失败"""
        with caplog.at_level(logging.ERROR):
            result = parse_signal_from_text('{"signal": "ATTACK", "confidence": 90}', source="test")
        assert result is None
        assert "Schema 验证失败" in caplog.text

    def test_trailing_comma_json(self):
        text = '{"signal": "BUY", "confidence": 70,}'
        result = parse_signal_from_text(text)
        assert result is not None
        assert result.signal == SignalType.BUY

    def test_full_signal_with_all_fields(self):
        text = '{"signal": "SELL", "confidence": 85, "reason": "MACD 死叉", "risk_level": "高", "risk_assessment": "注意止损", "daily_quote": "稳中求胜"}'
        result = parse_signal_from_text(text)
        assert result is not None
        assert result.signal == SignalType.SELL
        assert result.confidence == 85
        assert result.reason == "MACD 死叉"
        assert result.risk_level == "高"

    def test_source_parameter_in_log(self, caplog):
        """source 参数应出现在日志中"""
        with caplog.at_level(logging.WARNING):
            parse_signal_from_text("nonsense text", source="debate_role_wang")
        assert "debate_role_wang" in caplog.text
