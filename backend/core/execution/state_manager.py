"""
钢子出击 - 统一状态管理器（单例 + 持久化）
取代 executor.py 中的全局 _cooldown_map、_sell_tighten_map 等模块级变量。

设计原则：
- executor.py 直接访问 state.cooldown_map[key] 等字典属性（保持语义一致）
- 不使用 helper 方法做业务逻辑，避免与现有行为产生差异
- 持久化为可选能力，丢失状态只影响冷却/收紧（短期数据，影响可控）
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class StateManager:
    """统一状态管理器（单例模式 + JSON 持久化）"""

    _instance: Optional["StateManager"] = None
    _state_file = Path("data/state.json")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        """初始化所有状态字典 + 从磁盘加载"""
        # 冷却记录：key="{symbol}_{side}"，value=最后交易时间戳
        self.cooldown_map: Dict[str, float] = {}

        # SELL 信号收紧止损：key=symbol，value={"time": timestamp, "confidence": int}
        self.sell_tighten_map: Dict[str, Dict[str, Any]] = {}

        # 动态 ATR 缓存：key=symbol，value={"atr_pct": float, "time": float}
        self.symbol_atr: Dict[str, Dict[str, Any]] = {}

        # 单币种止损计数器：key=symbol，value={"count": int, "pause_until": float}
        self.sl_tracker: Dict[str, Dict[str, Any]] = {}

        # 币种准确率缓存：key=symbol，value={"accuracy": float, "time": float}
        self.accuracy_cache: Dict[str, Dict[str, Any]] = {}

        self._load_from_file()
        logger.info("[StateManager] 初始化完成")

    def _load_from_file(self):
        """从 JSON 文件恢复状态"""
        if not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            self.cooldown_map = data.get("cooldown_map", {})
            self.sell_tighten_map = data.get("sell_tighten_map", {})
            self.symbol_atr = data.get("symbol_atr", {})
            self.sl_tracker = data.get("sl_tracker", {})
            self.accuracy_cache = data.get("accuracy_cache", {})
            logger.info(f"[StateManager] 从 {self._state_file} 加载状态成功")
        except Exception as e:
            logger.warning(f"[StateManager] 状态文件加载失败，使用空状态: {e}")

    def save(self):
        """持久化当前状态到 JSON 文件"""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "cooldown_map": self.cooldown_map,
                "sell_tighten_map": self.sell_tighten_map,
                "symbol_atr": self.symbol_atr,
                "sl_tracker": self.sl_tracker,
                "accuracy_cache": self.accuracy_cache,
                "last_save": time.time(),
            }
            self._state_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"[StateManager] 状态保存失败: {e}")

    def clear_all(self):
        """清除所有内存状态"""
        self.cooldown_map.clear()
        self.sell_tighten_map.clear()
        self.symbol_atr.clear()
        self.sl_tracker.clear()
        self.accuracy_cache.clear()
        self.save()
        logger.info("[StateManager] 已清除全部状态")
