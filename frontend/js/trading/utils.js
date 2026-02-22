/**
 * 钢子出击 - 交易面板工具函数 & 共享状态
 * 所有交易面板子模块共享的基础工具和状态容器
 */

// ============ 价格格式化 ============
export function _fmtPrice(value, zeroAsEmpty) {
    const n = Number(value);
    if (!isFinite(n) || n === 0) return zeroAsEmpty ? '--' : '$0.00';
    const abs = Math.abs(n);
    let dp;
    if (abs >= 1000) dp = 0;
    else if (abs >= 1) dp = 2;
    else if (abs >= 0.01) dp = 4;
    else dp = 6;
    if (dp === 0) return '$' + n.toLocaleString('en-US', {maximumFractionDigits:0});
    return '$' + n.toFixed(dp);
}

// HTML onclick 仍需全局访问
window._fmtPrice = _fmtPrice;

// ============ 共享状态 ============
export const state = {
  API_BASE: window.API_BASE || window.location.origin,
  _isMobileTP: /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent),
  _fastTimer: null,
  _slowTimer: null,
  _tradingInited: false,
  _tradeSoundPrimed: false,
  _tradeUnreadCount: 0,
  _tradeAccDays: 1, // 0=全部, 1=今日, 7=最近7天（默认今日）
  _tradeAccDailyChart: null,
  _tradeToggleBusy: false,
  _fastRefreshSeq: 0,
  _usdtTotalReady: false,
  _lastUsdtTotal: 0,
  LAST_TRADE_SOUND_KEY: 'gangzi_trade_last_sound_key',
  MAX_TRADE_SOUND_BACKFILL: 2,
  _tradeUnreadOrderIds: new Set(),
  _historySoundSuppressUntil: 0,
  _accuracyRefreshSeq: 0,
  _lastTradeData: null,
  _dailyPnlChartInst: null,
  _benchmarkChartInst: null,
};

// ============ 工具函数 ============

export function _suppressHistorySoundBackfill(ms) {
  if (ms === undefined) ms = 180000;
  state._historySoundSuppressUntil = Math.max(state._historySoundSuppressUntil, Date.now() + ms);
}

export function esc(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

export function _setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = String(val);
}

export function _timeAgo(date) {
  const now = new Date();
  const diff = Math.floor((now - date) / 1000);
  if (diff < 60) return `${diff}秒前`;
  if (diff < 3600) return `${Math.floor(diff/60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff/3600)}小时前`;
  return `${Math.floor(diff/86400)}天前`;
}

export function _throttle(fn, ms) {
  let last = 0;
  return function () {
    const now = Date.now();
    if (now - last >= ms) {
      last = now;
      fn();
    }
  };
}

export function _showTradeToast(message, type) {
  if (type === undefined) type = 'info';
  const colors = { success: '#22c55e', error: '#ef4444', warning: '#f59e0b', info: '#3b82f6' };
  const icons = { success: 'ri-check-line', error: 'ri-close-circle-line', warning: 'ri-alert-line', info: 'ri-information-line' };
  const toast = document.createElement('div');
  toast.style.cssText = `position:fixed;top:20px;left:50%;transform:translateX(-50%);z-index:10000;
    padding:12px 24px;border-radius:12px;font-size:14px;font-weight:500;color:#fff;
    background:${colors[type] || colors.info};box-shadow:0 8px 24px rgba(0,0,0,0.25);
    display:flex;align-items:center;gap:8px;animation:slideDown .3s ease;max-width:90vw;`;
  toast.innerHTML = `<i class="${icons[type] || icons.info}"></i><span>${esc(message)}</span>`;
  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity .3s'; setTimeout(() => toast.remove(), 300); }, 3500);
}
