/**
 * 钢子出击 - 图表管理
 * 用 Chart.js 渲染各类图表
 */

let btcChartInstance = null;
const CHART_DEBUG = false;
const API_BASE = window.API_BASE || window.location.origin;

async function ensureChartReady(maxWaitMs = 4000) {
    const start = Date.now();
    while (typeof window.Chart !== 'function') {
        if (Date.now() - start > maxWaitMs) return false;
        await new Promise(r => setTimeout(r, 80));
    }
    return true;
}

// BTC 价格走势图
async function initBtcChart() {
    const canvas = document.getElementById('btcChart');
    if (!canvas) return;

    try {
        const resp = await window.authFetch(`${API_BASE}/api/market/kline/BTCUSDT?interval=1h&limit=48`);
        if (!resp.ok) return;
        const data = await resp.json();
        const klines = data.data || [];

        if (klines.length === 0) return;

        const labels = klines.map(k => {
            const d = new Date(k.time);
            return `${d.getHours().toString().padStart(2, '0')}:00`;
        });
        const prices = klines.map(k => k.close);

        // 渐变
        const ctx = canvas.getContext('2d');
        const gradient = ctx.createLinearGradient(0, 0, 0, 280);
        gradient.addColorStop(0, 'rgba(59, 130, 246, 0.3)');
        gradient.addColorStop(1, 'rgba(59, 130, 246, 0)');

        if (btcChartInstance) btcChartInstance.destroy();

        btcChartInstance = new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'BTC/USDT',
                    data: prices,
                    borderColor: '#3b82f6',
                    borderWidth: 2,
                    backgroundColor: gradient,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    pointHoverBackgroundColor: '#3b82f6',
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(20, 24, 32, 0.95)',
                        titleColor: '#e8ecf1',
                        bodyColor: '#b0b8c4',
                        borderColor: '#232a36',
                        borderWidth: 1,
                        padding: 10,
                        callbacks: {
                            label: (ctx) => `$${ctx.raw.toLocaleString('en-US', { maximumFractionDigits: 2 })}`,
                        },
                    },
                },
                scales: {
                    x: {
                        ticks: { color: '#6b7585', font: { size: 10 }, maxTicksLimit: 12 },
                        grid: { color: 'rgba(35,42,54,0.5)' },
                    },
                    y: {
                        ticks: {
                            color: '#6b7585',
                            font: { size: 10 },
                            callback: v => '$' + v.toLocaleString(),
                        },
                        grid: { color: 'rgba(35,42,54,0.5)' },
                    },
                },
            },
        });

    } catch (e) {
        if (CHART_DEBUG) console.warn('BTC 图表加载失败:', e);
    }
}

// 指标面板
async function loadIndicatorPanel() {
    const panel = document.getElementById('indicatorPanel');
    if (!panel) return;

    try {
        const resp = await window.authFetch(`${API_BASE}/api/market/indicators/BTCUSDT`);
        if (!resp.ok) { panel.innerHTML = '<div class="no-data">加载失败</div>'; return; }
        const data = await resp.json();
        const ind = data.indicators || {};
        if (ind.error) { panel.innerHTML = `<div class="no-data">${ind.error}</div>`; return; }

        // #4 修复：深层属性全部加 null guard
        const rsi = ind.rsi ?? 50;
        const macd = ind.macd || {};
        const bb = ind.bollinger || {};
        const ma = ind.ma || {};
        const macdHist = macd.histogram ?? 0;
        const rsiToneCls = rsi > 70 ? 'text-down' : rsi < 30 ? 'text-up' : 'text-mid';
        const macdToneCls = macdHist > 0 ? 'text-up' : 'text-down';

        const rsiLabel = rsi > 70 ? '超买' : rsi < 30 ? '超卖' : '中性';

        panel.innerHTML = `
        <div class="panel-grid-2">
            <div class="panel-card">
                <div class="panel-label-sm">RSI(14)</div>
                <div class="panel-value-lg ${rsiToneCls}">${rsi}</div>
                <div class="panel-note-sm ${rsiToneCls}">${rsiLabel}</div>
            </div>
            <div class="panel-card">
                <div class="panel-label-sm">MACD</div>
                <div class="panel-kv-title ${macdToneCls}">${macdHist > 0 ? '多头' : '空头'}</div>
                <div class="panel-note-sm">DIF: ${macd.dif ?? 0}</div>
            </div>
            <div class="panel-card">
                <div class="panel-label-sm">布林带</div>
                <div class="panel-kv-list">
                    <span class="text-down">↑${bb.upper ?? 0}</span><br>
                    <span class="text-muted">─${bb.middle ?? 0}</span><br>
                    <span class="text-up">↓${bb.lower ?? 0}</span>
                </div>
            </div>
            <div class="panel-card">
                <div class="panel-label-sm">均线</div>
                <div class="panel-ma-list">
                    <div>MA7: ${ma.ma7 ?? 0}</div>
                    <div>MA25: ${ma.ma25 ?? 0}</div>
                    <div>MA99: ${ma.ma99 ?? 0}</div>
                </div>
            </div>
        </div>`;

    } catch (e) {
        panel.innerHTML = '<div class="no-data">指标加载失败</div>';
    }
}

// ============ #42 修复：合并 funding 请求，避免两个图表重复请求同一 API ============
let _fundingDataCache = null;
let _fetchFundingPromise = null;

async function _fetchFundingDataOnce() {
    if (_fundingDataCache) return _fundingDataCache;
    if (_fetchFundingPromise) return _fetchFundingPromise;

    const token = window.GangziApp?.getToken ? window.GangziApp.getToken() : '';
    const symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT'];

    // 改为只发一次批量/多并发请求并用 Promise 锁住，避免短时间内被调用两次导致竞争
    _fetchFundingPromise = Promise.allSettled(
        symbols.map(sym => fetch(`${API_BASE}/api/market/funding/${sym}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        }).then(r => r.ok ? r.json() : null).catch(() => null))
    ).then(results => {
        _fundingDataCache = { symbols, results };
        // 30 秒后过期
        setTimeout(() => { _fundingDataCache = null; _fetchFundingPromise = null; }, 30000);
        return _fundingDataCache;
    });

    return _fetchFundingPromise;
}

// ============ 资金费率走势图 ============
let fundingChartInstance = null;

async function initFundingChart() {
    const canvas = document.getElementById('fundingChart');
    if (!canvas) return;

    try {
        const { symbols, results } = await _fetchFundingDataOnce();

        const rates = [];
        const labels = [];
        for (let i = 0; i < symbols.length; i++) {
            if (results[i].status === 'fulfilled' && results[i].value) {
                rates.push(parseFloat(results[i].value.funding_rate || 0) * 100);
                labels.push(symbols[i].replace('USDT', ''));
            }
        }

        if (rates.length === 0) return;

        const colors = rates.map(v => v >= 0 ? 'rgba(0,214,143,0.7)' : 'rgba(255,71,87,0.7)');
        const borderColors = rates.map(v => v >= 0 ? '#00d68f' : '#ff4757');

        if (fundingChartInstance) fundingChartInstance.destroy();
        fundingChartInstance = new Chart(canvas, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: '资金费率 %',
                    data: rates,
                    backgroundColor: colors,
                    borderColor: borderColors,
                    borderWidth: 1,
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(20, 24, 32, 0.95)',
                        callbacks: { label: (ctx) => `费率: ${ctx.raw.toFixed(4)}%` },
                    },
                },
                scales: {
                    x: { ticks: { color: '#6b7585', font: { size: 11 } }, grid: { display: false } },
                    y: {
                        ticks: { color: '#6b7585', font: { size: 10 }, callback: v => v.toFixed(3) + '%' },
                        grid: { color: 'rgba(35,42,54,0.5)' },
                    },
                },
            },
        });
    } catch (e) {
        if (CHART_DEBUG) console.warn('资金费率图表加载失败:', e);
    }
}

// ============ 多空比走势图 ============
let lsRatioChartInstance = null;

async function initLsRatioChart() {
    const canvas = document.getElementById('lsRatioChart');
    if (!canvas) return;

    try {
        // #42 修复：复用 funding 数据，不重复请求
        const { symbols, results } = await _fetchFundingDataOnce();

        const ratios = [];
        const labels = [];
        for (let i = 0; i < symbols.length; i++) {
            if (results[i].status === 'fulfilled' && results[i].value) {
                const lsRaw = results[i].value.long_short_ratio;
                const ls = parseFloat(typeof lsRaw === 'object' ? (lsRaw?.long_short_ratio || 1) : (lsRaw || 1));
                ratios.push(ls);
                labels.push(symbols[i].replace('USDT', ''));
            }
        }

        if (ratios.length === 0) return;

        const ctx = canvas.getContext('2d');
        const gradient = ctx.createLinearGradient(0, 0, 0, 200);
        gradient.addColorStop(0, 'rgba(168, 85, 247, 0.3)');
        gradient.addColorStop(1, 'rgba(168, 85, 247, 0)');

        if (lsRatioChartInstance) lsRatioChartInstance.destroy();
        lsRatioChartInstance = new Chart(canvas, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: '多空比',
                    data: ratios,
                    backgroundColor: ratios.map(v => v >= 1 ? 'rgba(0,214,143,0.6)' : 'rgba(255,71,87,0.6)'),
                    borderColor: ratios.map(v => v >= 1 ? '#00d68f' : '#ff4757'),
                    borderWidth: 1,
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(20, 24, 32, 0.95)',
                        callbacks: { label: (ctx) => `多空比: ${ctx.raw.toFixed(3)}` },
                    },
                },
                scales: {
                    x: {
                        ticks: { color: '#6b7585', font: { size: 10 } },
                        grid: { color: 'rgba(35,42,54,0.5)' },
                    },
                    y: {
                        ticks: { color: '#6b7585', font: { size: 11 } },
                        grid: { display: false },
                    },
                },
            },
        });
    } catch (e) {
        if (CHART_DEBUG) console.warn('多空比图表加载失败:', e);
    }
}

// ============ 信号分布热力图 ============
async function initSignalHeatmap() {
    const container = document.getElementById('signalHeatmap');
    if (!container) return;

    try {
        const resp = await window.authFetch(`${API_BASE}/api/ai/history?limit=100`);
        if (!resp.ok) return;
        const data = await resp.json();
        const signals = data.history || [];

        // 构建 24h x 7day 矩阵
        const matrix = Array.from({ length: 6 }, () => Array(7).fill(0)); // 6 个时段 x 7 天
        const timeSlots = ['0-4', '4-8', '8-12', '12-16', '16-20', '20-24'];

        for (const sig of signals) {
            if (!sig.created_at) continue;
            const dt = new Date(sig.created_at);
            // #48 修复：校验 Date 有效性
            if (isNaN(dt.getTime())) continue;
            const day = (dt.getDay() + 6) % 7; // 0=周一
            const slot = Math.floor(dt.getHours() / 4);
            if (slot < 6 && day < 7) {
                matrix[slot][day] += sig.signal === 'BUY' ? 1 : sig.signal === 'SELL' ? -1 : 0;
            }
        }

        let html = '';
        for (let s = 0; s < 6; s++) {
            // 时段标签
            html += `<div class="heatmap-cell label">${timeSlots[s]}</div>`;
            for (let d = 0; d < 7; d++) {
                const val = matrix[s][d];
                const intensity = Math.min(Math.abs(val) * 30, 100);
                const bg = val > 0
                    ? `rgba(0,214,143,${intensity / 100 * 0.8 + 0.1})`
                    : val < 0
                    ? `rgba(255,71,87,${intensity / 100 * 0.8 + 0.1})`
                    : 'rgba(45,53,69,0.4)';
                const label = val !== 0 ? (val > 0 ? '+' + val : val) : '';
                html += `<div class="heatmap-cell heatmap-dyn-bg" data-bg="${bg}" title="时段${timeSlots[s]} 第${d + 1}天: ${label}">${label}</div>`;
            }
        }
        container.innerHTML = `<div class="heatmap-grid">${html}</div>`;
        container.querySelectorAll('.heatmap-dyn-bg').forEach((el) => {
            el.style.background = el.dataset.bg || 'rgba(45,53,69,0.4)';
        });
    } catch (e) {
        if (CHART_DEBUG) console.warn('信号热力图加载失败:', e);
    }
}

// ============ AI 角色雷达图 ============
let aiRadarInstance = null;

async function initAiRadarChart() {
    const canvas = document.getElementById('aiRadarChart');
    if (!canvas) return;

    try {
        const resp = await window.authFetch(`${API_BASE}/api/ai/latest-signal`);
        if (!resp.ok) return;
        const data = await resp.json();
        const signal = data.signal;
        if (!signal || !signal.role_opinions) return;

        const opinions = typeof signal.role_opinions === 'string'
            ? JSON.parse(signal.role_opinions) : signal.role_opinions;

        const labels = opinions.map(r => r.name || '分析师');
        const values = opinions.map(r => r.confidence || 0);

        if (aiRadarInstance) aiRadarInstance.destroy();
        aiRadarInstance = new Chart(canvas, {
            type: 'radar',
            data: {
                labels,
                datasets: [{
                    label: '置信度',
                    data: values,
                    borderColor: '#06b6d4',
                    backgroundColor: 'rgba(6,182,212,0.15)',
                    borderWidth: 2,
                    pointBackgroundColor: '#06b6d4',
                    pointBorderColor: '#fff',
                    pointBorderWidth: 1,
                    pointRadius: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                },
                scales: {
                    r: {
                        beginAtZero: true,
                        max: 100,
                        ticks: { stepSize: 20, color: '#6b7585', font: { size: 9 }, backdropColor: 'transparent' },
                        grid: { color: 'rgba(35,42,54,0.5)' },
                        angleLines: { color: 'rgba(35,42,54,0.5)' },
                        pointLabels: { color: '#b0b8c4', font: { size: 11 } },
                    },
                },
            },
        });
    } catch (e) {
        if (CHART_DEBUG) console.warn('AI 雷达图加载失败:', e);
    }
}

// ============ 风控指标面板 ============
async function initRiskMetrics() {
    const panel = document.getElementById('riskMetricsPanel');
    if (!panel) return;

    try {
        const resp = await window.authFetch(`${API_BASE}/api/ai/accuracy`);
        if (!resp.ok) { panel.innerHTML = '<div class="no-data">暂无数据</div>'; return; }
        const stats = await resp.json();

        const metrics = [
            { label: '总准确率', value: stats.weighted_accuracy || 0, color: 'var(--green)' },
            { label: '平均价格变化', value: stats.avg_price_change || 0, color: (stats.avg_price_change || 0) >= 0 ? 'var(--green)' : 'var(--red)', isPnl: true },
            { label: '信号总数', value: stats.total_signals || 0, color: 'var(--cyan)', isCount: true },
            { label: '正确信号', value: stats.correct_count || 0, color: 'var(--green)', isCount: true },
            { label: '错误信号', value: stats.incorrect_count || 0, color: 'var(--red)', isCount: true },
            { label: '中性信号', value: stats.neutral_count || 0, color: 'var(--text3)', isCount: true },
        ];

        let html = '';
        for (const m of metrics) {
            if (m.isCount) {
                const tone = m.color === 'var(--green)' ? 'text-up' : m.color === 'var(--red)' ? 'text-down' : m.color === 'var(--cyan)' ? 'text-cyan' : 'text-muted';
                html += `<div class="metric-bar">
                    <span class="metric-label">${m.label}</span>
                    <span class="metric-value ${tone}">${m.value}</span>
                </div>`;
            } else if (m.isPnl) {
                const tone = m.color === 'var(--green)' ? 'text-up' : 'text-down';
                html += `<div class="metric-bar">
                    <span class="metric-label">${m.label}</span>
                    <span class="metric-value ${tone}">${m.value >= 0 ? '+' : ''}${m.value.toFixed(2)}%</span>
                </div>`;
            } else {
                const pct = Math.min(Math.abs(m.value), 100);
                const tone = m.color === 'var(--green)' ? 'text-up' : m.color === 'var(--red)' ? 'text-down' : m.color === 'var(--cyan)' ? 'text-cyan' : 'text-muted';
                const fillCls = m.color === 'var(--green)' ? 'fill-up' : m.color === 'var(--red)' ? 'fill-down' : m.color === 'var(--cyan)' ? 'fill-cyan' : 'fill-muted';
                html += `<div class="metric-bar">
                    <span class="metric-label">${m.label}</span>
                    <div class="metric-track"><div class="metric-fill ${fillCls}" data-w="${pct}"></div></div>
                    <span class="metric-value ${tone}">${pct.toFixed(1)}%</span>
                </div>`;
            }
        }
        panel.innerHTML = html;
        panel.querySelectorAll('.metric-fill[data-w]').forEach((el) => {
            el.style.width = `${el.dataset.w || 0}%`;
        });
    } catch (e) {
        panel.innerHTML = '<div class="no-data">风控数据加载失败</div>';
    }
}

// 初始化所有图表
export async function initCharts() {
    const chartReady = await ensureChartReady();
    if (!chartReady) {
        const btc = document.getElementById('btcChart')?.parentElement;
        if (btc) btc.innerHTML = '<div class="no-data">图表组件加载失败</div>';
        return;
    }
    await initBtcChart();
    await loadIndicatorPanel();
    // 新增图表（不阻塞主流程）
    initFundingChart().catch(() => {});
    initLsRatioChart().catch(() => {});
}

// 风控 tab 图表初始化
export async function initRiskCharts() {
    await Promise.all([
        initSignalHeatmap(),
        initAiRadarChart(),
        initRiskMetrics(),
    ]);
}

window.GangziApp = window.GangziApp || {};
Object.assign(window.GangziApp, {
    initCharts,
    initRiskCharts,
});
