/**
 * 钢子出击 - 监控指标更新模块
 * 数据获取、健康状态 / 指标摘要 / 成本 / 配额 / 性能 / 验证 UI 更新
 */
import { monitoringState, _MONITORING_API_BASE, _chartTickColor } from '../monitoring.js';
import { getToken } from '../auth.js';
import { setMonitoringNotice, clearMonitoringNotice } from './panel-ui.js';
import { updateCharts, checkAlerts } from './charts.js';

// ---------------------------------------------------------------------------
// 数据刷新 & 获取
// ---------------------------------------------------------------------------

/**
 * 刷新监控数据
 */
export async function refreshMonitoringData() {
  try {
    const healthOk = await fetchHealthStatus();
    const metricResult = await fetchMetricsData();

    if (healthOk && metricResult.failures === 0) {
      clearMonitoringNotice();
      return;
    }

    const failedSections = [];
    if (!healthOk) failedSections.push('健康状态');
    if (metricResult.failures > 0) failedSections.push(`指标接口 ${metricResult.failures} 项`);
    setMonitoringNotice(`部分数据刷新失败：${failedSections.join('、')}。已保留最近一次成功数据。`);

  } catch (error) {
    setMonitoringNotice('监控刷新失败，请检查网络或稍后重试。');
  }
}

/**
 * 获取健康状态
 */
async function fetchHealthStatus() {
  try {
    const response = await fetch(_MONITORING_API_BASE + '/api/health');
    if (!response.ok) throw new Error(`健康检查失败(${response.status})`);

    const data = await response.json();
    updateHealthUI(data);
    return true;

  } catch (error) {
    updateHealthUI({
      status: 'unhealthy',
      checks: {},
      timestamp: new Date().toISOString()
    });
    return false;
  }
}

/**
 * 获取指标数据
 */
async function fetchMetricsData() {
  const failures = [];

  const markFailure = (name) => {
    failures.push(name);
  };

  try {
    const token = getToken ? getToken() : (window.GangziApp?.getToken ? window.GangziApp.getToken() : '');

    // 获取简化指标
    const summaryResponse = await fetch(_MONITORING_API_BASE + '/api/metrics/summary');
    if (summaryResponse.ok) {
      const summary = await summaryResponse.json();
      updateMetricsSummary(summary);
    } else {
      markFailure('summary');
    }

    // 获取详细指标（需要认证）
    if (token) {
      const metricsResponse = await fetch(_MONITORING_API_BASE + '/api/metrics/json', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (metricsResponse.ok) {
        const data = await metricsResponse.json();
        updateDetailedMetrics(data);
      } else {
        markFailure('metrics');
      }

      // 获取成本指标
      const costResponse = await fetch(_MONITORING_API_BASE + '/api/metrics/cost', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (costResponse.ok) {
        const costData = await costResponse.json();
        updateCostMetrics(costData);
      } else {
        markFailure('cost');
      }

      const quotaHistoryResp = await fetch(_MONITORING_API_BASE + '/api/metrics/api-calls?hours=168', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (quotaHistoryResp.ok) {
        const historyData = await quotaHistoryResp.json();
        updateQuotaTrend(historyData);
      } else {
        markFailure('quota-history');
      }

      // 获取性能指标
      const perfResponse = await fetch(_MONITORING_API_BASE + '/api/metrics/performance', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (perfResponse.ok) {
        const perfData = await perfResponse.json();
        updatePerformanceMetrics(perfData);
      } else {
        markFailure('performance');
      }

      // Phase A: 验证度量（双轨/基准/归因）
      const validationOk = await fetchValidationMetrics(token);
      if (!validationOk) {
        markFailure('validation');
      }
    }

    return { failures: failures.length };
  } catch (error) {
    return { failures: Math.max(failures.length, 1) };
  }
}

/**
 * 获取验证度量
 */
export async function fetchValidationMetrics(token) {
  try {
    const headers = { 'Authorization': `Bearer ${token}` };

    const [pf, bm, at] = await Promise.all([
      fetch(_MONITORING_API_BASE + '/api/analytics/prefilter?days=14', { headers }),
      fetch(_MONITORING_API_BASE + '/api/analytics/benchmark?days=30', { headers }),
      fetch(_MONITORING_API_BASE + '/api/analytics/attribution?days=14&limit=3000', { headers }),
    ]);

    if (!pf.ok || !bm.ok || !at.ok) return false;

    const pfData = await pf.json();
    const bmData = await bm.json();
    const atData = await at.json();

    updateValidationUI(pfData, bmData, atData);
    return true;
  } catch (e) {
    return false;
  }
}

// ---------------------------------------------------------------------------
// UI 更新函数
// ---------------------------------------------------------------------------

/**
 * 更新健康状态 UI
 */
function updateHealthUI(data) {
  // 更新整体状态
  const overallStatus = document.getElementById('overallHealthStatus');
  if (overallStatus) {
    const statusMap = {
      'healthy': { text: '健康', class: 'badge-green' },
      'degraded': { text: '降级', class: 'badge-yellow' },
      'unhealthy': { text: '异常', class: 'badge-red' },
    };
    const status = statusMap[data.status] || statusMap['unhealthy'];
    overallStatus.textContent = status.text;
    overallStatus.className = `badge ${status.class}`;
  }

  // 更新各组件状态
  const healthGrid = document.getElementById('healthGrid');
  if (healthGrid && data.checks) {
    const checkItems = {
      'database': { name: '数据库', icon: '<i class="ri-database-2-line"></i>' },
      'ai_service': { name: 'AI 服务', icon: '<i class="ri-robot-2-line"></i>' },
      'binance_ws': { name: '行情 WebSocket', icon: '<i class="ri-line-chart-line"></i>' },
    };

    healthGrid.innerHTML = Object.entries(checkItems).map(([key, info]) => {
      const check = data.checks[key];
      const status = check?.status || 'unhealthy';
      const statusClass = status === 'healthy' ? 'healthy' :
                          status === 'degraded' ? 'degraded' : 'unhealthy';
      const statusText = status === 'healthy' ? '正常' :
                         status === 'degraded' ? '降级' : '异常';

      return `
        <div class="health-item ${statusClass}">
          <div class="health-icon">${info.icon}</div>
          <div class="health-name">${info.name}</div>
          <div class="health-status">${statusText}</div>
        </div>
      `;
    }).join('');
  }

  // 更新时间戳
  const timestamp = document.getElementById('healthTimestamp');
  if (timestamp && data.timestamp) {
    const date = new Date(data.timestamp);
    timestamp.textContent = `最后更新: ${date.toLocaleString('zh-CN')}`;
  }
}

/**
 * 更新验证度量 UI
 */
function updateValidationUI(pfResp, bmResp, atResp) {
  const pf = pfResp?.data || pfResp || {};
  const bm = bmResp?.data || bmResp || {};
  const at = atResp?.data || atResp || {};

  const pfRateEl = document.getElementById('pfAgreedRate');
  if (pfRateEl) pfRateEl.textContent = (pf.pf_agreed_rate ?? '--');

  const pfStrongEl = document.getElementById('pfStrongCount');
  if (pfStrongEl) pfStrongEl.textContent = (pf.pf_strong_count ?? '--');

  const stratEl = document.getElementById('benchStrategy');
  if (stratEl) {
    try {
      const curve = bm.strategy?.cum_net_pnl_usdt || [];
      stratEl.textContent = curve.length ? curve[curve.length - 1].toFixed(2) : '--';
    } catch (_) { stratEl.textContent = '--'; }
  }

  const btcEl = document.getElementById('benchBtc');
  if (btcEl) {
    try {
      const curve = bm.btc?.cum_return_pct || [];
      btcEl.textContent = curve.length ? curve[curve.length - 1].toFixed(2) : '--';
    } catch (_) { btcEl.textContent = '--'; }
  }

  const topRoleEl = document.getElementById('topRoleAcc');
  if (topRoleEl) {
    const r = (at.roles || [])[0];
    topRoleEl.textContent = r ? `${r.role} ${r.accuracy}%` : '--';
  }

  const topSymEl = document.getElementById('topSymbolAcc');
  if (topSymEl) {
    const s = (at.symbols || [])[0];
    topSymEl.textContent = s ? `${s.symbol} ${s.accuracy}%` : '--';
  }

  const ts = document.getElementById('validationTimestamp');
  if (ts) {
    ts.textContent = `最后更新: ${new Date().toLocaleString('zh-CN')}`;
  }
}

/**
 * 更新指标摘要
 */
function updateMetricsSummary(data) {
  // API 调用
  const apiCalls5min = document.getElementById('apiCalls5min');
  if (apiCalls5min && data.api) {
    apiCalls5min.textContent = data.api.recent_5min_calls || 0;
  }

  // WebSocket 连接
  const wsTotal = data.websocket?.total || 0;

  // 系统运行时间
  const systemUptime = document.getElementById('systemUptime');
  if (systemUptime && data.uptime) {
    systemUptime.textContent = data.uptime;
  }

  // 检查告警
  checkAlerts(data);
}

/**
 * 更新详细指标
 */
function updateDetailedMetrics(data) {
  if (!data.metrics) return;

  const metrics = data.metrics;

  // API 统计
  const apiStats = metrics.api;
  const recent5min = apiStats?.recent_5min || {};

  // 更新 API 成功率
  const avgResponseTime = document.getElementById('avgResponseTime');
  if (avgResponseTime) {
    avgResponseTime.textContent = recent5min.avg_duration_ms
      ? `${recent5min.avg_duration_ms.toFixed(0)}ms`
      : '--';
  }

  // 信号统计
  const signalStats = metrics.signals;
  const recent1h = signalStats?.recent_1h || {};

  const signals1h = document.getElementById('signals1h');
  if (signals1h) {
    signals1h.textContent = recent1h.count || 0;
  }

  // 更新图表
  updateCharts(metrics);
}

/**
 * 更新成本指标
 */
function updateCostMetrics(data) {
  if (!data.today) return;

  // 今日成本
  const todayCost = document.getElementById('todayCost');
  if (todayCost) {
    todayCost.textContent = `\u00A5${data.today.estimated_cost_cny?.toFixed(4) || '0.0000'}`;
  }

  // 预估日成本
  const projectedDailyCost = document.getElementById('projectedDailyCost');
  if (projectedDailyCost && data.projected) {
    projectedDailyCost.textContent = `\u00A5${data.projected.daily_cost?.toFixed(4) || '0.0000'}`;
  }

  // 预估月成本
  const monthlyEstimate = document.getElementById('monthlyEstimate');
  if (monthlyEstimate && data.projected) {
    monthlyEstimate.textContent = `\u00A5${data.projected.monthly_estimate?.toFixed(2) || '0.00'}`;
  }
}

/**
 * 更新配额趋势
 */
function updateQuotaTrend(data) {
  const summaryEl = document.getElementById('quotaTrendSummary');
  const chartEl = document.getElementById('quotaTrendChart');
  if (!summaryEl || !chartEl) return;

  const history = Array.isArray(data?.quota_history) ? data.quota_history : [];
  if (history.length === 0) {
    summaryEl.textContent = '暂无配额趋势数据';
    if (monitoringState.charts.quotaTrend) {
      monitoringState.charts.quotaTrend.destroy();
      monitoringState.charts.quotaTrend = null;
    }
    return;
  }

  const recent = history.slice(0, 7).reverse();
  const labels = recent.map((item) => (item.date || '--').slice(5));
  const values = recent.map((item) => Number(item.usage_percent || 0));
  const latest = recent[recent.length - 1] || { usage_percent: 0, total_calls: 0 };

  if (monitoringState.charts.quotaTrend) {
    monitoringState.charts.quotaTrend.destroy();
  }

  monitoringState.charts.quotaTrend = new Chart(chartEl, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: '使用率(%)',
        data: values,
        borderColor: '#f59e0b',
        backgroundColor: 'rgba(245, 158, 11, 0.18)',
        fill: true,
        tension: 0.32,
        pointRadius: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
      },
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          ticks: { color: _chartTickColor() },
          grid: { color: 'rgba(148, 163, 184, 0.1)' },
        },
        x: {
          ticks: { color: _chartTickColor() },
          grid: { color: 'rgba(148, 163, 184, 0.05)' },
        },
      },
    },
  });

  const lines = recent.map((item) => {
    const date = item.date || '--';
    const usage = Number(item.usage_percent || 0).toFixed(1);
    const total = Number(item.total_calls || 0);
    return `${date}: ${usage}% (${total} 次)`;
  });

  const usageAvg = values.length > 0
    ? values.reduce((sum, v) => sum + v, 0) / values.length
    : 0;
  if (window.innerWidth <= 480) {
    summaryEl.textContent = `最新 ${Number(latest.usage_percent || 0).toFixed(1)}% | 近7日均值 ${usageAvg.toFixed(1)}%`;
    return;
  }
  summaryEl.textContent = `最新：${Number(latest.usage_percent || 0).toFixed(1)}%（${Number(latest.total_calls || 0)} 次） | ${lines.join(' | ')}`;
}

/**
 * 更新性能指标
 */
function updatePerformanceMetrics(data) {
  if (!data.api_performance?.recent_5min?.latency_percentiles_ms) return;

  const percentiles = data.api_performance.recent_5min.latency_percentiles_ms;

  // 更新 API 延迟百分位数
  const p50El = document.getElementById('apiP50');
  const p90El = document.getElementById('apiP90');
  const p95El = document.getElementById('apiP95');
  const p99El = document.getElementById('apiP99');
  if (p50El) p50El.textContent = percentiles.p50?.toFixed(0) + 'ms' || '--';
  if (p90El) p90El.textContent = percentiles.p90?.toFixed(0) + 'ms' || '--';
  if (p95El) p95El.textContent = percentiles.p95?.toFixed(0) + 'ms' || '--';
  if (p99El) p99El.textContent = percentiles.p99?.toFixed(0) + 'ms' || '--';
}
