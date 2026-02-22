/**
 * 钢子出击 - 交易面板订单/交易记录模块
 * 交易记录渲染、订单推送处理、成交提示音、通知
 */
import { state, esc, _fmtPrice, _suppressHistorySoundBackfill } from './utils.js';
import { _rerenderFromCache } from './positions.js';

const API_BASE = state.API_BASE;

// ====== 交易记录全局状态 ======
window._tradeShowAll = false;
window._refreshTradeList = function() { if (state._lastTradeData) renderTradeHistory(state._lastTradeData); };

// ====== 渲染签名（去重） ======
function _tradeHistoryRenderSig(history, showAll) {
  const rows = history.map(r => [
    r.id, r.symbol, r.side, r.status, r.price,
    r.signal_confidence, r.realized_pnl_usdt, r.quote_amount,
    r.error_msg, r.created_at
  ].join(':')).join('|');
  return `${showAll ? 'all' : 'filled'}|${rows}`;
}

// ====== 构建加仓标记映射 ======
function _buildOpenAddOnMap(history) {
  const addOnMap = new Map();
  const openState = new Map();
  const seenExchangeOrderIds = new Set();

  const ordered = [...history]
    .filter(r => r && r.status === 'filled')
    .sort((a, b) => {
      const ta = Date.parse(a.created_at || '') || 0;
      const tb = Date.parse(b.created_at || '') || 0;
      if (ta !== tb) return ta - tb;
      return Number(a.id || 0) - Number(b.id || 0);
    });

  for (const r of ordered) {
    const exchangeOrderId = String(r.exchange_order_id || '').trim();
    if (exchangeOrderId) {
      if (seenExchangeOrderIds.has(exchangeOrderId)) continue;
      seenExchangeOrderIds.add(exchangeOrderId);
    }

    const symbol = String(r.symbol || '').toUpperCase();
    const side = String(r.side || '').toUpperCase();
    const posSide = String(r.position_side || '').toUpperCase();
    const rowKey = String(r.id || '');
    if (!symbol || !rowKey) continue;

    if (side === 'BUY' || side === 'SHORT') {
      let openSide = side === 'BUY' ? 'long' : 'short';
      if (posSide === 'LONG') openSide = 'long';
      if (posSide === 'SHORT') openSide = 'short';
      const k = `${symbol}:${openSide}`;
      const cur = openState.get(k) || 0;
      addOnMap.set(rowKey, cur > 0);
      openState.set(k, cur + 1);
      continue;
    }

    if (side === 'SELL' || side === 'COVER') {
      let closeSide = side === 'SELL' ? 'long' : 'short';
      if (posSide === 'LONG') closeSide = 'long';
      if (posSide === 'SHORT') closeSide = 'short';
      const k = `${symbol}:${closeSide}`;
      const cur = openState.get(k) || 0;
      openState.set(k, Math.max(0, cur - 1));
    }
  }

  return addOnMap;
}

// ====== 友好化错误原因 ======
function _friendlyReason(record) {
  const msg = record.error_msg || '';
  if (!msg) return '';
  if (msg.includes('持仓为 0') || msg.includes('持仓为0')) {
    const coin = (record.symbol || '').replace('USDT', '');
    return `未持有${coin}，信号未执行`;
  }
  if (msg.includes('限额已满')) return '已达当日交易限额';
  if (msg.includes('连续止损') && msg.includes('暂停')) return '连续止损暂停中，等待恢复';
  if (msg.includes('冷却') || msg.includes('cooldown')) return '交易冷却中，稍后再试';
  if (msg.includes('最大持仓') || msg.includes('position')) return '已达最大持仓上限';
  if (msg.includes('止盈')) return '触发止盈，自动卖出';
  if (msg.includes('止损')) return '触发止损，自动卖出';
  return msg.length > 30 ? msg.substring(0, 28) + '...' : msg;
}

// ====== 渲染：交易记录 ======
export function renderTradeHistory(data) {
  state._lastTradeData = data;
  const list = document.getElementById('tradeHistoryList');
  const countBadge = document.getElementById('tradeCountBadge');
  if (!list) return;

  const allHistory = data.history || [];
  const showAll = window._tradeShowAll;

  const history = showAll ? allHistory : allHistory.filter(r => r.status === 'filled');
  const filledCount = allHistory.filter(r => r.status === 'filled').length;

  if (countBadge) {
    countBadge.textContent = showAll
      ? `${data.total || 0} 笔`
      : `${filledCount} 笔成交`;
  }

  const renderSig = _tradeHistoryRenderSig(history, showAll);
  if (list.dataset.renderSig === renderSig) return;
  list.dataset.renderSig = renderSig;

  if (history.length === 0) {
    list.innerHTML = '<div class="no-data">暂无成交记录</div>';
    return;
  }

  const addOnMap = _buildOpenAddOnMap(history);
  const html = history.map(r => {
    const sideClass = {BUY:'buy', SELL:'sell', SHORT:'short', COVER:'cover'}[r.side] || 'skip';
    const isAddOn = !!addOnMap.get(String(r.id || ''));
    let sideCn = { BUY: isAddOn ? '加多' : '开多', SHORT: isAddOn ? '加空' : '开空', SELL: '平多', COVER: '平空' }[r.side] || r.side;
    const statusClass = r.status || 'pending';
    const statusCn = { filled: '成交', failed: '失败', skipped: '跳过', pending: '挂起' }[r.status] || r.status;
    const time = r.created_at ? new Date(r.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '--';
    const priceStr = r.price > 0 ? _fmtPrice(Number(r.price)) : '--';
    const confStr = r.signal_confidence > 0 ? `置信度 ${r.signal_confidence}%` : '';
    const rpnl = Number(r.realized_pnl_usdt);
    const hasRpnl = (r.side === 'SELL' || r.side === 'COVER') && Number.isFinite(rpnl);
    const rpnlPillHtml = hasRpnl
      ? `<div class="trade-pnl-pill ${rpnl >= 0 ? 'profit' : 'loss'}">${rpnl >= 0 ? '+' : ''}$${rpnl.toFixed(2)}</div>`
      : '';

    const reasonText = _friendlyReason(r);
    const isFailed = r.status === 'failed' || r.status === 'skipped';
    const amountStr = r.quote_amount > 0 ? `金额 ${Number(r.quote_amount).toFixed(2)} USDT` : '';

    let closeTag = '';
    if (r.error_msg) {
      const m = r.error_msg;
      const tagRaw = (m.match(/\[([^\]]+)\]/) || [])[1] || '';
      const tagMain = String(tagRaw).split('|')[0];
      if (tagMain === '交易所开仓') closeTag = '交易所开仓';
      else if (tagMain === '移动止盈') closeTag = '移动止盈';
      else if (tagMain === '止盈') closeTag = '止盈';
      else if (tagMain === '止损') closeTag = '止损';
      else if (tagMain === '超时平仓') closeTag = '超时平仓';
      else if (tagMain === '翻仓') closeTag = '翻仓';
      else if (tagMain === '手动平仓') closeTag = '手动平仓';
      else if (tagMain === '一键平仓') closeTag = '一键平仓';
      else if (tagMain.startsWith('AI平仓')) closeTag = 'AI平仓';
      else if (tagMain === '交易所平仓') closeTag = '交易所平仓';
      else if (tagMain.startsWith('AI开仓') || tagMain === 'AI信号') closeTag = 'AI开仓';
    }

    let bottomParts = [time];
    if (isFailed && reasonText) {
      bottomParts.push(reasonText);
    } else {
      if (amountStr) bottomParts.push(amountStr);
    }
    if (confStr) bottomParts.push(confStr);
    const bottomText = bottomParts.join(' · ');

    const isOpenSide = r.side === 'BUY' || r.side === 'SHORT';
    const closeTagStyle = isOpenSide
      ? 'background:rgba(0,200,83,0.15);color:var(--green)'
      : 'background:rgba(251,191,36,0.15);color:var(--yellow,#fbbf24)';

    return `
      <div class="trade-record${isFailed ? ' trade-dimmed' : ''}" data-id="${r.id}">
        <div class="trade-side ${sideClass}">${esc(sideCn)}</div>
        <div class="trade-detail">
          <div class="trade-detail-top">${esc(r.symbol)} 成交价 ${priceStr}${closeTag ? ` <span style="font-size:10px;padding:1px 5px;border-radius:3px;margin-left:4px;font-weight:600;${closeTagStyle}">${esc(closeTag)}</span>` : ''}</div>
          <div class="trade-detail-bottom">${esc(bottomText)}</div>
        </div>
        ${rpnlPillHtml}
        ${showAll ? '<div class="trade-status-tag ' + statusClass + '">' + esc(statusCn) + '</div>' : ''}
      </div>
    `;
  }).join('');

  if (window.morphdom) {
    const wrapper = document.createElement('div');
    wrapper.id = 'tradeHistoryList';
    wrapper.className = 'trade-history-list';
    wrapper.innerHTML = html;
    window.morphdom(list, wrapper, {
      childrenOnly: true,
      getNodeKey: function(node) {
        if (node.classList && node.classList.contains('trade-record')) {
          return node.getAttribute('data-id');
        }
        return node.id;
      }
    });
  } else {
    list.innerHTML = html;
  }
}

// ====== 未读标记 ======
export function _renderTradeUnreadBadge() {
  const el = document.getElementById('tradeUnreadBadge');
  if (!el) return;
  if (state._tradeUnreadCount > 0) {
    el.style.display = '';
    el.textContent = `未读 ${state._tradeUnreadCount}`;
  } else {
    el.style.display = 'none';
    el.textContent = '未读 0';
  }
}

function _markTradeUnread(order) {
  if (!document.hidden) return;
  const oid = String(order?.order_id || '').trim();
  if (!oid || state._tradeUnreadOrderIds.has(oid)) return;
  state._tradeUnreadOrderIds.add(oid);
  if (state._tradeUnreadOrderIds.size > 500) state._tradeUnreadOrderIds.clear();
  state._tradeUnreadCount += 1;
  _renderTradeUnreadBadge();
}

// ====== 成交通知 ======
function _notifyFilledOrder(order) {
  if (!document.hidden) return;
  if (!('Notification' in window)) return;

  const side = String(order.side || '').toUpperCase();
  const action = (side === 'BUY' || side === 'SHORT') ? '开仓' : '平仓';
  const symbol = String(order.symbol || '--');
  const qty = Number(order.filled_qty || order.quantity || 0);
  const px = Number(order.avg_price || order.price || 0);
  const body = `${symbol} ${action}成交 · 数量 ${qty || '--'} · 价格 ${px > 0 ? `$${px.toFixed(2)}` : '--'}`;
  const options = { body, tag: `trade-${order.order_id || Date.now()}`, silent: false, requireInteraction: false };

  if (Notification.permission === 'granted') {
    new Notification('钢子出击成交提醒', options);
    return;
  }
  if (Notification.permission === 'default') {
    Notification.requestPermission()
      .then((perm) => {
        if (perm === 'granted') new Notification('钢子出击成交提醒', options);
      })
      .catch(() => {});
  }
}

// ====== 成交提示音工具 ======
export function _getTradeSoundKind(orderOrSide) {
  const obj = (orderOrSide && typeof orderOrSide === 'object') ? orderOrSide : null;
  const side = String(obj ? obj.side : orderOrSide || '').toUpperCase();
  const posSide = String(obj?.position_side || '').toUpperCase();
  const isReduce = !!obj?.reduce_only || !!obj?.close_position;

  if (posSide === 'LONG') {
    if (side === 'SELL' || isReduce) return 'sell';
    if (side === 'BUY') return 'buy';
  }
  if (posSide === 'SHORT') {
    if (side === 'BUY' || isReduce) return 'sell';
    if (side === 'SELL') return 'buy';
  }

  if (isReduce) return 'sell';
  if (side === 'BUY' || side === 'SHORT') return 'buy';
  if (side === 'SELL' || side === 'COVER') return 'sell';
  return '';
}

// ====== 历史差量补播成交提示音 ======
export function maybePlayLatestFilledTradeSound(historyData) {
  const list = historyData?.history || historyData?.data || [];
  if (!Array.isArray(list) || list.length === 0) return;

  const filled = list.filter(r => r && r.status === 'filled' && r.id !== undefined && r.id !== null);
  if (filled.length === 0) return;

  const ids = filled.map(r => Number(r.id)).filter(n => Number.isFinite(n) && n > 0);
  if (ids.length === 0) return;
  const newestId = Math.max(...ids);

  if (!state._tradeSoundPrimed) {
    localStorage.setItem(state.LAST_TRADE_SOUND_KEY, String(newestId));
    state._tradeSoundPrimed = true;
    return;
  }

  const lastId = Number(localStorage.getItem(state.LAST_TRADE_SOUND_KEY) || 0);
  if (!Number.isFinite(lastId) || lastId <= 0) {
    localStorage.setItem(state.LAST_TRADE_SOUND_KEY, String(newestId));
    return;
  }

  const newTrades = filled
    .filter(r => Number(r.id) > lastId)
    .sort((a, b) => Number(a.id) - Number(b.id));
  if (newTrades.length === 0) return;

  const toPlay = newTrades.slice(-state.MAX_TRADE_SOUND_BACKFILL);
  localStorage.setItem(state.LAST_TRADE_SOUND_KEY, String(newestId));

  const play = window.GangziApp?.playTradeSound;
  if (typeof play !== 'function') return;

  setTimeout(() => {
    toPlay.forEach((r) => {
      const kind = _getTradeSoundKind(r);
      if (!kind) return;
      play(kind, { orderId: String(r.exchange_order_id || r.id || '') });
    });
  }, 80);
}

// ====== WS 订单推送处理 ======
export function _handleOrderPush(e) {
  const order = e.detail;
  if (!order || order.status !== 'FILLED') return;

  const kind = _getTradeSoundKind(order);
  if (kind) {
    const play = window.GangziApp?.playTradeSound;
    if (typeof play === 'function') {
      play(kind, { orderId: String(order.order_id || '') });
      _suppressHistorySoundBackfill();
    }
  }

  _notifyFilledOrder(order);
  _markTradeUnread(order);

  // 立即更新持仓缓存
  const side = String(order.side || '').toUpperCase();
  const ps = String(order.position_side || '').toUpperCase();
  const sym = String(order.symbol || '');
  const filledQty = Math.max(0, Number(order.filled_qty || order.quantity || 0) || 0);
  const px = Math.max(0, Number(order.avg_price || order.price || 0) || 0);
  const isReduce = !!order.reduce_only || !!order.close_position;
  const cache = window._positionsCache;
  if (Array.isArray(cache) && sym) {
    let targetPos = '';
    let isClose = false;

    if (ps === 'LONG') {
      targetPos = 'long';
      isClose = (side === 'SELL') || isReduce;
    } else if (ps === 'SHORT') {
      targetPos = 'short';
      isClose = (side === 'BUY') || isReduce;
    } else {
      if (isReduce) {
        if (side === 'SELL') { targetPos = 'long'; isClose = true; }
        else if (side === 'BUY') { targetPos = 'short'; isClose = true; }
      } else {
        if (side === 'BUY') { targetPos = 'long'; isClose = false; }
        else if (side === 'SELL') { targetPos = 'short'; isClose = false; }
      }
    }

    if (targetPos) {
      const idx = cache.findIndex(p => p.symbol === sym && p.side === targetPos);
      if (isClose) {
        if (idx >= 0) {
          const cur = cache[idx];
          const curQty = Math.max(0, Number(cur.quantity || 0) || 0);
          const remain = curQty - (filledQty > 0 ? filledQty : curQty);
          if (remain <= 1e-8) {
            cache.splice(idx, 1);
          } else {
            cur.quantity = remain;
            if (Number(cur.avg_price || 0) > 0) cur.cost_value = remain * Number(cur.avg_price || 0);
            if (Number(cur.current_price || 0) > 0) cur.market_value = remain * Number(cur.current_price || 0);
            const cost = Number(cur.cost_value || 0);
            const market = Number(cur.market_value || 0);
            cur.pnl = market - cost;
            cur.pnl_pct = cost > 0 ? (cur.pnl / cost * 100) : 0;
          }
          _rerenderFromCache();
        }
      } else {
        if (idx >= 0) {
          const cur = cache[idx];
          const curQty = Math.max(0, Number(cur.quantity || 0) || 0);
          const curAvg = Math.max(0, Number(cur.avg_price || 0) || 0);
          const addQty = filledQty;
          if (addQty > 0) {
            const totalQty = curQty + addQty;
            const nextAvg = totalQty > 0 ? ((curQty * curAvg + addQty * px) / totalQty) : curAvg;
            cur.quantity = totalQty;
            cur.avg_price = nextAvg;
            if (Number(cur.current_price || 0) <= 0) cur.current_price = px || nextAvg;
            cur.cost_value = totalQty * (Number(cur.avg_price || 0) || 0);
            cur.market_value = totalQty * (Number(cur.current_price || 0) || 0);
            const cost = Number(cur.cost_value || 0);
            const market = Number(cur.market_value || 0);
            cur.pnl = market - cost;
            cur.pnl_pct = cost > 0 ? (cur.pnl / cost * 100) : 0;
            _rerenderFromCache();
          }
        } else if (filledQty > 0 && px > 0) {
          cache.push({
            symbol: sym,
            side: targetPos,
            currency: sym.replace('USDT', ''),
            quantity: filledQty,
            avg_price: px,
            current_price: px,
            leverage: 1,
            cost_value: filledQty * px,
            market_value: filledQty * px,
            pnl: 0,
            pnl_pct: 0,
            liquidation_price: 0,
          });
          _rerenderFromCache();
        }
      }
    }
  }

  // 延迟 300ms 再查交易记录
  const token = window.GangziApp?.getToken ? window.GangziApp.getToken() : '';
  if (!token) return;
  setTimeout(() => {
    fetch(`${API_BASE}/api/trade/history?today=1&status=filled&limit=2000`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    .then(r => r.ok ? r.json() : null)
    .then(d => { if (d) { renderTradeHistory(d); } })
    .catch(err => console.warn('[WS订单] 刷新交易记录失败:', err));
  }, 300);
}
