/**
 * 钢子出击 - 自动交易控制面板（入口文件）
 * 初始化、事件绑定、数据刷新协调、WS 处理、交易开关
 */
import { state, _throttle, _showTradeToast, _suppressHistorySoundBackfill } from './trading/utils.js';
import { addTradingStyles } from './trading/styles.js';
import { buildTradingHTML } from './trading/html-template.js';
import { renderAccountHero, renderBalances, _handleBalancePush } from './trading/balance.js';
import { renderPositions, _rerenderFromCache, renderSlPauseStatus } from './trading/positions.js';
import { renderTradeHistory, _renderTradeUnreadBadge, _handleOrderPush, maybePlayLatestFilledTradeSound } from './trading/orders.js';
import { renderStats, renderAccuracyFull, renderSuperbrain, loadSignalStats, renderEngineStatus } from './trading/stats.js';
import { renderAccuracyDailyTrend, renderDailyPnlChart, renderBenchmarkChart } from './trading/charts.js';

const API_BASE = state.API_BASE;

// ====== 初始化 ======
function initTradingPanel() {
  if (state._tradingInited) return;

  const container = document.getElementById('tradingPanelRoot');
  if (!container) return;

  container.innerHTML = buildTradingHTML();
  addTradingStyles();
  bindTradingEvents();
  refreshFastData();
  refreshSlowData();
  loadSignalStats();

  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission().catch(() => {});
  }

  state._fastTimer = setInterval(refreshFastData, 120000);
  state._slowTimer = setInterval(refreshSlowData, 120000);
  state._tradingInited = true;

  // WS 推送事件处理
  window.addEventListener('ws-position-update', _throttle(() => { _wsRefreshPositions(); }, 500));
  window.addEventListener('ws-balance-update',  _handleBalancePush);
  window.addEventListener('ws-order-update',    _throttle(() => { _wsRefreshAfterOrder(); }, 500));
  window.addEventListener('ws-order-update',    _handleOrderPush);
  window.addEventListener('ws-trade-status',    _throttle(() => { _wsRefreshAfterOrder(); }, 300));

  // 初始化分析流水
  if (window.GangziApp && window.GangziApp.initAnalysisFeed) {
    window.GangziApp.initAnalysisFeed();
  }
}

// ====== 交易开关 UI ======
function setTradeTogglePending(isPending, labelText) {
  if (labelText === undefined) labelText = '切换中...';
  const btn = document.getElementById('tradeToggleBtn');
  if (!btn) return;
  const toggleIcon = document.getElementById('toggleIcon');
  const toggleText = document.getElementById('toggleText');

  if (isPending) {
    btn.classList.add('pending');
    btn.disabled = true;
    if (toggleIcon) toggleIcon.innerHTML = '<i class="ri-loader-4-line"></i>';
    if (toggleText) toggleText.textContent = labelText;
    return;
  }

  btn.classList.remove('pending');
  btn.disabled = true;
}

function renderTradeToggle(data) {
  const badge = document.getElementById('tradeStatusBadge');
  const btn = document.getElementById('tradeToggleBtn');
  const toggleIcon = document.getElementById('toggleIcon');
  const toggleText = document.getElementById('toggleText');

  const enabled = data.trade_enabled;
  const active = data.runtime_active;
  const exchConn = data.exchange_connected !== false;
  const balWarn = data.balance_warning === true;

  if (badge) {
    if (!enabled) { badge.textContent = '未启用'; badge.className = 'badge badge-gray'; }
    else if (!exchConn) { badge.textContent = '交易所断开'; badge.className = 'badge badge-red'; }
    else if (balWarn) { badge.textContent = '余额不足'; badge.className = 'badge badge-yellow'; }
    else if (active) { badge.textContent = '运行中'; badge.className = 'badge badge-green'; }
    else { badge.textContent = '已暂停'; badge.className = 'badge badge-yellow'; }
  }

  if (btn) {
    btn.classList.remove('active', 'paused', 'disabled');
    if (!enabled) {
      btn.classList.add('disabled'); btn.disabled = true;
      if (toggleIcon) toggleIcon.innerHTML = '<i class="ri-lock-line"></i>';
      if (toggleText) toggleText.textContent = '未启用';
    } else if (active) {
      btn.classList.add('active'); btn.disabled = false;
      if (toggleIcon) toggleIcon.innerHTML = '<i class="ri-pause-line"></i>';
      if (toggleText) toggleText.textContent = '暂停交易';
    } else {
      btn.classList.add('paused'); btn.disabled = false;
      if (toggleIcon) toggleIcon.innerHTML = '<i class="ri-play-line"></i>';
      if (toggleText) toggleText.textContent = '恢复交易';
    }
  }
}

// ====== 确认弹窗 ======
function ensureGzModal() {
  const existing = document.getElementById('gzModalOverlay');
  if (existing) return existing;

  const overlay = document.createElement('div');
  overlay.id = 'gzModalOverlay';
  overlay.className = 'gz-modal-overlay';
  overlay.innerHTML = `
    <div class="gz-modal" role="dialog" aria-modal="true" aria-labelledby="gzModalTitle">
      <div class="gz-modal-head" id="gzModalTitle">确认</div>
      <div class="gz-modal-body" id="gzModalBody">--</div>
      <div class="gz-modal-actions">
        <button type="button" class="gz-btn" id="gzModalCancel">取消</button>
        <button type="button" class="gz-btn gz-btn-danger" id="gzModalOk">确认</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      const cancel = document.getElementById('gzModalCancel');
      if (cancel) cancel.click();
    }
  });

  return overlay;
}

function gzConfirm(opts) {
  const title = (opts && opts.title) || '确认';
  const message = (opts && opts.message) || '';
  return new Promise((resolve) => {
    const overlay = ensureGzModal();
    const titleEl = document.getElementById('gzModalTitle');
    const bodyEl = document.getElementById('gzModalBody');
    const okBtn = document.getElementById('gzModalOk');
    const cancelBtn = document.getElementById('gzModalCancel');

    if (titleEl) titleEl.textContent = title;
    if (bodyEl) bodyEl.textContent = message;

    const cleanup = () => {
      overlay.classList.remove('show');
      if (okBtn) okBtn.onclick = null;
      if (cancelBtn) cancelBtn.onclick = null;
      document.removeEventListener('keydown', onKeyDown, true);
    };

    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        cleanup();
        resolve(false);
      }
    };
    document.addEventListener('keydown', onKeyDown, true);

    if (okBtn) {
      okBtn.onclick = () => {
        cleanup();
        resolve(true);
      };
    }
    if (cancelBtn) {
      cancelBtn.onclick = () => {
        cleanup();
        resolve(false);
      };
    }

    overlay.classList.add('show');
  });
}

// ====== 刷新状态 ======
async function refreshTradeStatusOnly() {
  const token = window.GangziApp?.getToken ? window.GangziApp.getToken() : '';
  if (!token) return false;
  const headers = { 'Authorization': `Bearer ${token}` };
  try {
    const resp = await fetch(`${API_BASE}/api/trade/status`, { headers });
    if (!resp.ok) return false;
    const d = await resp.json();
    renderTradeToggle(d);
    renderBalances(d.balances || {});
    return true;
  } catch (e) {
    return false;
  }
}

// ====== 事件绑定 ======
function bindTradingEvents() {
  const btn = document.getElementById('tradeToggleBtn');
  if (btn) {
    btn.addEventListener('click', async () => {
      if (btn.classList.contains('disabled')) return;
      if (state._tradeToggleBusy) return;
      state._tradeToggleBusy = true;
      setTradeTogglePending(true);
      try {
        const token = window.GangziApp?.getToken ? window.GangziApp.getToken() : '';
        const resp = await fetch(`${API_BASE}/api/trade/toggle`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
        });

        if (resp.status === 401) {
          _showTradeToast('登录已过期，请重新登录', 'error');
          return;
        }
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

        const result = await resp.json();
        const reason = result?.data?.reason || result?.reason || '';
        if (reason && reason !== 'ok') {
          _showTradeToast(result?.data?.message || result?.message || '操作失败', 'warning');
        } else {
          _showTradeToast(result?.data?.message || '操作成功', 'success');
        }

        const ok = await refreshTradeStatusOnly();
        if (!ok) await refreshTradingData();
        loadSignalStats();
        window.setTimeout(() => { if (state._tradingInited) refreshTradeStatusOnly(); }, 800);
        window.setTimeout(() => { if (state._tradingInited) refreshTradeStatusOnly(); }, 2000);
      } catch (e) {
        console.warn('[交易面板] toggle 失败:', e);
        _showTradeToast('网络请求失败，请检查网络后重试', 'error');
      } finally {
        setTradeTogglePending(false);
        state._tradeToggleBusy = false;
      }
    });
  }

  const group = document.getElementById('tradeAccFilterGroup');
  if (group) {
    group.addEventListener('click', async (e) => {
      const btnEl = e.target.closest('.acc-filter-btn');
      if (!btnEl) return;
      const days = parseInt(btnEl.dataset.days, 10) || 0;
      state._tradeAccDays = days;
      group.querySelectorAll('.acc-filter-btn').forEach((b) => b.classList.remove('active'));
      btnEl.classList.add('active');
      await refreshAccuracyOnly();
    });
  }

  // 一键平仓按钮
  const closeAllBtn = document.getElementById('closeAllBtn');
  if (closeAllBtn) {
    closeAllBtn.addEventListener('click', async () => {
      if (closeAllBtn.disabled) return;
      const ok = await gzConfirm({
        title: '\u26a0\ufe0f 确认一键平仓？',
        message: '此操作将立即以市价平掉全部多仓和空仓。\n\n确认继续？',
      });
      if (!ok) return;

      closeAllBtn.disabled = true;
      closeAllBtn.innerHTML = '<i class="ri-loader-4-line"></i> 平仓中...';

      try {
        const token = window.GangziApp?.getToken ? window.GangziApp.getToken() : '';
        const resp = await fetch(`${API_BASE}/api/trade/close-all`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
        });
        const data = await resp.json();
        if (data.code === 0) {
          const msg = data.message || `已平仓 ${data.closed} 个仓位`;
          alert('\u2705 ' + msg);
          _suppressHistorySoundBackfill();
          refreshTradingData();
          loadSignalStats();
        } else {
          alert('\u274c 平仓失败: ' + (data.message || '未知错误'));
        }
      } catch (e) {
        alert('\u274c 请求失败: ' + e.message);
      } finally {
        closeAllBtn.disabled = false;
        closeAllBtn.innerHTML = '<i class="ri-close-circle-line"></i> 一键平仓';
      }
    });
  }
}

// ====== 准确率刷新 ======
async function refreshAccuracyOnly() {
  const token = window.GangziApp?.getToken ? window.GangziApp.getToken() : '';
  if (!token) return;
  const headers = { 'Authorization': `Bearer ${token}` };
  const url = state._tradeAccDays > 0
    ? `${API_BASE}/api/ai/accuracy?days=${state._tradeAccDays}`
    : `${API_BASE}/api/ai/accuracy`;

  const seq = ++state._accuracyRefreshSeq;
  try {
    const resp = await fetch(url, { headers });
    if (!resp.ok) return;
    const accData = await resp.json();
    if (seq !== state._accuracyRefreshSeq) return;
    const acc = accData.data || accData;
    if (acc.total_signals > 0) {
      renderAccuracyFull(acc);
    }
    renderAccuracyDailyTrend(acc);
  } catch (e) {
    console.warn('[交易面板] accuracy 刷新失败:', e);
  }
}

// ============ WS 推送处理 ============

async function _wsRefreshPositions() {
  const token = window.GangziApp?.getToken ? window.GangziApp.getToken() : '';
  if (!token) return;
  const headers = { 'Authorization': `Bearer ${token}` };
  try {
    const [statusResp, posResp] = await Promise.allSettled([
      fetch(`${API_BASE}/api/trade/status`, { headers }),
      fetch(`${API_BASE}/api/trade/positions`, { headers }),
    ]);
    if (statusResp.status === 'fulfilled' && statusResp.value.ok) {
      const d = await statusResp.value.json();
      renderTradeToggle(d);
      renderBalances(d.balances || {});
    }
    if (posResp.status === 'fulfilled' && posResp.value.ok) {
      const d = await posResp.value.json();
      renderPositions(d);
      renderAccountHero(d);
    }
  } catch (e) { console.warn('[WS持仓] 刷新失败:', e); }
}

async function _wsRefreshAfterOrder() {
  const token = window.GangziApp?.getToken ? window.GangziApp.getToken() : '';
  if (!token) return;
  const headers = { 'Authorization': `Bearer ${token}` };
  try {
    const [posResp, histResp] = await Promise.allSettled([
      fetch(`${API_BASE}/api/trade/positions`, { headers }),
      fetch(`${API_BASE}/api/trade/history?today=1&status=filled&limit=2000`, { headers }),
    ]);
    if (posResp.status === 'fulfilled' && posResp.value.ok) {
      const d = await posResp.value.json();
      renderPositions(d);
      renderAccountHero(d);
    }
    if (histResp.status === 'fulfilled' && histResp.value.ok) {
      const d = await histResp.value.json();
      renderTradeHistory(d);
    }
  } catch (e) { console.warn('[WS订单] 刷新失败:', e); }
}

// ============ 全量刷新 ============
async function refreshFastData() {
  const token = window.GangziApp?.getToken ? window.GangziApp.getToken() : '';
  if (!token) return;
  const headers = { 'Authorization': `Bearer ${token}` };
  const seq = ++state._fastRefreshSeq;
  try {
    const [statusResp, posResp, histResp, engineResp, pnlResp, benchResp] = await Promise.allSettled([
      fetch(`${API_BASE}/api/trade/status`, { headers }),
      fetch(`${API_BASE}/api/trade/positions`, { headers }),
      fetch(`${API_BASE}/api/trade/history?today=1&status=filled&limit=2000`, { headers }),
      fetch(`${API_BASE}/api/trade/engine-status`, { headers }),
      fetch(`${API_BASE}/api/analytics/daily-pnl`, { headers }),
      fetch(`${API_BASE}/api/analytics/benchmark?days=30`, { headers }),
    ]);

    if (seq !== state._fastRefreshSeq) return;

    if (statusResp.status === 'fulfilled' && statusResp.value.ok) {
      const d = await statusResp.value.json();
      if (seq !== state._fastRefreshSeq) return;
      renderTradeToggle(d);
      renderBalances(d.balances || {});
    }
    if (posResp.status === 'fulfilled' && posResp.value.ok) {
      const d = await posResp.value.json();
      if (seq !== state._fastRefreshSeq) return;
      renderPositions(d);
      renderAccountHero(d);
    }
    if (histResp.status === 'fulfilled' && histResp.value.ok) {
      const d = await histResp.value.json();
      if (seq !== state._fastRefreshSeq) return;
      renderTradeHistory(d);
      if (Date.now() >= state._historySoundSuppressUntil) {
        maybePlayLatestFilledTradeSound(d);
      }
    }

    try {
      if (engineResp.status === 'fulfilled' && engineResp.value.ok) {
        const ed = await engineResp.value.json();
        if (seq !== state._fastRefreshSeq) return;
        renderEngineStatus((ed.data || ed).symbols || ed.symbols || []);
      }
    } catch(_e) { console.warn('[引擎状态] 渲染失败:', _e); }
    try {
      if (pnlResp.status === 'fulfilled' && pnlResp.value.ok) {
        const pd = await pnlResp.value.json();
        if (seq !== state._fastRefreshSeq) return;
        renderDailyPnlChart((pd.data || pd).rows || pd.rows || []);
      }
    } catch(_e) { console.warn('[净值曲线] 渲染失败:', _e); }
    try {
      if (benchResp.status === 'fulfilled' && benchResp.value.ok) {
        const bd = await benchResp.value.json();
        if (seq !== state._fastRefreshSeq) return;
        renderBenchmarkChart(bd.data || bd);
      }
    } catch(_e) { console.warn('[策略对比] 渲染失败:', _e); }

  } catch (e) {
    console.warn('[交易面板] 快速刷新失败:', e);
  }
}

async function refreshSlowData() {
  if (document.hidden) return;
  const token = window.GangziApp?.getToken ? window.GangziApp.getToken() : '';
  if (!token) return;
  const headers = { 'Authorization': `Bearer ${token}` };

  fetch(`${API_BASE}/api/trade/stats`, { headers })
    .then(r => r.ok ? r.json() : null)
    .then(d => {
      try { if (d) { renderStats(d); renderSlPauseStatus(d.sl_protection); } }
      catch(e) { console.warn('[交易统计] 渲染异常:', e); }
    })
    .catch(e => { console.warn('[交易统计] 请求失败:', e); });

  fetch(state._tradeAccDays > 0 ? `${API_BASE}/api/ai/accuracy?days=${state._tradeAccDays}` : `${API_BASE}/api/ai/accuracy`, { headers })
    .then(r => r.ok ? r.json() : Promise.reject('http'))
    .then(d => {
      try {
        const acc = d?.data || d;
        if (acc && acc.total_signals > 0) renderAccuracyFull(acc);
        if (acc) renderAccuracyDailyTrend(acc);
      } catch(e) { console.warn('[AI准确率] 渲染异常:', e); }
    })
    .catch(e => { console.warn('[AI准确率] 请求失败:', e); });

  fetch(`${API_BASE}/api/ai/superbrain`, { headers })
    .then(r => r.ok ? r.json() : Promise.reject('http'))
    .then(d => {
      try { if (d) renderSuperbrain(d.data || d); }
      catch(e) { console.warn('[最强大脑] 渲染异常:', e); }
    })
    .catch(e => { console.warn('[最强大脑] 请求失败:', e); });

  if (window.fetchValidationMetrics) {
    window.fetchValidationMetrics(token).catch(() => {});
  }
}

async function refreshTradingData() {
  await Promise.allSettled([refreshFastData(), refreshSlowData()]);
}

// ==== 导出到全局 ====
window.GangziApp = window.GangziApp || {};
window.GangziApp.destroyTradingCharts = function() {
  if (state._tradeAccDailyChart) { state._tradeAccDailyChart.destroy(); state._tradeAccDailyChart = null; }
  if (state._dailyPnlChartInst) { state._dailyPnlChartInst.destroy(); state._dailyPnlChartInst = null; }
  if (state._benchmarkChartInst) { state._benchmarkChartInst.destroy(); state._benchmarkChartInst = null; }
};
window.GangziApp.clearTradingTimers = function() {
  if (state._fastTimer) { clearInterval(state._fastTimer); state._fastTimer = null; }
  if (state._slowTimer) { clearInterval(state._slowTimer); state._slowTimer = null; }
};

window.initTradingPanel = initTradingPanel;

// positions.js closeSinglePosition 需要调用 refreshTradingData
window._refreshTradingData = refreshTradingData;

// 页面可见性切换
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    // 后台不暂停定时器
  } else if (state._tradingInited) {
    state._tradeUnreadCount = 0;
    _renderTradeUnreadBadge();
    const posList = document.getElementById('positionList');
    if (posList) {
      posList.dataset.renderSig = 'syncing';
      posList.innerHTML = '<div class="no-data" style="font-size:13px;">同步中...</div>';
    }
    refreshFastData();
    refreshSlowData();
    _wsRefreshAfterOrder();
    if (!state._fastTimer) {
      state._fastTimer = setInterval(refreshFastData, 120000);
    }
    if (!state._slowTimer) {
      state._slowTimer = setInterval(refreshSlowData, 120000);
    }
  }
});
