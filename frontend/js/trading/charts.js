/**
 * 钢子出击 - 交易面板图表模块
 * 准确率趋势图、净值曲线、策略对比图
 */
import { state } from './utils.js';

// ====== 准确率趋势图 ======
export function renderAccuracyDailyTrend(acc) {
  const canvas = document.getElementById('tradeAccuracyDailyChart');
  const hint = document.getElementById('tradeAccuracyDailyHint');
  if (!canvas) return;

  const series = Array.isArray(acc.by_day) ? acc.by_day : [];
  if (typeof Chart === 'undefined') {
    if (hint) hint.textContent = 'Chart.js 未加载，无法绘制趋势图';
    return;
  }

  if (!series.length) {
    if (hint) hint.textContent = '暂无按天趋势数据';
    if (state._tradeAccDailyChart) {
      state._tradeAccDailyChart.destroy();
      state._tradeAccDailyChart = null;
    }
    return;
  }

  const labels = series.map((d) => String(d.date || '--').slice(5));
  const values = series.map((d) => Number(d.accuracy || 0));
  const latest = series[series.length - 1] || {};
  const titleEl = canvas.closest('.accuracy-by-symbol')?.querySelector('.accuracy-section-title');
  if (titleEl) {
    const dateRange = labels.length === 1 ? labels[0] : labels[0] + ' ~ ' + labels[labels.length - 1];
    titleEl.textContent = dateRange + ' 按天准确率变化';
  }
  if (hint) {
    const w = acc.trend_window_days || (state._tradeAccDays || 0);
    hint.textContent = `区间: ${state._tradeAccDays === 0 ? `最近${w}天` : `${state._tradeAccDays}天`} · 最新 ${Number(latest.accuracy || 0).toFixed(1)}%（${latest.correct || 0}对/${latest.incorrect || 0}错）`;
  }

  if (state._tradeAccDailyChart) {
    state._tradeAccDailyChart.destroy();
    state._tradeAccDailyChart = null;
  }
  state._tradeAccDailyChart = new Chart(canvas, {
      type: 'line',
      ...(state._isMobileTP ? {devicePixelRatio: 1} : {}),
      data: {
        labels,
        datasets: [
          {
            label: '方向准确率(%)',
            data: values,
            borderColor: '#22c55e',
            backgroundColor: 'rgba(34, 197, 94, 0.12)',
            fill: true,
            tension: 0.32,
            pointRadius: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: state._isMobileTP ? false : undefined,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, max: 100, ticks: { stepSize: 25, font: { size: 11 } } },
          x: { display: false },
        },
      },
    });
}

// ---------- 净值曲线 ----------
export function renderDailyPnlChart(rows) {
  const canvas = document.getElementById('dailyPnlChart');
  const empty = document.getElementById('dailyPnlEmpty');
  if (!canvas) return;
  if (!rows || !rows.length) {
    canvas.style.display = 'none';
    if (empty) empty.style.display = '';
    return;
  }
  canvas.style.display = '';
  if (empty) empty.style.display = 'none';
  if (typeof Chart === 'undefined') return;
  const labels = rows.map(r => r.date);
  let _cumPnl = 0;
  const values = rows.map(r => {
    if (r.cumulative_pnl != null) return r.cumulative_pnl;
    if (r.net_pnl != null) { _cumPnl += r.net_pnl; return _cumPnl; }
    if (r.realized_pnl != null) { _cumPnl += r.realized_pnl; return _cumPnl; }
    return r.pnl || 0;
  });
  if (state._dailyPnlChartInst) {
    state._dailyPnlChartInst.destroy();
    state._dailyPnlChartInst = null;
  }
  state._dailyPnlChartInst = new Chart(canvas, {
      type: 'line',
      ...(state._isMobileTP ? {devicePixelRatio: 1} : {}),
      data: {
        labels,
        datasets: [{
          label: '累计盈亏 (USDT)',
          data: values,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59,130,246,0.08)',
          fill: true,
          tension: 0.3,
          pointRadius: 2,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { maxTicksLimit: 8, font: { size: 10 } }, grid: { display: false } },
          y: { ticks: { font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } },
        },
      },
    });
}

// ---------- 策略 vs BTC ----------
export function renderBenchmarkChart(data) {
  const canvas = document.getElementById('benchmarkChart');
  const empty = document.getElementById('benchmarkEmpty');
  if (!canvas) return;
  let labels, strat, btcArr;
  if (data.rows && data.rows.length) {
    labels = data.rows.map(r => r.date);
    strat = data.rows.map(r => r.strategy_pct != null ? r.strategy_pct : 0);
    btcArr = data.rows.map(r => r.btc_pct != null ? r.btc_pct : 0);
  } else if (data.strategy && data.strategy.dates) {
    labels = data.strategy.dates;
    const sVals = data.strategy.cum_net_pnl_usdt || data.strategy.values || [];
    const bVals = data.btc.cum_return_pct || data.btc.values || [];
    const baseEquity = sVals[0] || 1;
    strat = sVals.map(v => ((v - baseEquity) / Math.abs(baseEquity) * 100));
    btcArr = bVals.map(v => v != null ? v : 0);
  } else {
    canvas.style.display = 'none';
    if (empty) empty.style.display = '';
    return;
  }
  if (!labels || !labels.length) {
    canvas.style.display = 'none';
    if (empty) empty.style.display = '';
    return;
  }
  canvas.style.display = '';
  if (empty) empty.style.display = 'none';
  if (typeof Chart === 'undefined') return;
  const btc = btcArr;
  if (state._benchmarkChartInst) {
    state._benchmarkChartInst.destroy();
    state._benchmarkChartInst = null;
  }
  state._benchmarkChartInst = new Chart(canvas, {
      type: 'line',
      ...(state._isMobileTP ? {devicePixelRatio: 1} : {}),
      data: {
        labels,
        datasets: [
          { label: '策略', data: strat, borderColor: '#3b82f6', tension: 0.3, pointRadius: 1, borderWidth: 2 },
          { label: 'BTC', data: btc, borderColor: '#f97316', tension: 0.3, pointRadius: 1, borderWidth: 2 },
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { font: { size: 10 }, boxWidth: 12 } } },
        scales: {
          x: { ticks: { maxTicksLimit: 8, font: { size: 10 } }, grid: { display: false } },
          y: { ticks: { font: { size: 10 }, callback: v => v + '%' }, grid: { color: 'rgba(255,255,255,0.04)' } },
        },
      },
    });
}
