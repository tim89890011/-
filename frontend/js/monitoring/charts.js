/**
 * 钢子出击 - 监控图表模块
 * API 成功率图表、WebSocket 连接数图表、告警检查
 */
import { monitoringState, _chartTickColor } from '../monitoring.js';

// ---------------------------------------------------------------------------
// 图表更新
// ---------------------------------------------------------------------------

/**
 * 更新图表（入口）
 */
export function updateCharts(metrics) {
  // 保存历史数据
  monitoringState.metricsHistory.push({
    timestamp: Date.now(),
    apiSuccessRate: metrics.api?.recent_5min?.success_rate || 0,
    wsConnections: metrics.websocket?.total_connections || 0,
  });

  // 限制历史数据长度
  if (monitoringState.metricsHistory.length > monitoringState.maxHistoryPoints) {
    monitoringState.metricsHistory.shift();
  }

  // 更新 API 成功率图表
  updateApiSuccessRateChart();

  // 更新 WebSocket 连接数图表
  updateWsConnectionsChart();
}

/**
 * 更新 API 成功率图表
 */
export function updateApiSuccessRateChart() {
  const ctx = document.getElementById('apiSuccessRateChart');
  if (!ctx) return;
  if (typeof Chart === 'undefined') {
    return;
  }

  const history = monitoringState.metricsHistory;
  const labels = history.map((_, i) => i);
  const data = history.map(h => h.apiSuccessRate);

  if (monitoringState.charts.apiSuccessRate) {
    monitoringState.charts.apiSuccessRate.destroy();
  }

  monitoringState.charts.apiSuccessRate = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: '成功率 (%)',
        data: data,
        borderColor: '#22c55e',
        backgroundColor: 'rgba(34, 197, 94, 0.1)',
        fill: true,
        tension: 0.4,
        pointRadius: 0,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: { display: false },
        y: {
          beginAtZero: true,
          max: 100,
          grid: {
            color: 'rgba(148, 163, 184, 0.1)'
          },
          ticks: {
            color: _chartTickColor()
          }
        }
      }
    }
  });
}

/**
 * 更新 WebSocket 连接数图表
 */
export function updateWsConnectionsChart() {
  const ctx = document.getElementById('wsConnectionsChart');
  if (!ctx) return;
  if (typeof Chart === 'undefined') {
    return;
  }

  const history = monitoringState.metricsHistory;
  const labels = history.map((_, i) => i);
  const data = history.map(h => h.wsConnections);

  if (monitoringState.charts.wsConnections) {
    monitoringState.charts.wsConnections.destroy();
  }

  monitoringState.charts.wsConnections = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: '连接数',
        data: data,
        borderColor: '#38bdf8',
        backgroundColor: 'rgba(56, 189, 248, 0.1)',
        fill: true,
        tension: 0.4,
        pointRadius: 0,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: { display: false },
        y: {
          beginAtZero: true,
          grid: {
            color: 'rgba(148, 163, 184, 0.1)'
          },
          ticks: {
            color: _chartTickColor()
          }
        }
      }
    }
  });
}

// ---------------------------------------------------------------------------
// 告警检查
// ---------------------------------------------------------------------------

/**
 * 检查告警
 */
export function checkAlerts(data) {
  const alertContainer = document.getElementById('alertContainer');
  if (!alertContainer) return;

  const alerts = [];

  // 配额告警
  if (data.quota) {
    const usagePercent = data.quota.usage_percent || 0;
    if (usagePercent >= 90) {
      alerts.push({
        level: 'critical',
        icon: '<i class="ri-alarm-warning-line"></i>',
        title: 'API 配额警告',
        message: `配额使用率已达 ${usagePercent.toFixed(1)}%，请立即关注`
      });
    } else if (usagePercent >= 80) {
      alerts.push({
        level: 'warning',
        icon: '<i class="ri-error-warning-line"></i>',
        title: 'API 配额提醒',
        message: `配额使用率已达 ${usagePercent.toFixed(1)}%，请注意控制使用`
      });
    }

    // 成本告警
    const status = data.quota.status;
    if (status === 'exceeded') {
      alerts.push({
        level: 'critical',
        icon: '<i class="ri-money-dollar-circle-line"></i>',
        title: 'API 配额已耗尽',
        message: '今日 API 配额已用完，非必要分析已暂停'
      });
    }
  }

  // 系统健康告警
  if (data.websocket?.total === 0) {
    alerts.push({
      level: 'warning',
      icon: '🔌',
      title: 'WebSocket 连接异常',
      message: '当前无活跃的 WebSocket 连接'
    });
  }

  // 渲染告警
  if (alerts.length > 0) {
    alertContainer.innerHTML = alerts.map(alert => `
      <div class="alert-item ${alert.level}">
        <span class="alert-icon">${alert.icon}</span>
        <div class="alert-content">
          <div class="alert-title">${alert.title}</div>
          <div class="alert-message">${alert.message}</div>
        </div>
        <button class="alert-close" onclick="this.parentElement.remove()">×</button>
      </div>
    `).join('');
  } else {
    alertContainer.innerHTML = '';
  }
}
