/**
 * 钢子出击 - 交易面板余额/账户模块
 * 余额渲染、账户英雄区、余额推送处理
 */
import { state } from './utils.js';

// ====== 渲染：账户英雄区 ======
export function renderAccountHero(posData) {
  const summary = posData.summary || {};
  const totalValue = document.getElementById('totalAssetValue');
  const totalPnl = document.getElementById('totalPnlText');
  const usdtFree = document.getElementById('usdtFreeText');
  const posValue = document.getElementById('positionValueText');
  const costText = document.getElementById('totalCostText');
  const floatPnl = document.getElementById('floatPnlText');

  const cost = summary.total_cost || 0;
  const pnl = summary.total_pnl || 0;

  // 重要：不要用含杠杆的名义市值（notional）做"总资产"。
  // 用账户权益口径：USDT 总余额（free+used） + 未实现盈亏。
  const usdtParsed = parseFloat(usdtFree?.dataset?.usdtTotal || usdtFree?.dataset?.raw || '0');
  if (Number.isFinite(usdtParsed)) {
    state._usdtTotalReady = true;
    state._lastUsdtTotal = usdtParsed;
  }
  const usdtTotalVal = Number.isFinite(usdtParsed) ? usdtParsed : state._lastUsdtTotal;
  const totalAsset = usdtTotalVal + pnl;

  if (totalValue) totalValue.textContent = `$${totalAsset.toLocaleString('en', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

  if (totalPnl) {
    const sign = pnl >= 0 ? '+' : '';
    const denom = usdtTotalVal > 0 ? usdtTotalVal : 0;
    const pnlPctEquity = denom > 0 ? (pnl / denom * 100) : 0;
    totalPnl.textContent = `浮动盈亏 ${sign}$${pnl.toFixed(2)} (${sign}${pnlPctEquity.toFixed(2)}%)`;
    totalPnl.className = `account-hero-sub ${pnl > 0 ? 'profit' : pnl < 0 ? 'loss' : 'neutral'}`;
  }
  if (posValue) posValue.textContent = `$${cost.toFixed(2)}`;
  const marketVal = summary.total_value || 0;
  if (costText) costText.textContent = `$${marketVal.toFixed(2)}`;
  if (floatPnl) {
    const sign = pnl >= 0 ? '+' : '';
    floatPnl.textContent = `${sign}$${pnl.toFixed(2)}`;
    floatPnl.style.color = pnl > 0 ? 'var(--green)' : pnl < 0 ? 'var(--red)' : 'var(--text)';
  }
}

// ====== 渲染：余额 ======
export function renderBalances(balances) {
  if (!balances || Object.keys(balances).length === 0) return;

  const usdtInfo = balances.USDT || balances['USDT'] || { free: 0, used: 0 };
  const free = Number(usdtInfo.free || 0);
  const used = Number(usdtInfo.used || 0);
  const total = free + used;

  const _uf = document.getElementById('usdtFreeText');
  if (_uf) {
    _uf.textContent = '$' + free.toFixed(2);
    _uf.dataset.raw = String(free);
    _uf.dataset.usdtTotal = String(total);
  }
}

// ====== WS 余额推送处理 ======
export function _handleBalancePush(e) {
  const balances = e.detail;
  if (!balances || typeof balances !== 'object') return;

  const usdt = balances['USDT'] || balances['usdt'];
  if (!usdt) return;

  const total = parseFloat(usdt.balance || 0);
  const free = parseFloat(usdt.cross_wallet || total);

  const el = document.getElementById('usdtFreeText');
  if (el) {
    el.textContent = '$' + free.toFixed(2);
    el.dataset.raw = String(free);
    el.dataset.usdtTotal = String(total);
  }
  if (Number.isFinite(total)) {
    state._usdtTotalReady = true;
    state._lastUsdtTotal = total;
  }
}
