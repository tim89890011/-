/**
 * 钢子出击 - 彩蛋功能（入口模块）
 * 市场情绪温度计 + 巨鲸警报 + AI 方向一致性统计面板
 */
import { loadBacktestReportsPanel } from './extras/backtest-report.js';
import {
    loadSentimentPanel,
    loadWhalePanel,
    loadAccuracyPanel,
    initAccFilterButtons,
} from './extras/market-widgets.js';
import {
    loadSignalHistory,
    loadQuotaPanel,
    loadCostPanel,
} from './extras/cost-monitor.js';

// Re-export all public functions for any ES module consumers
export {
    loadBacktestReportsPanel,
    loadSentimentPanel,
    loadWhalePanel,
    loadAccuracyPanel,
    loadSignalHistory,
    loadQuotaPanel,
    loadCostPanel,
};

// ============ 初始化所有彩蛋 ============
export function initExtras() {
    loadSentimentPanel();
    loadWhalePanel();
    initAccFilterButtons();
    loadAccuracyPanel(0);
    loadSignalHistory();
    loadQuotaPanel();
    loadCostPanel();
    loadBacktestReportsPanel();
}

window.GangziApp = window.GangziApp || {};
Object.assign(window.GangziApp, {
    loadSentimentPanel,
    loadWhalePanel,
    loadAccuracyPanel,
    loadSignalHistory,
    loadQuotaPanel,
    loadCostPanel,
    loadBacktestReportsPanel,
    initExtras,
});
