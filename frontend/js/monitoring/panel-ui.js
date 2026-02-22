/**
 * 钢子出击 - 监控面板 UI 模块
 * 面板创建、样式注入、事件绑定、通知管理
 */
import { monitoringState } from '../monitoring.js';

// ---------------------------------------------------------------------------
// 面板创建
// ---------------------------------------------------------------------------

/**
 * 创建监控面板 HTML
 */
export function createMonitoringPanel() {
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

// ---------------------------------------------------------------------------
// 样式注入
// ---------------------------------------------------------------------------

/**
 * 添加监控面板样式
 */
export function addMonitoringStyles() {
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

// ---------------------------------------------------------------------------
// 事件绑定
// ---------------------------------------------------------------------------

/**
 * 绑定监控事件
 */
export function bindMonitoringEvents() {
  // Tab 切换时刷新数据（通过 window 引用避免循环依赖）
  const adminTab = document.querySelector('[data-tab="admin"]');
  if (adminTab) {
    adminTab.addEventListener('click', () => {
      if (typeof window.refreshMonitoringData === 'function') {
        window.refreshMonitoringData();
      }
    });
  }
}

// ---------------------------------------------------------------------------
// 通知管理
// ---------------------------------------------------------------------------

export function setMonitoringNotice(message, retryable = true) {
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
        if (typeof window.refreshMonitoringData === 'function') {
          window.refreshMonitoringData();
        }
      }, { once: true });
    }
  }
}

export function clearMonitoringNotice() {
  const notice = document.getElementById('monitoringNotice');
  if (!notice) return;
  monitoringState.lastNoticeText = '';
  notice.classList.add('hidden');
  notice.innerHTML = '';
}
