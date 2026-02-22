/**
 * 钢子出击 - 监控面板模块
 * 系统健康状态、实时指标图表、告警提示
 */
import { API_BASE, getToken } from './auth.js';

const _MONITORING_API_BASE = API_BASE || window.location.origin;

// 监控面板状态
const monitoringState = {
  isInitialized: false,
  refreshInterval: null,
  charts: {},
  metricsHistory: [],
  maxHistoryPoints: 50,
  lastNoticeText: '',
};

/**
 * 初始化监控面板
 */
function _chartTickColor() { return document.body.classList.contains('light-theme') ? '#636366' : '#94a3b8'; }

export function initMonitoringPanel() {
  if (monitoringState.isInitialized) return;

  // 创建监控面板 HTML 结构
  createMonitoringPanel();

  // 绑定事件
  bindMonitoringEvents();

  // 初始加载数据
  refreshMonitoringData();

  // 设置定时刷新
  monitoringState.refreshInterval = setInterval(refreshMonitoringData, 10000);

  monitoringState.isInitialized = true;
}

/**
 * 创建监控面板 HTML
 */
function createMonitoringPanel() {
  const pageAdmin = document.getElementById('page-admin');
  if (!pageAdmin) return;

  // 哨兵：如果只剩部分节点（例如被误删/渲染中断），允许重建整套监控面板
  const existing = document.getElementById('monitoringPanel');
  if (existing) {
    const requiredIds = [
      'apiSuccessRateChart',
      'wsConnectionsChart',
      'alertContainer',
      'todayCost',
      'pfAgreedRate',
      'performanceTable',
    ];
    const missing = requiredIds.some((id) => !document.getElementById(id));
    if (!missing) return;

    // 清理已存在的监控面板节点，避免重复插入
    pageAdmin.querySelectorAll('[data-monitoring-panel="1"]').forEach((el) => el.remove());
  }

  // 在 API 配额监控之前插入监控面板
  const quotaPanel = pageAdmin.querySelector('#quotaPanel');
  if (!quotaPanel) return;

  const monitoringHTML = `
    <!-- 系统健康状态 -->
    <div class="card mb" id="monitoringPanel" data-monitoring-panel="1">
      <div class="card-head">
        <h3><i class="ri-heart-pulse-line"></i> 系统健康状态</h3>
        <span class="badge badge-blue" id="overallHealthStatus">检查中...</span>
      </div>
      <div class="card-body">
        <div class="monitoring-notice hidden" id="monitoringNotice"></div>
        <div class="health-grid" id="healthGrid">
          <div class="health-item loading">
            <div class="health-icon"><i class="ri-refresh-line"></i></div>
            <div class="health-name">数据库</div>
            <div class="health-status">检查中...</div>
          </div>
          <div class="health-item loading">
            <div class="health-icon"><i class="ri-refresh-line"></i></div>
            <div class="health-name">AI 服务</div>
            <div class="health-status">检查中...</div>
          </div>
          <div class="health-item loading">
            <div class="health-icon"><i class="ri-refresh-line"></i></div>
            <div class="health-name">行情 WebSocket</div>
            <div class="health-status">检查中...</div>
          </div>
        </div>
        <div class="health-timestamp" id="healthTimestamp">--</div>
      </div>
    </div>

    <!-- 实时指标图表 -->
    <div class="card mb" data-monitoring-panel="1">
      <div class="card-head">
        <h3><i class="ri-bar-chart-2-line"></i> 实时指标监控</h3>
        <span class="badge badge-cyan">实时</span>
      </div>
      <div class="card-body">
        <div class="metrics-grid">
          <div class="metric-chart-container">
            <h4>API 调用成功率 (5分钟)</h4>
            <div class="chart-h chart-h-200">
              <canvas id="apiSuccessRateChart"></canvas>
            </div>
          </div>
          <div class="metric-chart-container">
            <h4>WebSocket 连接数</h4>
            <div class="chart-h chart-h-200">
              <canvas id="wsConnectionsChart"></canvas>
            </div>
          </div>
        </div>
        <div class="metrics-summary" id="metricsSummary">
          <div class="metric-item">
            <span class="metric-label">API 调用 (5分钟)</span>
            <span class="metric-value" id="apiCalls5min">--</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">平均响应时间</span>
            <span class="metric-value" id="avgResponseTime">--</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">信号生成 (1小时)</span>
            <span class="metric-value" id="signals1h">--</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">系统运行时间</span>
            <span class="metric-value" id="systemUptime">--</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 告警提示区域 -->
    <div id="alertContainer" class="alert-container" data-monitoring-panel="1"></div>

    <!-- API 成本分析 -->
    <div class="card mb" data-monitoring-panel="1">
      <div class="card-head">
        <h3><i class="ri-money-dollar-circle-line"></i> API 成本分析</h3>
        <span class="badge badge-green">今日</span>
      </div>
      <div class="card-body">
        <div class="cost-analysis-grid" id="costAnalysisGrid">
          <div class="cost-item">
            <div class="cost-value" id="todayCost">--</div>
            <div class="cost-label">今日成本 (CNY)</div>
          </div>
          <div class="cost-item">
            <div class="cost-value" id="projectedDailyCost">--</div>
            <div class="cost-label">预估日成本 (CNY)</div>
          </div>
          <div class="cost-item">
            <div class="cost-value" id="monthlyEstimate">--</div>
            <div class="cost-label">预估月成本 (CNY)</div>
          </div>
        </div>
        <div class="cost-by-model" id="costByModel">
          <!-- 按模型成本详情 -->
        </div>
        <div class="quota-trend">
          <h4>近7天配额趋势</h4>
          <div class="chart-h chart-h-160">
            <canvas id="quotaTrendChart"></canvas>
          </div>
          <div class="quota-trend-summary" id="quotaTrendSummary">--</div>
        </div>
      </div>
    </div>

    <!-- 性能指标 -->
    <div class="card" data-monitoring-panel="1">
      <div class="card-head">
        <h3><i class="ri-speed-line"></i> 性能指标</h3>
        <span class="badge badge-purple">P50/P90/P99</span>
      </div>
      <div class="card-body">
        <div class="performance-table-container">
          <table class="performance-table" id="performanceTable">
            <thead>
              <tr>
                <th>指标</th>
                <th>P50</th>
                <th>P90</th>
                <th>P95</th>
                <th>P99</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>API 响应时间 (ms)</td>
                <td id="apiP50">--</td>
                <td id="apiP90">--</td>
                <td id="apiP95">--</td>
                <td id="apiP99">--</td>
              </tr>
              <tr>
                <td>HTTP 请求耗时 (ms)</td>
                <td id="httpP50">--</td>
                <td id="httpP90">--</td>
                <td id="httpP95">--</td>
                <td id="httpP99">--</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  // 插入到 quotaPanel 所属 card 容器之前（monitoringHTML 含多个顶级兄弟 div）
  const newPanel = document.createElement('div');
  newPanel.innerHTML = monitoringHTML;
  const fragment = document.createDocumentFragment();
  while (newPanel.firstElementChild) {
      fragment.appendChild(newPanel.firstElementChild);
  }
  const quotaCard = quotaPanel.closest('.card') || quotaPanel.parentNode;
  const container = quotaCard.parentNode;
  container.insertBefore(fragment, quotaCard);

  // 添加样式
  addMonitoringStyles();
}

/**
 * 添加监控面板样式
 */
function addMonitoringStyles() {
  if (document.getElementById('monitoringStyles')) return;

  const styles = document.createElement('style');
  styles.id = 'monitoringStyles';
  styles.textContent = `
    /* 健康状态网格 */
    .health-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 16px;
      margin-bottom: 16px;
    }

    .health-item {
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 16px;
      border-radius: 12px;
      background: var(--bg-tertiary, rgba(30, 41, 59, 0.5));
      border: 1px solid var(--border-color, rgba(148, 163, 184, 0.1));
      transition: all 0.3s ease;
    }

    .health-item.healthy {
      border-color: rgba(34, 197, 94, 0.3);
      background: rgba(34, 197, 94, 0.1);
    }

    .health-item.degraded {
      border-color: rgba(234, 179, 8, 0.3);
      background: rgba(234, 179, 8, 0.1);
    }

    .health-item.unhealthy {
      border-color: rgba(239, 68, 68, 0.3);
      background: rgba(239, 68, 68, 0.1);
    }

    .health-item.loading {
      opacity: 0.7;
    }

    .health-icon {
      font-size: 24px;
      margin-bottom: 8px;
    }

    .health-name {
      font-size: 13px;
      color: var(--text-secondary, #94a3b8);
      margin-bottom: 4px;
    }

    .health-status {
      font-size: 14px;
      font-weight: 600;
    }

    .health-item.healthy .health-status { color: #22c55e; }
    .health-item.degraded .health-status { color: #eab308; }
    .health-item.unhealthy .health-status { color: #ef4444; }

    .health-timestamp {
      text-align: center;
      font-size: 12px;
      color: var(--text-secondary, #94a3b8);
    }

    .monitoring-notice {
      margin-bottom: 12px;
      padding: 10px 12px;
      border-radius: 8px;
      font-size: 12px;
      line-height: 1.5;
      border: 1px solid rgba(234, 179, 8, 0.35);
      background: rgba(234, 179, 8, 0.12);
      color: var(--yellow, #fcd34d);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .monitoring-notice.hidden {
      display: none;
    }

    .monitoring-notice button {
      border: 1px solid rgba(148, 163, 184, 0.35);
      background: rgba(15, 23, 42, 0.55);
      color: var(--text, #e2e8f0);
      border-radius: 6px;
      padding: 4px 10px;
      font-size: 12px;
      cursor: pointer;
      min-height: 32px;
    }

    /* 指标图表网格 */
    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 20px;
      margin-bottom: 20px;
    }

    .metric-chart-container h4 {
      font-size: 14px;
      color: var(--text-secondary, #94a3b8);
      margin-bottom: 12px;
    }

    /* 指标摘要 */
    .metrics-summary {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 16px;
      padding-top: 16px;
      border-top: 1px solid var(--border-color, rgba(148, 163, 184, 0.1));
    }

    .metric-item {
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
    }

    .metric-label {
      font-size: 12px;
      color: var(--text-secondary, #94a3b8);
      margin-bottom: 4px;
    }

    .metric-value {
      font-size: 20px;
      font-weight: 700;
      color: var(--text-primary, #f8fafc);
    }

    /* 成本分析 */
    .cost-analysis-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 16px;
      margin-bottom: 16px;
    }

    .cost-item {
      text-align: center;
      padding: 16px;
      border-radius: 12px;
      background: var(--bg-tertiary, rgba(30, 41, 59, 0.5));
    }

    .cost-value {
      font-size: 24px;
      font-weight: 700;
      color: var(--accent, #38bdf8);
      margin-bottom: 4px;
    }

    .cost-label {
      font-size: 12px;
      color: var(--text-secondary, #94a3b8);
    }

    .quota-trend {
      margin-top: 12px;
      padding: 10px 12px;
      background: rgba(56, 189, 248, 0.08);
      border: 1px solid rgba(56, 189, 248, 0.18);
      border-radius: 8px;
    }

    .quota-trend h4 {
      margin: 0 0 10px 0;
      font-size: 13px;
      color: var(--text-secondary, #94a3b8);
    }

    .quota-trend-summary {
      margin-top: 8px;
      font-size: 12px;
      color: var(--text-secondary, #94a3b8);
    }

    /* 告警容器 */
    .alert-container {
      margin-bottom: 16px;
    }

    .alert-item {
      display: flex;
      align-items: center;
      padding: 12px 16px;
      border-radius: 8px;
      margin-bottom: 8px;
      animation: slideIn 0.3s ease;
    }

    @keyframes slideIn {
      from {
        opacity: 0;
        transform: translateY(-10px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    .alert-item.critical {
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid rgba(239, 68, 68, 0.3);
    }

    .alert-item.warning {
      background: rgba(234, 179, 8, 0.15);
      border: 1px solid rgba(234, 179, 8, 0.3);
    }

    .alert-item.info {
      background: rgba(56, 189, 248, 0.15);
      border: 1px solid rgba(56, 189, 248, 0.3);
    }

    .alert-icon {
      font-size: 18px;
      margin-right: 12px;
    }

    .alert-content {
      flex: 1;
    }

    .alert-title {
      font-weight: 600;
      font-size: 14px;
      margin-bottom: 2px;
    }

    .alert-message {
      font-size: 12px;
      color: var(--text-secondary, #94a3b8);
    }

    .alert-close {
      background: none;
      border: none;
      color: var(--text-secondary, #94a3b8);
      cursor: pointer;
      font-size: 16px;
      padding: 4px;
    }

    /* 性能表格 */
    .performance-table-container {
      overflow-x: auto;
    }

    .performance-table {
      width: 100%;
      border-collapse: collapse;
    }

    .performance-table th,
    .performance-table td {
      padding: 12px;
      text-align: center;
      border-bottom: 1px solid var(--border-color, rgba(148, 163, 184, 0.1));
    }

    .performance-table th {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-secondary, #94a3b8);
      text-transform: uppercase;
    }

    .performance-table td {
      font-size: 14px;
      color: var(--text-primary, #f8fafc);
    }

    .performance-table tbody tr:hover {
      background: var(--bg-tertiary, rgba(30, 41, 59, 0.5));
    }
  `;

  document.head.appendChild(styles);
}

/**
 * 绑定监控事件
 */
function bindMonitoringEvents() {
  // Tab 切换时刷新数据
  const adminTab = document.querySelector('[data-tab="admin"]');
  if (adminTab) {
    adminTab.addEventListener('click', () => {
      refreshMonitoringData();
    });
  }
}

function setMonitoringNotice(message, retryable = true) {
  const notice = document.getElementById('monitoringNotice');
  if (!notice) return;

  if (message === monitoringState.lastNoticeText && !notice.classList.contains('hidden')) {
    return;
  }

  monitoringState.lastNoticeText = message;
  notice.classList.remove('hidden');
  notice.innerHTML = retryable
    ? `<span>${message}</span><button type="button" id="monitoringRetryBtn">立即重试</button>`
    : `<span>${message}</span>`;

  if (retryable) {
    const retryBtn = document.getElementById('monitoringRetryBtn');
    if (retryBtn) {
      retryBtn.addEventListener('click', () => {
        refreshMonitoringData();
      }, { once: true });
    }
  }
}

function clearMonitoringNotice() {
  const notice = document.getElementById('monitoringNotice');
  if (!notice) return;
  monitoringState.lastNoticeText = '';
  notice.classList.add('hidden');
  notice.innerHTML = '';
}

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

/**
 * 更新图表
 */
function updateCharts(metrics) {
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
function updateApiSuccessRateChart() {
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
function updateWsConnectionsChart() {
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

/**
 * 检查告警
 */
function checkAlerts(data) {
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

/**
 * 销毁监控面板
 */
export function destroyMonitoringPanel() {
  if (monitoringState.refreshInterval) {
    clearInterval(monitoringState.refreshInterval);
    monitoringState.refreshInterval = null;
  }

  // 销毁图表
  Object.values(monitoringState.charts).forEach(chart => {
    if (chart) chart.destroy();
  });
  monitoringState.charts = {};

  monitoringState.isInitialized = false;
}

// 保持全局兼容（HTML 事件处理器 + 其他非模块脚本引用）
window.initMonitoringPanel = initMonitoringPanel;
window.destroyMonitoringPanel = destroyMonitoringPanel;
window.refreshMonitoringData = refreshMonitoringData;
window.fetchValidationMetrics = fetchValidationMetrics;
