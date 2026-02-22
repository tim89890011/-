/**
 * 钢子出击 - 交易面板持仓管理模块
 * 持仓渲染、手动平仓、实时价格更新、止损暂停状态
 */
import { state, esc, _fmtPrice, _showTradeToast, _suppressHistorySoundBackfill } from './utils.js';
import { renderAccountHero } from './balance.js';

const API_BASE = state.API_BASE;

// ====== 渲染签名（去重） ======
function _positionsRenderSig(positions) {
  return positions.map(p => [
    p.symbol, p.side, p.quantity, p.avg_price, p.current_price,
    p.pnl, p.pnl_pct, p.market_value, p.liquidation_price, p.leverage
  ].join(':')).join('|');
}

// ====== 手动平仓单个仓位 ======
async function closeSinglePosition(symbol, side, event) {
  event.stopPropagation();
  const sideCn = side === 'long' ? '多' : '空';
  const coin = symbol.replace('USDT','').replace('/USDT:USDT','');
  if (!confirm('确定平仓 ' + coin + ' ' + sideCn + '仓？')) return;
  const rawSymbol = symbol.replace('/USDT:USDT','USDT').replace('/USDT','USDT');
  const token = window.GangziApp?.getToken ? window.GangziApp.getToken() : '';
  if (!token) { alert('请先登录'); return; }
  try {
    const resp = await fetch(API_BASE + '/api/trade/close-position', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
      body: JSON.stringify({ symbol: rawSymbol, side: side }),
    });
    const result = await resp.json();
    if (result.code === 0) {
      _showTradeToast(coin + ' ' + sideCn + '仓已平仓', 'success');
      _suppressHistorySoundBackfill();
      setTimeout(() => {
        if (typeof window._refreshTradingData === 'function') window._refreshTradingData();
      }, 1000);
    } else {
      alert(result.message || '平仓失败');
    }
  } catch (e) {
    alert('平仓请求失败: ' + e.message);
  }
}

// ====== 渲染：持仓列表 ======
export function renderPositions(data) {
  const badge = document.getElementById('positionSummaryBadge');
  const listEl = document.getElementById('positionList');

  const summary = data.summary || {};
  const positions = data.positions || [];

  if (badge) badge.textContent = `${summary.position_count || 0} 个持仓`;
  if (!listEl) return;

  // 缓存持仓数据供 WebSocket 实时更新
  window._positionsCache = positions;

  if (positions.length === 0) {
    if (listEl.dataset.renderSig !== 'empty') {
      listEl.dataset.renderSig = 'empty';
      listEl.innerHTML = '<div class="no-data" style="font-size:13px;">暂无持仓</div>';
    }
    return;
  }

  const sig = _positionsRenderSig(positions);
  if (listEl.dataset.renderSig === sig) return;
  listEl.dataset.renderSig = sig;

  const html = positions.map(p => {
    const pnlCls = p.pnl >= 0 ? 'profit' : 'loss';
    const sign = p.pnl >= 0 ? '+' : '';
    const coinCls = p.currency === 'BTC' ? 'btc' : p.currency === 'ETH' ? 'eth' : 'other';
    const isShort = p.side === 'short';
    const sideCls = isShort ? 'pos-side-short' : 'pos-side-long';
    const sideCn = isShort ? '空' : '多';

    return `
      <div class="pos-card" data-symbol="${esc(p.symbol)}" data-side="${p.side}">
        <div class="pos-coin-icon ${coinCls}">${esc(p.currency)}</div>
        <div class="pos-info">
          <div class="pos-info-top">
            <span class="pos-symbol">${esc(p.symbol)}</span>
            <span class="pos-side-tag ${sideCls}">${sideCn}</span>
            <span style="font-size:10px;padding:0 3px;border:1px solid var(--border);border-radius:3px;color:var(--text3);margin-left:2px">${p.leverage}x</span>
            <span class="pos-qty">$${(p.quantity * p.avg_price).toFixed(2)}</span>
            <button class="pos-close-btn" onclick="closeSinglePosition('${esc(p.symbol)}','${p.side}',event)">手动平仓</button>
          </div>
          <div class="pos-info-mid">
            <span>成本 ${_fmtPrice(p.avg_price)}</span>
            <span class="pos-live-price">现价 ${_fmtPrice(p.current_price)}</span>
            <span>清算 ${_fmtPrice(p.liquidation_price, true)}</span>
          </div>
        </div>
        <div class="pos-pnl-area">
          <div class="pos-pnl-amount ${pnlCls}">${sign}$${p.pnl.toFixed(2)}</div>
          <div class="pos-pnl-pct ${pnlCls}">${sign}${p.pnl_pct.toFixed(2)}%</div>
          <div class="pos-market-value">市值 $${p.market_value.toFixed(2)}</div>
        </div>
      </div>
    `;
  }).join('');

  if (window.morphdom) {
    const wrapper = document.createElement('div');
    wrapper.id = 'positionList';
    wrapper.className = 'pos-list';
    wrapper.innerHTML = html;
    window.morphdom(listEl, wrapper, {
      childrenOnly: true,
      getNodeKey: function(node) {
        if (node.classList && node.classList.contains('pos-card')) {
          return node.getAttribute('data-symbol') + '-' + node.getAttribute('data-side');
        }
        return node.id;
      }
    });
  } else {
    listEl.innerHTML = html;
  }
}

// ====== 从缓存重新渲染 ======
export function _rerenderFromCache() {
  const cache = window._positionsCache || [];
  const totalPnl = cache.reduce((s, p) => s + (p.pnl || 0), 0);
  const totalCost = cache.reduce((s, p) => s + (p.cost_value || 0), 0);
  const totalValue = cache.reduce((s, p) => s + (p.market_value || 0), 0);

  const posData = {
    positions: cache,
    summary: {
      total_cost: totalCost,
      total_value: totalValue,
      total_pnl: totalPnl,
      total_pnl_pct: totalCost > 0 ? (totalPnl / totalCost * 100) : 0,
      position_count: cache.length,
    }
  };
  renderPositions(posData);
  renderAccountHero(posData);
}

// ====== WebSocket 实时更新持仓价格、盈亏、总资产 ======
window.addEventListener('ws-prices', (e) => {
  const prices = e.detail;
  const cache = window._positionsCache;
  if (!cache || !cache.length) return;

  let totalPnl = 0;
  let totalMargin = 0;

  cache.forEach(p => {
    const priceData = prices[p.symbol];
    if (!priceData) {
      totalPnl += p.pnl || 0;
      totalMargin += p.cost_value || 0;
      return;
    }

    const livePrice = parseFloat(priceData.price || 0);
    if (livePrice <= 0) {
      totalPnl += p.pnl || 0;
      totalMargin += p.cost_value || 0;
      return;
    }

    const isShort = p.side === 'short';
    const pnl = isShort
      ? (p.avg_price - livePrice) * p.quantity
      : (livePrice - p.avg_price) * p.quantity;
    const marketValue = livePrice * p.quantity;
    const margin = p.leverage > 0 ? marketValue / p.leverage : (p.cost_value || 1);
    const pnlPct = margin > 0 ? (pnl / margin * 100) : 0;

    p.current_price = livePrice;
    p.pnl = pnl;
    p.pnl_pct = pnlPct;
    p.market_value = marketValue;

    totalPnl += pnl;
    totalMargin += margin;

    const card = document.querySelector(
      `#positionList .pos-card[data-symbol="${p.symbol}"][data-side="${p.side}"]`
    );
    if (!card) return;

    const priceEl = card.querySelector('.pos-live-price');
    if (priceEl) {
      const newText = `现价 ${_fmtPrice(livePrice)}`;
      if (priceEl.textContent !== newText) priceEl.textContent = newText;
    }

    const sign = pnl >= 0 ? '+' : '';
    const pnlCls = pnl >= 0 ? 'profit' : 'loss';

    const pnlAmtEl = card.querySelector('.pos-pnl-amount');
    if (pnlAmtEl) {
      pnlAmtEl.textContent = `${sign}$${pnl.toFixed(2)}`;
      pnlAmtEl.className = `pos-pnl-amount ${pnlCls}`;
    }

    const pnlPctEl = card.querySelector('.pos-pnl-pct');
    if (pnlPctEl) {
      pnlPctEl.textContent = `${sign}${pnlPct.toFixed(2)}%`;
      pnlPctEl.className = `pos-pnl-pct ${pnlCls}`;
    }

    const mvEl = card.querySelector('.pos-market-value');
    if (mvEl) mvEl.textContent = `市值 $${marketValue.toFixed(2)}`;
  });

  // hero 区：总资产 & 浮动盈亏
  const usdtFreeEl = document.getElementById('usdtFreeText');
  const usdtParsed = parseFloat(usdtFreeEl?.dataset?.usdtTotal || '');
  if (Number.isFinite(usdtParsed)) {
    state._usdtTotalReady = true;
    state._lastUsdtTotal = usdtParsed;
  }
  const usdtTotal = Number.isFinite(usdtParsed) ? usdtParsed : state._lastUsdtTotal;
  if (!state._usdtTotalReady) return;
  const totalAsset = usdtTotal + totalPnl;

  const totalValueEl = document.getElementById('totalAssetValue');
  if (totalValueEl) {
    totalValueEl.textContent = `$${totalAsset.toLocaleString('en', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
  }

  const totalPnlEl = document.getElementById('totalPnlText');
  if (totalPnlEl) {
    const s = totalPnl >= 0 ? '+' : '';
    const pctEq = usdtTotal > 0 ? (totalPnl / usdtTotal * 100) : 0;
    totalPnlEl.textContent = `浮动盈亏 ${s}$${totalPnl.toFixed(2)} (${s}${pctEq.toFixed(2)}%)`;
    totalPnlEl.className = `account-hero-sub ${totalPnl > 0 ? 'profit' : totalPnl < 0 ? 'loss' : 'neutral'}`;
  }

  const floatPnlEl = document.getElementById('floatPnlText');
  if (floatPnlEl) {
    const s = totalPnl >= 0 ? '+' : '';
    floatPnlEl.textContent = `${s}$${totalPnl.toFixed(2)}`;
    floatPnlEl.style.color = totalPnl > 0 ? 'var(--green)' : totalPnl < 0 ? 'var(--red)' : 'var(--text)';
  }

  const costTextEl = document.getElementById('totalCostText');
  if (costTextEl) {
    const totalMV = cache.reduce((acc, p) => acc + (p.market_value || 0), 0);
    costTextEl.textContent = `$${totalMV.toFixed(2)}`;
  }
});

// ====== 渲染：止损暂停状态 ======
export function renderSlPauseStatus(slData) {
  const el = document.getElementById('slPauseStatus');
  if (!el) return;
  if (!slData || !slData.symbols || slData.symbols.length === 0) {
    el.innerHTML = '';
    return;
  }
  const items = slData.symbols.map(s => {
    const coin = (s.symbol || '').replace('USDT', '');
    if (s.paused) {
      const min = Math.ceil(s.remaining_seconds / 60);
      return `<span class="sl-pause-tag sl-paused"><i class="ri-pause-circle-line"></i> ${esc(coin)} 连续止损${s.sl_count}次 暂停中（${min}分钟）</span>`;
    }
    if (s.sl_count > 0) {
      return `<span class="sl-pause-tag sl-warning"><i class="ri-error-warning-line"></i> ${esc(coin)} 已连续止损${s.sl_count}次</span>`;
    }
    return '';
  }).filter(Boolean);
  el.innerHTML = items.length ? `<div class="sl-pause-bar">${items.join('')}</div>` : '';
}

// 导出到全局（HTML onclick 需要）
window.closeSinglePosition = closeSinglePosition;
