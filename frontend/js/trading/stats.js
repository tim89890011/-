/**
 * 钢子出击 - 交易面板统计模块
 * 渲染今日战绩、策略配置、AI准确率、最强大脑、信号统计、引擎状态
 */
import { state, esc, _setText, _timeAgo } from './utils.js';

const API_BASE = state.API_BASE;

// ====== 渲染：统计 & 策略 ======
export function renderStats(data) {
  const today = data.today || {};
  const total = data.total || {};
  const strategy = data.strategy || {};
  const account = data.account || {};

  // 交易记录头部：今日成交
  const todayBadge = document.getElementById('tradeTodayFilledBadge');
  if (todayBadge) todayBadge.textContent = `今日成交 ${today.trades ?? '--'}`;

  // 交易记录头部：今日执行状态
  const stBadge = document.getElementById('tradeTodayStatusBadge');
  const st = data.today_status || {};
  if (stBadge) {
    const filled = st.filled ?? '--';
    const skipped = st.skipped ?? '--';
    const failed = st.failed ?? '--';
    stBadge.textContent = `本轮 成交${filled} 跳过${skipped} 失败${failed}`;
  }

  // USDT 可用余额缓存到 DOM
  const usdtFree = document.getElementById('usdtFreeText');
  if (usdtFree) {
    usdtFree.textContent = `$${(account.usdt_free || 0).toFixed(2)}`;
    usdtFree.dataset.raw = String(account.usdt_free || 0);
    usdtFree.dataset.usdtTotal = String(account.usdt_total || 0);
  }
  if (Object.prototype.hasOwnProperty.call(account, 'usdt_total')) {
    const totalVal = Number(account.usdt_total || 0);
    if (Number.isFinite(totalVal)) {
      state._usdtTotalReady = true;
      state._lastUsdtTotal = totalVal;
    }
  }

  // 今日
  _setText('todayTradesNum', today.trades || 0);
  _setText('todayBuyNum', (today.buy_count || 0) + (today.short_count || 0));
  _setText('todaySellNum', (today.sell_count || 0) + (today.cover_count || 0));
  const todayVol = (today.buy_volume || 0) + (today.sell_volume || 0) + (today.short_volume || 0) + (today.cover_volume || 0);
  _setText('todayVolumeNum', `$${todayVol.toFixed(2)}`);

  // 止盈/止损次数
  const tpTotal = (today.tp_count || 0) + (today.trailing_count || 0);
  const slTotal = today.sl_count || 0;
  _setText('todayTpNum', tpTotal);
  _setText('todaySlNum', slTotal);
  _setText('todayBlockedNum', today.sl_blocked || 0);

  // 已实现盈亏
  const rPnl = data.realized_pnl || {};
  const netPnl = rPnl.total_pnl || 0;
  const grossPnl = rPnl.gross_pnl || 0;
  const commCost = rPnl.commission || 0;
  const fundingFee = rPnl.funding_fee || 0;

  const rpnlEl = document.getElementById('realizedPnlNum');
  if (rpnlEl) {
    const s = netPnl >= 0 ? '+' : '';
    rpnlEl.textContent = `${s}$${netPnl.toFixed(2)}`;
    rpnlEl.style.color = netPnl > 0 ? 'var(--green)' : netPnl < 0 ? 'var(--red)' : 'var(--text)';
  }
  const grossEl = document.getElementById('grossPnlNum');
  if (grossEl) {
    const s = grossPnl >= 0 ? '+' : '';
    grossEl.textContent = `${s}$${grossPnl.toFixed(2)}`;
    grossEl.style.color = grossPnl > 0 ? 'var(--green)' : grossPnl < 0 ? 'var(--red)' : 'var(--text)';
  }
  _setText('commissionCostNum', `-$${commCost.toFixed(2)}`);
  const fundEl = document.getElementById('fundingFeeNum');
  if (fundEl) {
    const s = fundingFee >= 0 ? '+' : '';
    fundEl.textContent = `${s}$${fundingFee.toFixed(2)}`;
    fundEl.style.color = fundingFee > 0 ? 'var(--green)' : fundingFee < 0 ? 'var(--red)' : 'var(--text)';
  }
  const wrEl = document.getElementById('winRateNum');
  if (wrEl) {
    const wr = rPnl.win_rate || 0;
    wrEl.textContent = `${wr.toFixed(1)}%`;
    wrEl.style.color = wr >= 50 ? 'var(--green)' : wr > 0 ? 'var(--yellow, #f59e0b)' : 'var(--text)';
  }
  _setText('winClosedNum', `${rPnl.win_count || 0}/${rPnl.trade_count || 0}`);

  // 累计
  _setText('totalTradesNum', `${total.trades || 0} 笔`);
  _setText('totalVolumeNum', `$${(total.volume || 0).toFixed(2)}`);
  _setText('totalCommissionNum', `$${(total.commission || 0).toFixed(4)}`);

  // 最近交易
  if (data.last_trade_at) {
    const ago = _timeAgo(new Date(data.last_trade_at));
    _setText('lastTradeTime', ago);
  }

  // 策略
  _setText('strategyName', strategy.name || '波段交易');
  _setText('stratAmountText', `${strategy.amount_usdt || 0} USDT`);
  const confBuy = strategy.min_conf_buy ?? strategy.min_confidence ?? 55;
  const confShort = strategy.min_conf_short ?? strategy.min_confidence ?? 55;
  const confSell = strategy.min_conf_sell ?? strategy.min_confidence ?? 60;
  _setText('stratConfText', `开多≥${confBuy}% / 开空≥${confShort}% / 平多≥${confSell}%`);
  const symbolsEl = document.getElementById('stratSymbolsText');
  if (symbolsEl) {
    const syms = (strategy.symbols || '').split(',').map(s => s.trim()).filter(Boolean);
    if (syms.length > 0) {
      symbolsEl.innerHTML = syms.map(s => {
        const coin = s.replace('USDT', '');
        return `<span class="symbol-tag">${esc(coin)}</span>`;
      }).join('');
    } else {
      symbolsEl.textContent = '--';
    }
  }
  const cd = strategy.cooldown_seconds || 30;
  _setText('stratCooldownText', cd >= 60 ? `${Math.round(cd/60)}分钟` : `${cd}s`);
  _setText('stratIntervalText', strategy.analysis_interval || '--');
  _setText('stratMaxPosText', `$${strategy.max_position_usdt ?? 500} / 币种`);
  const dl = strategy.daily_limit_usdt;
  _setText('stratDailyLimitText', (dl != null && dl > 0) ? `$${dl} / 天` : '无限制');
  const tp = strategy.take_profit_pct || 3;
  const sl = strategy.stop_loss_pct || 2;
  _setText('stratTpSlText', `+${tp}% 止盈 / -${sl}% 止损`);
  const lev = strategy.leverage || 3;
  const mm = (strategy.margin_mode || 'isolated') === 'isolated' ? '逐仓' : '全仓';
  _setText('stratLeverageText', `${lev}x ${mm}`);
  _setText('stratTrailingText', strategy.trailing_stop_enabled ? '4级递进' : '关闭');
  const toh = strategy.position_timeout_hours || 0;
  _setText('stratTimeoutText', toh > 0 ? `${toh}h强平 / 12h弱平` : '关闭');
}

// ====== 渲染：准确率完整版 ======
export function renderAccuracyFull(acc) {
  const badge = document.getElementById('accuracyTotalBadge');
  if (badge) badge.textContent = `${acc.total_signals || 0} 条已验证`;
  _setText('accuracyPctNum', `${acc.direction_accuracy || 0}%`);
  _setText('accuracyWeightedNum', `${acc.weighted_accuracy || 0}%`);
  _setText('accuracyCorrectNum', acc.correct_count || 0);
  _setText('accuracyWrongNum', acc.incorrect_count || 0);
  const correctEl = document.getElementById('accuracyCorrectNum');
  const wrongEl = document.getElementById('accuracyWrongNum');
  if (correctEl) correctEl.style.color = 'var(--green)';
  if (wrongEl) wrongEl.style.color = 'var(--red)';

  // 按类型
  const byType = acc.by_signal_type || {};
  const typeEl = document.getElementById('accuracyByType');
  if (typeEl && Object.keys(byType).length > 0) {
    const _typeCls = {BUY:'buy', SELL:'sell', SHORT:'short', COVER:'cover', HOLD:'hold'};
    const _typeCn = {BUY:'开多', SELL:'平多', SHORT:'开空', COVER:'平空', HOLD:'观望'};
    typeEl.innerHTML = ['BUY', 'SELL', 'SHORT', 'COVER', 'HOLD'].map(t => {
      const d = byType[t] || {};
      const total = d.total || 0;
      const accPct = d.accuracy != null ? d.accuracy : '--';
      const cls = _typeCls[t] || 'hold';
      const cn = _typeCn[t] || t;
      return `<div class="accuracy-type-item">
        <div class="accuracy-type-label ${cls}">${cn}</div>
        <div class="accuracy-type-value">${total > 0 ? accPct + '%' : '--'}</div>
        <div class="accuracy-type-sub">${d.correct || 0}对 / ${d.incorrect || 0}错</div>
      </div>`;
    }).join('');
  }

  // 按币种
  const bySymbol = acc.by_symbol || {};
  const symEl = document.getElementById('accuracyBySymbol');
  if (symEl && Object.keys(bySymbol).length > 0) {
    const entries = Object.entries(bySymbol).sort((a, b) => b[1].total - a[1].total);
    symEl.innerHTML = `
      <div class="accuracy-section-title">各币种验证结果</div>
      <div class="accuracy-symbol-grid">
        ${entries.map(([sym, d]) => {
          const short = sym.replace('USDT', '');
          const pct = d.accuracy != null ? d.accuracy : 0;
          const colorCls = pct >= 60 ? 'acc-good' : pct >= 40 ? 'acc-mid' : 'acc-bad';
          return `<div class="accuracy-symbol-item">
            <span class="accuracy-sym-name">${esc(short)}</span>
            <span class="accuracy-sym-pct ${colorCls}">${pct}%</span>
            <span class="accuracy-sym-detail">${d.correct || 0}对 ${d.incorrect || 0}错 ${d.neutral || 0}中</span>
          </div>`;
        }).join('')}
      </div>`;
  }
}

// ====== 渲染：最强大脑 ======
export function renderSuperbrain(d) {
  const card = document.getElementById('superbrainCard');
  if (!card) return;
  card.style.display = '';

  _setText('sbSessionBadge', d.trading_session || '--');
  _setText('sbMarketRegime', d.market_regime || '--');

  const dirEl = document.getElementById('sbBtcDirection');
  if (dirEl) {
    dirEl.textContent = d.btc_direction || '--';
    dirEl.className = 'sb-value';
    if (d.btc_direction === '上涨') dirEl.classList.add('sb-up');
    else if (d.btc_direction === '下跌') dirEl.classList.add('sb-down');
  }

  _setText('sbBtcPrice', d.btc_price ? `$${Number(d.btc_price).toLocaleString()}` : '--');

  const c1h = d.btc_change_1h || 0;
  const c4h = d.btc_change_4h || 0;
  const changeEl = document.getElementById('sbBtcChange');
  if (changeEl) {
    changeEl.innerHTML = `<span class="${c1h >= 0 ? 'sb-up' : 'sb-down'}">${c1h >= 0 ? '+' : ''}${c1h.toFixed(2)}%</span> / <span class="${c4h >= 0 ? 'sb-up' : 'sb-down'}">${c4h >= 0 ? '+' : ''}${c4h.toFixed(2)}%</span>`;
  }

  const longVal = d.global_long_total || 0;
  const shortVal = d.global_short_total || 0;
  const totalVal = longVal + shortVal;
  _setText('sbLongVal', `$${longVal.toFixed(0)}`);
  _setText('sbShortVal', `$${shortVal.toFixed(0)}`);

  const biasTag = document.getElementById('sbBiasTag');
  if (biasTag) {
    biasTag.textContent = d.global_bias || '无持仓';
    biasTag.className = 'sb-bias-tag';
    if (d.global_bias === '偏多') biasTag.classList.add('sb-bias-long');
    else if (d.global_bias === '偏空') biasTag.classList.add('sb-bias-short');
  }

  const barLong = document.getElementById('sbBarLong');
  if (barLong) {
    barLong.style.width = totalVal > 0 ? `${(longVal / totalVal * 100).toFixed(1)}%` : '50%';
  }

  const detailsEl = document.getElementById('sbPosDetails');
  if (detailsEl) {
    detailsEl.textContent = (d.global_details && d.global_details !== '无') ? d.global_details : '';
  }

  const streaksEl = document.getElementById('sbStreaks');
  if (streaksEl) {
    const arr = d.loss_streaks || [];
    if (arr.length === 0) {
      streaksEl.innerHTML = '<span class="sb-streak-ok">连亏状态: 正常</span>';
    } else {
      streaksEl.innerHTML = arr.map(s => {
        const cls = s.level === 'halt' ? 'sb-streak-halt' : (s.level === 'caution' ? 'sb-streak-caution' : 'sb-streak-warn');
        const label = s.level === 'halt' ? '硬停' : (s.level === 'caution' ? '警戒' : '提醒');
        return `<span class="${cls}">${esc(s.symbol)} 做${esc(s.direction)}连亏${s.streak}次 [${label}]</span>`;
      }).join(' ');
    }
  }

  const adviceEl = document.getElementById('sbAdvice');
  if (adviceEl) {
    adviceEl.textContent = d.market_advice || '';
  }
}

// ===== 信号统计功能 =====
export function loadSignalStats() {
  const token = window.GangziApp?.getToken ? window.GangziApp.getToken() : '';
  if (!token) return;
  fetch(API_BASE + "/api/ai/signal-stats", {
    headers: { "Authorization": "Bearer " + token }
  })
  .then(function(r) { return r.ok ? r.json() : Promise.reject(r.status); })
  .then(function(d) {
    var data = d.data || d;
    renderSignalStats(data);
  })
  .catch(function() {
    var body = document.getElementById("signalStatsBody");
    if (body) body.innerHTML = '<div class="no-data">统计加载失败</div>';
  });
}

function renderSignalStats(data) {
  var badge = document.getElementById("signalStatsTotalBadge");
  if (badge) badge.textContent = "共 " + (data.total_signals || 0).toLocaleString() + " 条信号";

  var body = document.getElementById("signalStatsBody");
  if (!body) return;

  var bd = data.signal_breakdown || {};
  var ts = data.trade_stats || {};
  var ra = data.recent_accuracy || {};
  var bs = data.by_symbol || [];

  var fillRate = ts.total_traded > 0 ? (ts.filled / ts.total_traded * 100).toFixed(1) : "0.0";

  var sigTypes = ["BUY","SELL","SHORT","COVER","HOLD"];
  var sigColors = {BUY:"var(--green)",SELL:"var(--red)",SHORT:"var(--orange,#f59e0b)",COVER:"var(--cyan,#06b6d4)",HOLD:"var(--muted,#94a3b8)"};
  var total = data.total_signals || 1;
  var barHTML = '<div class="ss-bar-wrap">';
  sigTypes.forEach(function(t) {
    var cnt = bd[t] || 0;
    var pct = (cnt / total * 100).toFixed(1);
    if (cnt > 0) barHTML += '<div class="ss-bar-seg" style="width:' + pct + '%;background:' + (sigColors[t]||"#666") + '" title="' + t + ': ' + cnt + ' (' + pct + '%)"></div>';
  });
  barHTML += '</div><div class="ss-bar-legend">';
  sigTypes.forEach(function(t) {
    var cnt = bd[t] || 0;
    if (cnt > 0) barHTML += '<span><i style="background:' + (sigColors[t]||"#666") + '"></i>' + t + ' ' + cnt + '</span>';
  });
  barHTML += '</div>';

  var tradeHTML = '<div class="stats-grid small">';
  tradeHTML += '<div class="stat-item-sm"><span class="stat-sm-label">总交易</span><span class="stat-sm-value">' + ts.total_traded + '</span></div>';
  tradeHTML += '<div class="stat-item-sm"><span class="stat-sm-label">成交</span><span class="stat-sm-value" style="color:var(--green)">' + ts.filled + '</span></div>';
  tradeHTML += '<div class="stat-item-sm"><span class="stat-sm-label">跳过</span><span class="stat-sm-value">' + ts.skipped + '</span></div>';
  tradeHTML += '<div class="stat-item-sm"><span class="stat-sm-label">失败</span><span class="stat-sm-value" style="color:var(--red)">' + ts.failed + '</span></div>';
  tradeHTML += '<div class="stat-item-sm"><span class="stat-sm-label">执行率</span><span class="stat-sm-value">' + fillRate + '%</span></div></div>';

  var recentHTML = '<div class="stats-grid small">';
  var periods = [{key:"last_24h",label:"24h"},{key:"last_7d",label:"7天"},{key:"last_30d",label:"30天"}];
  periods.forEach(function(p) {
    var r = ra[p.key] || {};
    recentHTML += '<div class="stat-item-sm"><span class="stat-sm-label">' + p.label + '</span><span class="stat-sm-value">' + (r.total||0) + ' <small style="color:var(--muted,#94a3b8);font-size:11px">交易' + (r.traded||0) + '</small></span></div>';
  });
  recentHTML += '</div>';

  var tableHTML = "";
  if (bs.length > 0) {
    tableHTML = '<div class="ss-table-wrap"><table class="ss-table"><thead><tr><th>币种</th><th>信号</th><th>BUY</th><th>SELL</th><th>HOLD</th><th>交易</th><th>成交</th><th>置信度</th></tr></thead><tbody>';
    bs.forEach(function(s) {
      tableHTML += '<tr><td><b>' + s.symbol.replace("USDT","") + '</b></td><td>' + s.total + '</td><td style="color:var(--green)">' + s.buy_count + '</td><td style="color:var(--red)">' + s.sell_count + '</td><td>' + s.hold_count + '</td><td>' + s.traded + '</td><td>' + s.filled + '</td><td>' + s.avg_confidence + '%</td></tr>';
    });
    tableHTML += '</tbody></table></div>';
  }

  body.innerHTML = barHTML
    + '<div class="trade-section-title" style="margin-top:12px">交易执行</div>' + tradeHTML
    + '<div class="trade-section-title" style="margin-top:12px">近期信号量</div>' + recentHTML
    + (tableHTML ? '<div class="trade-section-title" style="margin-top:12px">按币种统计</div>' + tableHTML : "");
}

// ---------- 引擎状态 ----------
export function renderEngineStatus(symbols) {
  const card = document.getElementById('engineStatusCard');
  const grid = document.getElementById('engineStatusGrid');
  if (!card || !grid) return;
  if (!symbols || !symbols.length) {
    card.style.display = 'none';
    grid.dataset.renderSig = 'empty';
    return;
  }

  const sig = symbols.map(s => [s.symbol, s.status, s.cooldown_remaining, s.atr_pct, s.sl_streak, s.pause_remaining].join(':')).join('|');
  if (grid.dataset.renderSig === sig) {
    card.style.display = '';
    return;
  }
  grid.dataset.renderSig = sig;
  card.style.display = '';
  grid.innerHTML = symbols.map(s => {
    const inCooldown = s.status === 'cooldown' || s.cooldown_remaining > 0;
    const isPaused = s.status === 'paused' || s.pause_remaining > 0;
    const cdClass = inCooldown ? 'color:#f97316' : 'color:#22c55e';
    const pauseTag = isPaused ? '<span style="color:#ef4444;font-weight:600">已暂停</span>' : '';
    const cdText = inCooldown ? 'CD ' + (s.cooldown_remaining || 0) + 's' : '就绪';
    return `<div class="engine-sym-row">
      <b>${s.symbol}</b>
      <span style="${cdClass}">${cdText}</span>
      <span>ATR ${s.atr_pct != null ? s.atr_pct.toFixed(2) + '%' : '--'}</span>
      <span>连亏 ${s.sl_streak || 0}</span>
      ${pauseTag}
    </div>`;
  }).join('');
}
