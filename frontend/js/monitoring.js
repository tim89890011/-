/**
 * 钢子出击 - 监控面板模块（入口）
 * 状态管理、初始化 / 销毁、子模块聚合导出
 */
import { API_BASE } from './auth.js';
import { createMonitoringPanel, bindMonitoringEvents } from './monitoring/panel-ui.js';
import { refreshMonitoringData, fetchValidationMetrics } from './monitoring/metrics-update.js';

// ---------------------------------------------------------------------------
// 共享状态（子模块通过 import 引用）
// ---------------------------------------------------------------------------

export const _MONITORING_API_BASE = API_BASE || window.location.origin;

export const monitoringState = {
  isInitialized: false,
  refreshInterval: null,
  charts: {},
  metricsHistory: [],
  maxHistoryPoints: 50,
  lastNoticeText: '',
};

export function _chartTickColor() {
  return document.body.classList.contains('light-theme') ? '#636366' : '#94a3b8';
}

// ---------------------------------------------------------------------------
// 初始化 / 销毁
// ---------------------------------------------------------------------------

export function initMonitoringPanel() {
  if (monitoringState.isInitialized) return;

  createMonitoringPanel();
  bindMonitoringEvents();
  refreshMonitoringData();

  monitoringState.refreshInterval = setInterval(refreshMonitoringData, 10000);
  monitoringState.isInitialized = true;
}

export function destroyMonitoringPanel() {
  if (monitoringState.refreshInterval) {
    clearInterval(monitoringState.refreshInterval);
    monitoringState.refreshInterval = null;
  }

  Object.values(monitoringState.charts).forEach(chart => {
    if (chart) chart.destroy();
  });
  monitoringState.charts = {};

  monitoringState.isInitialized = false;
}

// ---------------------------------------------------------------------------
// 子模块函数重导出（保持原有 export 接口不变）
// ---------------------------------------------------------------------------

export { refreshMonitoringData, fetchValidationMetrics };

// ---------------------------------------------------------------------------
// 全局兼容（HTML 事件处理器 + 其他非模块脚本引用）
// ---------------------------------------------------------------------------

window.initMonitoringPanel = initMonitoringPanel;
window.destroyMonitoringPanel = destroyMonitoringPanel;
window.refreshMonitoringData = refreshMonitoringData;
window.fetchValidationMetrics = fetchValidationMetrics;
