"""
tests/test_json_parser.py - AI 回复 JSON 解析的测试
"""

import pytest


class TestParseJsonFromText:
    """测试从 AI 回复中提取 JSON"""

    def test_direct_json(self):
        """直接 JSON 字符串"""
        from backend.ai_engine.json_parser import parse_json_from_text
        result = parse_json_from_text('{"signal": "BUY", "confidence": 75}')
        assert result["signal"] == "BUY"
        assert result["confidence"] == 75

    def test_markdown_code_block(self):
        """Markdown ```json 代码块"""
        from backend.ai_engine.json_parser import parse_json_from_text
        text = 'Some text\n```json\n{"signal": "SELL", "confidence": 60}\n```\nMore text'
        result = parse_json_from_text(text)
        assert result["signal"] == "SELL"

    def test_embedded_json(self):
        """文本中嵌入的 JSON"""
        from backend.ai_engine.json_parser import parse_json_from_text
        text = 'AI analysis: {"signal": "SHORT", "confidence": 80} end.'
        result = parse_json_from_text(text)
        assert result["signal"] == "SHORT"

    def test_trailing_comma(self):
        """JSON 中有尾逗号"""
        from backend.ai_engine.json_parser import parse_json_from_text
        text = '{"signal": "BUY", "confidence": 70,}'
        result = parse_json_from_text(text)
        assert result["signal"] == "BUY"

    def test_think_tag_removal(self):
        """DeepSeek R1 <think> 标签应被剥离"""
        from backend.ai_engine.json_parser import parse_json_from_text
        text = '<think>Let me analyze...</think>{"signal": "HOLD", "confidence": 50}'
        result = parse_json_from_text(text)
        assert result["signal"] == "HOLD"

    def test_regex_field_extraction(self):
        """当 JSON 格式损坏时从字段级正则提取"""
        from backend.ai_engine.json_parser import parse_json_from_text
        text = 'The "signal": "BUY" with "confidence": 85 looks good'
        result = parse_json_from_text(text)
        assert result is not None
        assert result["signal"] == "BUY"
        assert result["confidence"] == 85

    def test_chinese_text_extraction(self):
        """从中文推理文本中提取信号"""
        from backend.ai_engine.json_parser import parse_json_from_text
        text = "经过分析，最终信号为 BUY，置信度: 72%"
        result = parse_json_from_text(text)
        assert result is not None
        assert result["signal"] == "BUY"
        assert result["confidence"] == 72

    def test_empty_input(self):
        """空输入"""
        from backend.ai_engine.json_parser import parse_json_from_text
        assert parse_json_from_text("") is None
        assert parse_json_from_text(None) is None

    def test_no_json_found(self):
        """纯文本无 JSON"""
        from backend.ai_engine.json_parser import parse_json_from_text
        result = parse_json_from_text("This is just plain text with no signals")
        assert result is None


class TestExtractJsonFromReasoning:
    """测试从 R1 推理链中提取 JSON"""

    def test_markdown_block(self):
        """推理链中的 markdown JSON 块"""
        from backend.ai_engine.json_parser import extract_json_from_reasoning
        text = 'Analysis done.\n```json\n{"signal": "BUY", "confidence": 80}\n```\nEnd.'
        result = extract_json_from_reasoning(text)
        assert result is not None
        assert '"signal"' in result

    def test_embedded_json_with_signal(self):
        """推理链中嵌入的含 signal 键的 JSON"""
        from backend.ai_engine.json_parser import extract_json_from_reasoning
        text = 'So my decision is {"signal": "SELL", "confidence": 65, "reason": "downtrend"} based on...'
        result = extract_json_from_reasoning(text)
        assert result is not None

    def test_no_signal_key(self):
        """没有 signal 键的 JSON 不会被提取"""
        from backend.ai_engine.json_parser import extract_json_from_reasoning
        text = 'Data: {"price": 50000, "volume": 100}'
        result = extract_json_from_reasoning(text)
        assert result is None

    def test_empty_input(self):
        """空输入"""
        from backend.ai_engine.json_parser import extract_json_from_reasoning
        result = extract_json_from_reasoning("")
        assert result is None
