/**
 * 钢子出击 · 用户设置页面 (ES Module)
 * 复用主站样式体系 + 主题同步
 */
import {
    API_BASE,
    getToken,
    checkAuth,
    clearToken,
    authFetch,
} from './auth.js';

const PRESETS = {
  steady: {
    amount_usdt: 50, amount_pct: 3, max_position_usdt: 500, max_position_pct: 20,
    daily_limit_usdt: 500, min_confidence: 65, cooldown_seconds: 600,
    leverage: 2, margin_mode: 'isolated',
    take_profit_pct: 3, stop_loss_pct: 1.5, trailing_stop_enabled: true,
    position_timeout_hours: 24,
  },
  aggressive: {
    amount_usdt: 200, amount_pct: 8, max_position_usdt: 1000, max_position_pct: 40,
    daily_limit_usdt: 2000, min_confidence: 40, cooldown_seconds: 180,
    leverage: 5, margin_mode: 'isolated',
    take_profit_pct: 6, stop_loss_pct: 3, trailing_stop_enabled: true,
    position_timeout_hours: 48,
  },
};

const FIELD_IDS = [
  'amount_usdt', 'amount_pct', 'max_position_usdt', 'max_position_pct',
  'daily_limit_usdt', 'min_confidence', 'cooldown_seconds', 'leverage',
  'margin_mode', 'take_profit_pct', 'stop_loss_pct', 'trailing_stop_enabled',
  'position_timeout_hours', 'tg_enabled', 'tg_chat_id',
];

let currentMode = 'steady';
let currentSymbols = [];

// ── Toast（复用主站 .app-toast） ─────────────────────
function showToast(msg) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove('show'), 2500);
}

// ── HTML 转义 ────────────────────────────────────────
function esc(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

// ── 主题同步（从 localStorage 读取主站设置） ─────────
function syncTheme() {
  const saved = localStorage.getItem('gangzi-theme');
  const btn = document.getElementById('themeToggle');
  if (saved === 'light') {
    document.body.classList.add('light-theme');
    if (btn) btn.innerHTML = '<i class="ri-moon-line"></i>';
  }
  if (btn) {
    btn.addEventListener('click', () => {
      document.body.classList.add('theme-transition');
      const isLight = document.body.classList.toggle('light-theme');
      btn.innerHTML = isLight ? '<i class="ri-moon-line"></i>' : '<i class="ri-sun-line"></i>';
      localStorage.setItem('gangzi-theme', isLight ? 'light' : 'dark');
      setTimeout(() => document.body.classList.remove('theme-transition'), 400);
    });
  }
}

// ── 初始化 ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  syncTheme();

  // 顶部时间（最先执行，不依赖任何东西）
  try {
    const timeEl = document.getElementById('headerTime');
    if (timeEl) {
      const tick = () => { timeEl.textContent = new Date().toLocaleString('zh-CN', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit' }); };
      tick(); setInterval(tick, 1000);
    }
  } catch(e) { console.warn('time init error', e); }

  // 绑定所有 UI 事件
  try {
    bindModeSwitcher();
    document.getElementById('saveBtn').addEventListener('click', saveSettings);
    bindPasswordForm();
    bindSymbolInput();
  } catch(e) { console.warn('bindUI error', e); }

  // 鉴权
  const token = getToken();
  if (!token) { window.location.href = '/login.html'; return; }
  const valid = await checkAuth();
  if (!valid) return;

  // 加载数据
  await loadSettings();
  await loadSlProtection();
});

// ── 加载设置 ─────────────────────────────────────────
export async function loadSettings() {
  try {
    const resp = await authFetch(`${API_BASE}/api/settings`);
    if (!resp.ok) throw new Error('加载失败');
    const data = await resp.json();
    currentMode = data.strategy_mode || 'steady';
    fillForm(data);
    highlightMode(currentMode);
    currentSymbols = data.symbols ? data.symbols.split(',').map(s => s.trim()).filter(Boolean) : [];
    renderSymbolTags();
  } catch (e) {
    showToast('加载设置失败: ' + e.message);
  }
}

function fillForm(data) {
  FIELD_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.type === 'checkbox') { el.checked = !!data[id]; }
    else if (el.tagName === 'SELECT') { el.value = data[id] || el.options[0].value; }
    else { el.value = data[id] ?? ''; }
  });
}

// ── 止损防护配置加载 ────────────────────────────────
async function loadSlProtection() {
  try {
    const resp = await authFetch(`${API_BASE}/api/trade/sl-protection`);
    if (!resp.ok) return;
    const data = await resp.json();
    const cfg = data.config || {};
    const el1 = document.getElementById('sl_cooldown_multiplier');
    const el2 = document.getElementById('max_consecutive_sl');
    const el3 = document.getElementById('sl_pause_minutes');
    if (el1) el1.value = cfg.sl_cooldown_multiplier ?? 2;
    if (el2) el2.value = cfg.max_consecutive_sl ?? 3;
    if (el3) el3.value = cfg.sl_pause_minutes ?? 30;
  } catch (e) {
    console.warn('loadSlProtection error', e);
  }
}

async function saveSlProtection() {
  const payload = {};
  const el1 = document.getElementById('sl_cooldown_multiplier');
  const el2 = document.getElementById('max_consecutive_sl');
  const el3 = document.getElementById('sl_pause_minutes');
  if (el1) payload.sl_cooldown_multiplier = parseFloat(el1.value) || 2;
  if (el2) payload.max_consecutive_sl = parseInt(el2.value) || 3;
  if (el3) payload.sl_pause_minutes = parseInt(el3.value) || 30;
  await authFetch(`${API_BASE}/api/trade/sl-protection`, {
    method: 'PUT', body: JSON.stringify(payload),
  });
}

// ── 策略模式 ─────────────────────────────────────────
function bindModeSwitcher() {
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      currentMode = btn.dataset.mode;
      highlightMode(currentMode);
      if (PRESETS[currentMode]) fillForm(PRESETS[currentMode]);
    });
  });
}

function highlightMode(mode) {
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });
}

// ── 保存 ─────────────────────────────────────────────
function collectFormData() {
  const payload = { strategy_mode: currentMode };
  FIELD_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.type === 'checkbox') { payload[id] = el.checked; }
    else if (el.tagName === 'SELECT') { payload[id] = el.value; }
    else {
      const v = parseFloat(el.value);
      payload[id] = isNaN(v) ? el.value : v;
    }
  });
  payload.symbols = currentSymbols.join(',');
  return payload;
}

export async function saveSettings() {
  const btn = document.getElementById('saveBtn');
  btn.classList.add('saving');
  btn.innerHTML = '<i class="ri-loader-4-line"></i> 保存中...';
  try {
    const resp = await authFetch(`${API_BASE}/api/settings`, {
      method: 'PUT', body: JSON.stringify(collectFormData()),
    });
    if (!resp.ok) {
      const e = await resp.json().catch(() => ({}));
      throw new Error(e.detail || e.message || '保存失败');
    }
    const result = await resp.json();
    currentMode = result.strategy_mode || currentMode;
    highlightMode(currentMode);
    await saveSlProtection();
    showToast('设置已保存');
  } catch (e) {
    showToast('保存失败: ' + e.message);
  } finally {
    btn.classList.remove('saving');
    btn.innerHTML = '<i class="ri-save-line"></i> 保存设置';
  }
}

// ── 币种标签 ─────────────────────────────────────────
function renderSymbolTags() {
  const c = document.getElementById('symbolsTags');
  c.innerHTML = currentSymbols.map(s =>
    `<span class="symbol-tag">${esc(s)}<span class="remove-sym" data-sym="${esc(s)}">&times;</span></span>`
  ).join('');
  c.querySelectorAll('.remove-sym').forEach(el => {
    el.addEventListener('click', () => {
      currentSymbols = currentSymbols.filter(s => s !== el.dataset.sym);
      renderSymbolTags();
    });
  });
}

function bindSymbolInput() {
  const input = document.getElementById('symbolInput');
  const addBtn = document.getElementById('addSymbolBtn');
  const doAdd = () => {
    const val = input.value.trim().toUpperCase();
    if (!val) return;
    if (!val.endsWith('USDT')) { showToast('请输入 USDT 交易对'); return; }
    if (currentSymbols.includes(val)) { showToast('已存在'); return; }
    currentSymbols.push(val);
    renderSymbolTags();
    input.value = '';
  };
  addBtn.addEventListener('click', doAdd);
  input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); doAdd(); } });
}

// ── 修改密码 ─────────────────────────────────────────
function bindPasswordForm() {
  const showBtn = document.getElementById('changePwdBtn');
  const form = document.getElementById('pwdForm');
  const cancelBtn = document.getElementById('cancelPwdBtn');
  const submitBtn = document.getElementById('submitPwdBtn');

  showBtn.addEventListener('click', () => { form.classList.remove('hidden'); showBtn.style.display = 'none'; });
  cancelBtn.addEventListener('click', () => { form.classList.add('hidden'); showBtn.style.display = ''; clearPwd(); });

  submitBtn.addEventListener('click', async () => {
    const oldPwd = document.getElementById('oldPassword').value;
    const newPwd = document.getElementById('newPassword').value;
    const confirmPwd = document.getElementById('confirmPassword').value;
    if (!oldPwd || !newPwd) { showToast('请填写完整'); return; }
    if (newPwd.length < 6) { showToast('新密码至少 6 位'); return; }
    if (newPwd !== confirmPwd) { showToast('两次密码不一致'); return; }

    submitBtn.disabled = true; submitBtn.textContent = '提交中...';
    try {
      const resp = await authFetch(`${API_BASE}/api/settings/change-password`, {
        method: 'POST', body: JSON.stringify({ old_password: oldPwd, new_password: newPwd }),
      });
      if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || '修改失败'); }
      showToast('密码已修改，2秒后跳转登录');
      clearPwd(); form.classList.add('hidden'); showBtn.style.display = '';
      setTimeout(() => { clearToken(); window.location.href = '/login.html'; }, 2000);
    } catch (e) { showToast(e.message); }
    finally { submitBtn.disabled = false; submitBtn.textContent = '确认修改'; }
  });
}

function clearPwd() {
  ['oldPassword', 'newPassword', 'confirmPassword'].forEach(id => { document.getElementById(id).value = ''; });
}
