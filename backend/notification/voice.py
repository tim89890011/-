"""
钢子出击 - 语音播报文本生成
"""

from backend.utils.symbol import to_base


def generate_voice_text(signal: dict) -> str:
    """
    根据信号生成中文语音播报文本
    signal 需包含: symbol, signal, confidence, risk_level
    """
    symbol = signal.get("symbol", "未知")
    # 简化币种名称
    coin_names = {
        "BTCUSDT": "比特币",
        "ETHUSDT": "以太坊",
        "BNBUSDT": "BNB",
        "SOLUSDT": "索拉纳",
        "XRPUSDT": "瑞波",
        "ADAUSDT": "艾达",
        "DOGEUSDT": "狗狗币",
        "AVAXUSDT": "雪崩",
        "DOTUSDT": "波卡",
        "POLUSDT": "波卡2",
    }
    coin_name = coin_names.get(symbol, to_base(symbol))

    sig = signal.get("signal", "HOLD")
    confidence = signal.get("confidence", 50)
    risk_level = signal.get("risk_level", "中")

    signal_cn = {
        "BUY": "开多",
        "SELL": "平多",
        "SHORT": "开空",
        "COVER": "平空",
        "HOLD": "观望",
    }.get(sig, "观望")

    text = f"钢子出击提醒：{coin_name}{signal_cn}信号，置信度{confidence}%，风险等级{risk_level}。本分析仅供参考，不构成投资建议。"

    return text
