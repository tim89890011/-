/**
 * 钢子出击 - 交易面板样式
 * 所有交易面板 CSS 样式的注入
 */

export function addTradingStyles() {
  if (document.getElementById('tradingPanelStyles')) return;

  const s = document.createElement('style');
  s.id = 'tradingPanelStyles';
  s.textContent = `

    /* === 信号统计卡片样式 === */
    .ss-bar-wrap{display:flex;height:20px;border-radius:6px;overflow:hidden;margin-bottom:8px;background:var(--surface,#1e293b);}
    .ss-bar-seg{min-width:2px;transition:width .3s;}
    .ss-bar-legend{display:flex;flex-wrap:wrap;gap:8px 14px;font-size:12px;color:var(--text-muted,#94a3b8);}
    .ss-bar-legend span{display:flex;align-items:center;gap:4px;}
    .ss-bar-legend i{display:inline-block;width:10px;height:10px;border-radius:2px;}
    .ss-table-wrap{overflow-x:auto;margin-top:4px;}
    .ss-table{width:100%;border-collapse:collapse;font-size:12px;}
    .ss-table th{text-align:left;padding:6px 8px;color:var(--text-muted,#94a3b8);border-bottom:1px solid var(--border,#334155);font-weight:500;}
    .ss-table td{padding:5px 8px;border-bottom:1px solid var(--border,#1e293b);}
    .ss-table tr:hover td{background:rgba(59,130,246,0.08);}

    /* === 两列列表：固定同屏条数对齐（7条）=== */
    :root {
      --list-rows: 7;
      --trade-row-h: 56px;
      --pos-row-h: 74px;
      --pos-gap: 10px;
    }

    /* === 交易开关按钮 === */
    .trade-toggle-wrap { display:flex; gap:8px; align-items:center; justify-content:flex-end; flex-wrap:wrap; }
    .trade-toggle-btn {
      display: flex; align-items: center; gap: 6px;
      padding: 8px 18px; border-radius: 10px; border: none;
      font-size: 13px; font-weight: 600; cursor: pointer;
      transition: all 0.25s ease;
      white-space: nowrap;
      max-width: 100%;
    }
    .trade-toggle-btn.pending { opacity: 0.9; }
    .trade-toggle-btn.active {
      background: linear-gradient(135deg, #22c55e, #16a34a);
      color: #fff; box-shadow: 0 4px 12px rgba(34,197,94,0.3);
    }
    .trade-toggle-btn.paused {
      background: linear-gradient(135deg, #f59e0b, #d97706);
      color: #fff; box-shadow: 0 4px 12px rgba(245,158,11,0.3);
    }
    .trade-toggle-btn.disabled {
      background: rgba(100,116,139,0.3); color: var(--text3, #94a3b8); cursor: not-allowed;
    }
    .trade-toggle-btn:not(.disabled):hover { transform: translateY(-1px); filter: brightness(1.1); }
    .toggle-icon { font-size: 14px; }

    /* === 账户总览英雄区 === */
    .account-hero {
      display: grid; grid-template-columns: 2fr 3fr; gap: 12px; align-items: stretch;
    }
    @media (max-width: 768px) {
      .account-hero { grid-template-columns: 1fr; }
    }
    .account-hero-main {
      padding: 20px 24px; border-radius: 12px;
      background:
        linear-gradient(135deg, rgba(59,130,246,0.13), rgba(139,92,246,0.10), rgba(59,130,246,0.13));
      background-size: 200% 200%;
      animation: heroShimmer 6s ease-in-out infinite;
      border: 1px solid rgba(59,130,246,0.18);
      box-shadow: 0 2px 16px rgba(59,130,246,0.08), 0 0 0 1px rgba(139,92,246,0.04);
      display: flex; flex-direction: column; justify-content: flex-start;
      position: relative; overflow: hidden;
    }
    .account-hero-main::after {
      content: ''; position: absolute; top: -50%; left: -50%;
      width: 200%; height: 200%;
      background: radial-gradient(circle, rgba(255,255,255,0.07) 0%, transparent 70%);
      animation: heroGlow 4s ease-in-out infinite alternate;
      pointer-events: none;
    }
    @keyframes heroShimmer {
      0%,100% { background-position: 0% 50%; }
      50% { background-position: 100% 50%; }
    }
    @keyframes heroGlow {
      0% { transform: translate(-10%, -10%); opacity: 0; }
      100% { transform: translate(10%, 10%); opacity: 1; }
    }
    @media (max-width: 768px) {
      .account-hero-main::before,
      .account-hero-main::after {
        animation: none !important;
        display: none !important;
      }
    }
    .account-hero-label { font-size: 14px; color: var(--text3); margin-bottom: 8px; }
    .account-hero-value { font-size: 36px; font-weight: 800; color: var(--text); letter-spacing: -0.5px; font-variant-numeric: tabular-nums; }
    .account-hero-sub { font-size: 15px; margin-top: 8px; }
    .account-hero-sub.profit { color: var(--green); }
    .account-hero-sub.loss { color: var(--red); }
    .account-hero-sub.neutral { color: var(--text3); }

    .account-hero-grid {
      display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px;
    }
    .account-stat {
      display: flex; flex-direction: column; gap: 4px;
      padding: 14px 16px; border-radius: 10px;
      background: var(--bg2); border: 1px solid var(--border);
    }
    .account-stat-label { font-size: 12px; color: var(--text3); }
    .account-stat-value { font-size: 16px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }

    /* === 今日战绩 === */
    .stats-grid {
      display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px;
      contain: layout style;
    }
    .stat-item {
      text-align: center; padding: 16px 12px; border-radius: 12px;
      background: var(--bg2); border: 1px solid var(--border);
      min-height: 72px;
    }
    .stat-number { font-size: 24px; font-weight: 800; color: var(--text); font-variant-numeric: tabular-nums; }
    .stat-label { font-size: 12px; color: var(--text3); margin-top: 4px; }

    .stats-grid.small { grid-template-columns: repeat(2, 1fr); gap: 8px; }
    .stat-item-sm {
      display: flex; justify-content: space-between; align-items: center;
      padding: 10px 14px; border-radius: 8px;
      background: var(--bg2); border: 1px solid var(--border);
    }
    .stat-sm-label { font-size: 12px; color: var(--text3); }
    .stat-sm-value { font-size: 13px; font-weight: 600; color: var(--text); font-variant-numeric: tabular-nums; }

    .trade-section-title {
      font-size: 13px; color: var(--text3);
      margin: 16px 0 10px; padding-top: 12px;
      border-top: 1px solid var(--border);
    }

    /* === 策略配置 === */
    .strategy-name {
      font-size: 18px; font-weight: 700; color: var(--blue);
      margin-bottom: 16px; padding-bottom: 12px;
      border-bottom: 1px solid var(--border);
    }
    .strategy-items { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
    .strategy-item {
      display: flex; align-items: center; gap: 10px;
      padding: 12px 14px; border-radius: 10px;
      background: var(--bg2); border: 1px solid var(--border);
    }
    .strategy-item-wide { grid-column: 1 / -1; }
    @media (max-width: 900px) { .strategy-items { grid-template-columns: repeat(2, 1fr); } }
    @media (max-width: 480px) { .strategy-items { grid-template-columns: 1fr; } }
    .strategy-icon { font-size: 18px; flex-shrink: 0; color: var(--text3); }
    .strategy-detail { flex: 1; }
    .strategy-item-label { font-size: 12px; color: var(--text3); }
    .strategy-item-value { font-size: 14px; font-weight: 600; color: var(--text); display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
    .symbol-tag {
      display: inline-block; font-size: 12px; font-weight: 600;
      padding: 2px 8px; border-radius: 4px;
      background: var(--blue-bg, rgba(0,122,255,0.08)); color: var(--blue, #007AFF);
    }

    /* === 余额格子 === */
    .trade-balance-grid {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 10px;
    }
    .trade-balance-item {
      text-align: center; padding: 14px; border-radius: 10px;
      background: var(--bg2); border: 1px solid var(--border);
    }
    .balance-currency { font-size: 13px; font-weight: 600; color: var(--blue); margin-bottom: 4px; }
    .balance-amount { font-size: 18px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
    .balance-sub { font-size: 11px; color: var(--text3); margin-top: 2px; }

    /* === 持仓盈亏 === */
    .pos-list, .engine-status-grid, .pnl-chart-wrap, #tradeListContainer { contain: content; }
    .pos-list {
      display: flex; flex-direction: column; gap: var(--pos-gap);
      min-height: 80px; contain: layout style;
      /* 固定同屏 7 条（超出滚动） */
      height: calc(var(--pos-row-h) * var(--list-rows) + var(--pos-gap) * var(--list-rows) - var(--pos-gap));
      overflow-y: auto;
    }
    .pos-card {
      display: flex; align-items: center; gap: 14px;
      padding: 14px 16px; border-radius: 12px;
      background: var(--bg2); border: 1px solid var(--border);
      transition: transform 0.15s ease;
      /* 固定条目高度，保证"条数对齐"稳定 */
      box-sizing: border-box;
      height: var(--pos-row-h);
    }
    .pos-card:hover { transform: translateY(-1px); }
    .pos-coin-icon {
      width: 42px; height: 42px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-weight: 700; font-size: 13px; color: #fff; flex-shrink: 0;
    }
    .pos-coin-icon.btc { background: linear-gradient(135deg, #f7931a, #e8850d); }
    .pos-coin-icon.eth { background: linear-gradient(135deg, #627eea, #4a6bd4); }
    .pos-coin-icon.other { background: linear-gradient(135deg, #8b5cf6, #7c3aed); }
    .pos-info { flex: 1; min-width: 0; }
    .pos-info-top { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
    .pos-symbol { font-size: 15px; font-weight: 700; color: var(--text); }
    .pos-side-tag {
      font-size: 11px; font-weight: 600; padding: 1px 6px; border-radius: 4px;
      line-height: 1.4; flex-shrink: 0;
    }
    .pos-side-long { background: var(--green-bg); color: var(--green); }
    .pos-side-short { background: var(--red-bg); color: var(--red); }
    .pos-qty { font-size: 12px; color: var(--text3); }
    /* 防止换行导致单条高度变化 */
    .pos-symbol, .pos-qty { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .pos-info-mid {
      display: flex; gap: 16px; margin-top: 4px;
      font-size: 12px; color: var(--text3);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .pos-info-mid > span { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
    .pos-pnl-area { text-align: right; flex-shrink: 0; }
    .pos-pnl-amount { font-size: 16px; font-weight: 700; font-variant-numeric: tabular-nums; }
    .pos-pnl-amount.profit { color: var(--green); }
    .pos-pnl-amount.loss { color: var(--red); }
    .pos-pnl-pct { font-size: 12px; margin-top: 2px; }
    .pos-pnl-pct.profit { color: var(--green); }
    .pos-pnl-pct.loss { color: var(--red); }
    .pos-close-btn {
      font-size: 10px; font-weight: 600;
      padding: 3px 10px; border-radius: 6px;
      border: 1px solid var(--red); cursor: pointer;
      background: transparent; color: var(--red);
      transition: all 0.2s ease; white-space: nowrap;
      margin-left: 6px; vertical-align: middle; line-height: 1.2;
    }
    .pos-close-btn:hover { background: var(--red); color: #fff; box-shadow: 0 2px 8px rgba(255,71,87,0.3); }
    .pos-close-btn:active { transform: scale(0.95); }
    .pos-market-value { font-size: 11px; color: var(--text3); margin-top: 2px; }

    /* === 交易记录过滤开关 === */
    .trade-filter-toggle {
      display: flex; align-items: center; gap: 4px;
      font-size: 12px; color: var(--text3); cursor: pointer; user-select: none;
    }
    .trade-filter-toggle input { width: 14px; height: 14px; cursor: pointer; }

    /* === 交易记录 === */
    .trade-history-list {
      overflow-y: auto; min-height: 60px; contain: layout style;
      /* 高度与右侧持仓列表对齐，避免"只到一半就要滚动" */
      height: calc(var(--pos-row-h) * var(--list-rows) + var(--pos-gap) * var(--list-rows) - var(--pos-gap));
      max-height: none;
    }
    .trade-record {
      display: flex; align-items: center; gap: 12px;
      padding: 10px 0; border-bottom: 1px solid var(--border);
      /* 固定条目高度，保证"条数对齐"稳定 */
      box-sizing: border-box;
      height: var(--trade-row-h);
    }
    .trade-record:last-child { border-bottom: none; }
    .trade-record.trade-dimmed { opacity: 0.55; }
    .trade-side {
      font-size: 12px; font-weight: 700; padding: 3px 10px;
      border-radius: 6px; min-width: 40px; text-align: center;
    }
    .trade-side.buy { background: var(--green-bg); color: var(--green); }
    .trade-side.sell { background: var(--red-bg); color: var(--red); }
    .trade-side.short { background: var(--red-bg); color: var(--red); }
    .trade-side.cover { background: var(--green-bg); color: var(--green); }
    .trade-side.skip { background: rgba(142,142,147,0.12); color: var(--text3); }
    .trade-detail { flex: 1; min-width: 0; }
    .trade-detail-top {
      font-size: 14px; font-weight: 600; color: var(--text);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .trade-detail-bottom {
      font-size: 12px; color: var(--text3); margin-top: 2px;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    /* 盈亏高亮药丸 — 右侧独立显示，一眼可见 */
    .trade-pnl-pill {
      flex-shrink: 0; font-size: 13px; font-weight: 700;
      padding: 3px 10px; border-radius: 8px;
      font-variant-numeric: tabular-nums;
      letter-spacing: -0.3px; white-space: nowrap;
    }
    .trade-pnl-pill.profit {
      color: var(--green); background: var(--green-bg);
    }
    .trade-pnl-pill.loss {
      color: var(--red); background: var(--red-bg);
    }
    .trade-status-tag { font-size: 11px; padding: 2px 8px; border-radius: 4px; }
    .trade-status-tag.filled { background: var(--green-bg); color: var(--green); }
    .trade-status-tag.failed { background: var(--red-bg); color: var(--red); }
    .trade-status-tag.skipped { background: rgba(142,142,147,0.10); color: var(--text3); }
    .trade-status-tag.pending { background: var(--blue-bg); color: var(--blue); }

    /* 行内平仓原因（底部文字行末尾） */
    .close-reason { font-weight: 700; }
    .close-reason.tp     { color: var(--green);  }
    .close-reason.sl     { color: var(--red);    }
    .close-reason.trail  { color: var(--blue);   }
    .close-reason.timeout{ color: var(--yellow); }
    .close-reason.flip   { color: var(--purple); }
    .close-reason.manual { color: var(--blue, #3b82f6);  }

    /* === AI 准确率 === */
    .accuracy-by-type {
      display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap;
    }
    .accuracy-type-item {
      flex: 1; min-width: 90px;
      text-align: center; padding: 10px 8px; border-radius: 10px;
      background: var(--bg2); border: 1px solid var(--border);
    }
    .accuracy-type-label { font-size: 12px; font-weight: 600; margin-bottom: 4px; }
    .accuracy-type-label.buy { color: var(--green); }
    .accuracy-type-label.sell { color: var(--red); }
    .accuracy-type-label.short { color: var(--red); }
    .accuracy-type-label.cover { color: var(--green); }
    .accuracy-type-label.hold { color: var(--text3); }
    .accuracy-type-value { font-size: 18px; font-weight: 800; color: var(--text); font-variant-numeric: tabular-nums; }
    .accuracy-type-sub { font-size: 11px; color: var(--text3); margin-top: 2px; }

    /* 各币种验证结果 */
    .accuracy-by-symbol { margin-top: 16px; }
    .accuracy-section-title {
      font-size: 12px; font-weight: 600; color: var(--text3);
      margin-bottom: 10px; padding-bottom: 6px;
      border-bottom: 1px solid var(--border);
    }
    .accuracy-symbol-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 8px;
    }
    .accuracy-symbol-item {
      display: flex; flex-direction: column; align-items: center;
      padding: 10px 6px; border-radius: 10px;
      background: var(--bg2); border: 1px solid var(--border);
      text-align: center; gap: 3px;
    }
    .accuracy-sym-name { font-size: 12px; font-weight: 700; color: var(--text); }
    .accuracy-sym-pct { font-size: 18px; font-weight: 800; font-variant-numeric: tabular-nums; }
    .accuracy-sym-pct.acc-good { color: var(--green); }
    .accuracy-sym-pct.acc-mid { color: var(--yellow, #f59e0b); }
    .accuracy-sym-pct.acc-bad { color: var(--red); }
    .accuracy-sym-detail { font-size: 10px; color: var(--text3); }

    /* 一键平仓按钮 */
    .btn-close-all {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 4px 12px; border-radius: 6px;
      background: var(--red, #ef4444); color: #fff;
      border: none; font-size: 12px; font-weight: 600;
      cursor: pointer; transition: all 0.2s;
      white-space: nowrap;
    }
    .btn-close-all:hover { opacity: 0.85; transform: scale(1.02); }
    .btn-close-all:active { transform: scale(0.96); }
    .btn-close-all:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
    .btn-close-all i { font-size: 14px; }

    /* 响应式 */
    @media (max-width: 600px) {
      .stats-grid { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 420px) {
      .trade-toggle-wrap { gap: 6px; }
      .trade-toggle-btn { padding: 8px 12px; }
    }

    /* === 通用确认弹窗（替代 window.confirm，兼容 Safari/WebView） === */
    .gz-modal-overlay {
      position: fixed; inset: 0;
      background: rgba(2, 6, 23, 0.62);
      display: none;
      align-items: center; justify-content: center;
      z-index: 9999;
      padding: 16px;
    }
    .gz-modal-overlay.show { display: flex; }
    .gz-modal {
      width: min(460px, 100%);
      background: rgba(15, 23, 42, 0.95);
      border: 1px solid rgba(148, 163, 184, 0.25);
      border-radius: 14px;
      box-shadow: 0 18px 60px rgba(0,0,0,0.5);
      color: var(--text, #e2e8f0);
      overflow: hidden;
    }
    .gz-modal-head { padding: 14px 16px; border-bottom: 1px solid rgba(148, 163, 184, 0.18); font-weight: 800; }
    .gz-modal-body { padding: 12px 16px; color: var(--text2, #cbd5e1); font-size: 13px; line-height: 1.55; white-space: pre-wrap; }
    .gz-modal-actions { padding: 12px 16px; display: flex; justify-content: flex-end; gap: 10px; border-top: 1px solid rgba(148, 163, 184, 0.18); }

    /* 亮色模式弹窗适配 */
    body.light-theme .gz-modal-overlay { background: rgba(0,0,0,0.3); }
    body.light-theme .gz-modal {
      background: rgba(255,255,255,0.95);
      border-color: rgba(0,0,0,0.1);
      box-shadow: 0 18px 60px rgba(0,0,0,0.15);
    }
    body.light-theme .gz-modal-head { color: #1c1c1e; border-bottom-color: rgba(0,0,0,0.08); }
    body.light-theme .gz-modal-body { color: #48484a; }
    body.light-theme .gz-modal-actions { border-top-color: rgba(0,0,0,0.08); }
    .gz-btn {
      border: 1px solid rgba(148, 163, 184, 0.28);
      background: rgba(15, 23, 42, 0.55);
      color: var(--text, #e2e8f0);
      padding: 8px 12px;
      border-radius: 10px;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.15s ease;
      white-space: nowrap;
    }
    .gz-btn:hover { filter: brightness(1.08); transform: translateY(-1px); }
    .gz-btn:active { transform: translateY(0px) scale(0.98); }
    .gz-btn-danger {
      border-color: rgba(239, 68, 68, 0.35);
      background: rgba(239, 68, 68, 0.16);
      color: #fecaca;
    }
    #signalStatsBody { max-height: 400px; overflow-y: auto; }
    #tradingFeedSlot .card-body { max-height: 500px; overflow-y: auto; }
    #signalStatsBody::-webkit-scrollbar,
    #tradingFeedSlot .card-body::-webkit-scrollbar { width: 4px; }
    #signalStatsBody::-webkit-scrollbar-thumb,
    #tradingFeedSlot .card-body::-webkit-scrollbar-thumb { background: #ccc; border-radius: 2px; }
  `;
  document.head.appendChild(s);
}

// 最强大脑卡片样式（动态注入）
(function injectSuperbrainCSS() {
  if (document.getElementById('sb-style')) return;
  const style = document.createElement('style');
  style.id = 'sb-style';
  style.textContent = `
    .superbrain-card { border-left: 3px solid #a855f7; }
    .sb-grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 12px; margin-bottom: 14px; }
    .sb-item { display: flex; flex-direction: column; gap: 2px; }
    .sb-label { font-size: 12px; color: var(--text-secondary, #b0b8c4); }
    .sb-value { font-size: 14px; font-weight: 600; color: var(--text-primary, #e8ecf1); }
    .sb-up { color: #22c55e !important; }
    .sb-down { color: #ef4444 !important; }
    .sb-position-bar { margin-bottom: 12px; }
    .sb-bar-label { display: flex; justify-content: space-between; align-items: center; font-size: 12px; margin-bottom: 4px; color: var(--text-secondary, #b0b8c4); }
    .sb-bar-label b { color: var(--text-primary, #e8ecf1); }
    .sb-bias-tag { font-size: 11px; padding: 1px 8px; border-radius: 10px; background: var(--bg-tertiary, #333); }
    .sb-bias-long { background: rgba(34,197,94,0.15); color: #22c55e; }
    .sb-bias-short { background: rgba(239,68,68,0.15); color: #ef4444; }
    .sb-bar-track { height: 6px; border-radius: 3px; background: rgba(239,68,68,0.3); overflow: hidden; }
    .sb-bar-long { height: 100%; background: #22c55e; border-radius: 3px 0 0 3px; transition: width 0.5s ease; }
    .sb-pos-details { font-size: 11px; color: var(--text-secondary, #b0b8c4); margin-top: 4px; }
    .sb-streaks { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
    .sb-streak-ok { font-size: 12px; color: #22c55e; }
    .sb-streak-warn { font-size: 12px; padding: 2px 8px; border-radius: 10px; background: rgba(239,68,68,0.12); color: #ef4444; }
    .sb-streak-caution { font-size: 12px; padding: 2px 8px; border-radius: 10px; background: rgba(249,115,22,0.15); color: #f97316; font-weight: 600; }
    .sb-streak-halt { font-size: 12px; padding: 2px 8px; border-radius: 10px; background: rgba(239,68,68,0.18); color: #ef4444; font-weight: 700; }
    .sb-advice { font-size: 12px; color: var(--text-secondary, #b0b8c4); font-style: italic; }
    .badge-purple { background: rgba(168,85,247,0.15); color: #a855f7; }
    .sl-pause-bar { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border, rgba(255,255,255,0.06)); }
    .sl-pause-tag { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; padding: 3px 10px; border-radius: 12px; font-weight: 500; }
    .sl-pause-tag i { font-size: 13px; }
    .sl-paused { background: rgba(239,68,68,0.12); color: #ef4444; }
    .sl-warning { background: rgba(249,115,22,0.12); color: #f97316; }
    @media (max-width: 600px) { .sb-grid { grid-template-columns: 1fr 1fr; } }
  `;
  document.head.appendChild(style);
})();
