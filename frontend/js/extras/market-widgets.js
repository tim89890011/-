/**
 * 钢子出击 - 市场情绪温度计 + 巨鲸警报 + AI 方向一致性统计面板
 */
import { authFetch, escapeHtml, API_BASE } from '../auth.js';

const EXTRAS_DEBUG = false;

// ============ (a) 市场情绪温度计 ============
export async function loadSentimentPanel() {
    const panel = document.getElementById('sentimentPanel');
    if (!panel) return;

    try {
        const resp = await authFetch(`${API_BASE}/api/market/sentiment`);
        if (!resp.ok) {
            panel.innerHTML = '<div class="no-data">情绪数据获取失败</div>';
            return;
        }
        const data = await resp.json();
        const value = parseInt(data.value || 50);
        const label = data.label || 'Neutral';

        // 颜色映射
        let color, bgColor;
        if (value <= 25) { color = '#3b82f6'; bgColor = 'rgba(59,130,246,0.1)'; }
        else if (value <= 45) { color = '#06b6d4'; bgColor = 'rgba(6,182,212,0.1)'; }
        else if (value <= 55) { color = '#ffc107'; bgColor = 'rgba(255,193,7,0.1)'; }
        else if (value <= 75) { color = '#f97316'; bgColor = 'rgba(249,115,22,0.1)'; }
        else { color = '#ff4757'; bgColor = 'rgba(255,71,87,0.1)'; }

        const labelCn = {
            'Extreme Fear': '极度恐惧',
            'Fear': '恐惧',
            'Neutral': '中性',
            'Greed': '贪婪',
            'Extreme Greed': '极度贪婪',
        }[label] || label;

        panel.innerHTML = `
        <div class="sentiment-wrap">
            <div class="sentiment-value">${value}</div>
            <div class="sentiment-label">${labelCn}</div>
            <div class="sentiment-bar">
                <div class="sentiment-pointer" data-left="${value}"></div>
            </div>
            <div class="sentiment-axis">
                <span>极度恐惧</span>
                <span>中性</span>
                <span>极度贪婪</span>
            </div>
        </div>`;
        const valueEl = panel.querySelector('.sentiment-value');
        const labelEl = panel.querySelector('.sentiment-label');
        const pointerEl = panel.querySelector('.sentiment-pointer');
        if (valueEl) valueEl.style.color = color;
        if (labelEl) labelEl.style.color = color;
        if (pointerEl) pointerEl.style.left = `${value}%`;

    } catch (e) {
        panel.innerHTML = '<div class="no-data">情绪指数加载失败</div>';
        if (EXTRAS_DEBUG) console.warn('情绪指数获取失败:', e);
    }
}

// ============ (c) 巨鲸警报 ============
export async function loadWhalePanel() {
    const panel = document.getElementById('whalePanel');
    if (!panel) return;

    try {
        const resp = await authFetch(`${API_BASE}/api/market/large-trades/BTCUSDT`);
        if (!resp.ok) { panel.innerHTML = '<div class="no-data">巨鲸数据加载失败</div>'; return; }
        const data = await resp.json();
        const trades = data.trades || [];

        if (trades.length === 0) {
            panel.innerHTML = '<div class="no-data">暂无大额交易数据</div>';
            return;
        }

        panel.innerHTML = `
        <div class="whale-title">BTC 最近大额交易（按成交额排序）</div>
        ${trades.slice(0, 8).map(t => {
            const isBuy = !t.is_buyer_maker;
            const amountCls = isBuy ? 'text-up' : 'text-down';
            const icon = isBuy ? '🟢' : '🔴';
            const amount = (t.quote_qty / 1000).toFixed(1);
            const time = new Date(t.time).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

            return `<div class="whale-row">
                <span>${icon} ${isBuy ? '买入' : '卖出'}</span>
                <span class="${amountCls} whale-amount">$${escapeHtml(amount)}K</span>
                <span class="text-muted">@ $${escapeHtml(String(Number(t.price) || 0))}</span>
                <span class="whale-time">${escapeHtml(time)}</span>
            </div>`;
        }).join('')}`;

    } catch (e) {
        panel.innerHTML = '<div class="no-data">巨鲸数据加载失败</div>';
    }
}

// ============ (d) AI 方向一致性统计面板（Pro 重设计） ============
let _accCurrentDays = 0; // 当前筛选天数
let _accDailyChart = null;
let _accFilterBound = false;
let _accReqSeq = 0;

export async function loadAccuracyPanel(days) {
    if (typeof days === 'number') _accCurrentDays = days;
    const panel = document.getElementById('accuracyPanel');
    if (!panel) return;

    try {
        const reqId = ++_accReqSeq;
        const url = _accCurrentDays > 0
            ? `${API_BASE}/api/ai/accuracy?days=${_accCurrentDays}`
            : `${API_BASE}/api/ai/accuracy`;
        const resp = await authFetch(url);
        if (!resp.ok) { panel.innerHTML = '<div class="no-data">统计数据加载失败</div>'; return; }
        const stats = await resp.json();
        // 防竞态：只渲染最后一次请求的结果
        if (reqId !== _accReqSeq) return;

        if (stats.total_signals === 0) {
            // 今日可能没有任何已验证信号：仍渲染趋势区块，避免 UI 直接消失/提示不更新
            panel.innerHTML = `
                <div class="acc-banner">
                    <i class="ri-error-warning-line"></i>
                    <span>此统计仅为价格方向预测一致性参考，不构成投资效果保证</span>
                </div>
                <div class="no-data" style="margin:10px 0;">暂无足够数据统计方向一致性（需等待信号验证）</div>
                <div class="acc-section">
                    <div class="acc-section-title">按天准确率变化</div>
                    <div class="chart-h chart-h-200">
                        <canvas id="accDailyTrendChart"></canvas>
                    </div>
                    <div class="acc-meta" id="accDailyTrendHint">--</div>
                </div>
            `;
            try { renderAccDailyTrend(stats); } catch (_) {}
            return;
        }

        const acc = stats.weighted_accuracy || 0;
        const ringAngle = Math.min(acc, 100) / 100 * 360;
        const ringColor = acc >= 60 ? 'var(--green)' : acc >= 40 ? 'var(--blue)' : 'var(--red)';
        const accCls = acc >= 60 ? 'text-up' : acc >= 40 ? 'text-mid' : 'text-down';

        // 币种卡片
        let coinsHtml = '';
        if (stats.by_symbol && Object.keys(stats.by_symbol).length > 0) {
            const coins = Object.entries(stats.by_symbol).map(([symbol, data]) => {
                const pct = data.accuracy || 0;
                const accent = pct >= 55 ? 'var(--green)' : pct >= 45 ? 'var(--blue)' : 'var(--red)';
                return `<div class="acc-coin" style="--coin-accent:${accent}">
                    <div class="acc-coin-name">${escapeHtml(symbol.replace('USDT', ''))}</div>
                    <div class="acc-coin-pct">${pct}%</div>
                    <div class="acc-coin-frac">(${data.correct}/${data.total})</div>
                </div>`;
            }).join('');
            coinsHtml = `<div class="acc-section">
                <div class="acc-section-title">各币种方向一致性</div>
                <div class="acc-coins">${coins}</div>
            </div>`;
        }

        // 信号类型进度条
        let typesHtml = '';
        if (stats.by_signal_type) {
            const typeConfig = {
                'BUY':  { label: '买入', color: 'var(--green)', cls: 'text-up' },
                'SELL': { label: '卖出', color: 'var(--red)',   cls: 'text-down' },
                'HOLD': { label: '观望', color: 'var(--text3)', cls: 'text-muted' },
            };
            const types = Object.entries(stats.by_signal_type)
                .filter(([_, d]) => d.total > 0)
                .map(([type, data]) => {
                    const cfg = typeConfig[type] || { label: type, color: 'var(--text3)', cls: '' };
                    const pct = data.accuracy || 0;
                    return `<div class="acc-type">
                        <div class="acc-type-left">
                            <span class="acc-type-dot" style="background:${cfg.color}"></span>
                            <span class="acc-type-name">${cfg.label}</span>
                        </div>
                        <div class="acc-type-bar-track">
                            <div class="acc-type-bar-fill" style="width:${pct}%;background:${cfg.color}"></div>
                        </div>
                        <div class="acc-type-right">
                            <span class="acc-type-pct ${cfg.cls}">${pct}%</span>
                            <span class="acc-type-count">${data.total}次</span>
                        </div>
                    </div>`;
                }).join('');
            typesHtml = `<div class="acc-section">
                <div class="acc-section-title">各信号类型表现</div>
                <div class="acc-types">${types}</div>
            </div>`;
        }

        // 方法说明
        const methodology = stats.methodology || {};
        const thresholds = methodology.thresholds || {};
        const timeDecay = methodology.time_decay || {};
        const weights = timeDecay.weights || [];
        const disclaimer = stats.disclaimer || {};

        const thresholdTags = Object.entries(thresholds.values || {}).map(([sym, val]) =>
            `<span class="acc-method-tag">${escapeHtml(sym.replace('USDT', ''))}: ${escapeHtml(val)}</span>`
        ).join('') + `<span class="acc-method-tag default">默认: ${escapeHtml(thresholds.default || '2.0%')}</span>`;

        const weightItems = weights.map(w =>
            `<div class="acc-method-weight">
                <span class="acc-method-weight-period">${escapeHtml(w.period)}</span>
                <span class="acc-method-weight-val">${escapeHtml(w.weight)}</span>
            </div>`
        ).join('');

        panel.innerHTML = `
            <div class="acc-banner">
                <i class="ri-error-warning-line"></i>
                <span>此统计仅为价格方向预测一致性参考，不构成投资效果保证</span>
            </div>

            <div class="acc-hero">
                <div class="acc-hero-side">
                    <div class="acc-hero-num text-up">${stats.correct_count}</div>
                    <div class="acc-hero-label">预测正确</div>
                    <div class="acc-hero-sub">次</div>
                </div>
                <div class="acc-ring" style="--ring-color:${ringColor};--ring-angle:${ringAngle}deg">
                    <div class="acc-ring-inner">
                        <div class="acc-ring-val ${accCls}">${acc}%</div>
                        <div class="acc-ring-sub">方向一致性</div>
                    </div>
                </div>
                <div class="acc-hero-side">
                    <div class="acc-hero-num text-down">${stats.incorrect_count}</div>
                    <div class="acc-hero-label">预测错误</div>
                    <div class="acc-hero-sub">次</div>
                </div>
            </div>

            <div class="acc-meta">
                总信号 <b>${stats.total_signals}</b> · 中性 <b>${stats.neutral_count}</b> · 平均价格变化 <b>${stats.avg_price_change > 0 ? '+' : ''}${stats.avg_price_change}%</b>
            </div>

            <div class="acc-section">
                <div class="acc-section-title">按天准确率变化</div>
                <div class="chart-h chart-h-200">
                    <canvas id="accDailyTrendChart"></canvas>
                </div>
                <div class="acc-meta" id="accDailyTrendHint">--</div>
            </div>

            ${coinsHtml}
            ${typesHtml}

            <details class="acc-method">
                <summary>
                    <span class="acc-method-icon"><i class="ri-bar-chart-2-line"></i></span>
                    统计方法说明
                    <span class="acc-method-arrow">▼</span>
                </summary>
                <div class="acc-method-body">
                    <h4>${escapeHtml(methodology.title || '统计方法说明')}</h4>
                    <p>${escapeHtml(methodology.description || '')}</p>

                    <h5>判断规则</h5>
                    <ul>${(methodology.rules || []).map(rule => `<li>${escapeHtml(rule)}</li>`).join('')}</ul>

                    <h5>${escapeHtml(thresholds.description || 'HOLD 信号阈值')}</h5>
                    <div class="acc-method-thresholds">${thresholdTags}</div>

                    <h5>${escapeHtml(timeDecay.description || '时间衰减权重')}</h5>
                    <div class="acc-method-weights">${weightItems}</div>

                    <div class="acc-method-disclaimer">
                        <h4>${escapeHtml(disclaimer.title || '重要免责声明')}</h4>
                        <p>${escapeHtml(disclaimer.content || '')}</p>
                        <p><strong>${escapeHtml(disclaimer.risk_warning || '')}</strong></p>
                    </div>
                </div>
            </details>`;

        // 趋势图（可选）：无数据也会更新 hint，避免保留旧状态
        try { renderAccDailyTrend(stats); } catch (e) {
            if (EXTRAS_DEBUG) console.warn('[准确率] 趋势图渲染失败:', e);
        }

    } catch (e) {
        panel.innerHTML = '<div class="no-data">方向一致性统计加载失败</div>';
        if (EXTRAS_DEBUG) console.error('准确率面板加载失败:', e);
    }
}

function renderAccDailyTrend(stats) {
    const canvas = document.getElementById('accDailyTrendChart');
    const hint = document.getElementById('accDailyTrendHint');
    if (!canvas) return;

    const series = Array.isArray(stats.by_day) ? stats.by_day : [];
    if (typeof Chart === 'undefined') {
        if (hint) hint.textContent = 'Chart.js 未加载，无法绘制趋势图';
        return;
    }

    const w = stats.trend_window_days || (_accCurrentDays || 0);
    const rangeText = _accCurrentDays === 0 ? `最近${w}天` : `${_accCurrentDays}天`;

    if (!series.length) {
        if (hint) hint.textContent = `区间: ${rangeText} · 暂无按天趋势数据`;
        if (_accDailyChart) {
            _accDailyChart.destroy();
            _accDailyChart = null;
        }
        return;
    }

    const labels = series.map((d) => String(d.date || '--').slice(5));
    const values = series.map((d) => Number(d.accuracy || 0));
    const latest = series[series.length - 1] || {};
    if (hint) {
        hint.textContent = `区间: ${rangeText} · 最新 ${Number(latest.accuracy || 0).toFixed(1)}%（${latest.correct || 0}对/${latest.incorrect || 0}错）`;
    }

    if (_accDailyChart) _accDailyChart.destroy();
    _accDailyChart = new Chart(canvas, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: '方向准确率(%)',
                data: values,
                borderColor: '#22c55e',
                backgroundColor: 'rgba(34, 197, 94, 0.12)',
                fill: true,
                tension: 0.32,
                pointRadius: 2,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, max: 100 },
                x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } },
            },
        },
    });
}

// ============ 准确率筛选按钮绑定 ============
export function initAccFilterButtons() {
    // 事件委托：避免 initExtras 执行时 DOM 还未就绪导致绑定失败
    if (_accFilterBound) return;
    _accFilterBound = true;
    document.addEventListener('click', async (e) => {
        const btn = e.target.closest('#accFilterGroup .acc-filter-btn');
        if (!btn) return;
        const group = document.getElementById('accFilterGroup');
        if (!group) return;
        const days = parseInt(btn.dataset.days, 10) || 0;
        // debug marker for automation / quick inspection
        window.__acc_last_days = days;
        window.__acc_last_ts = Date.now();
        group.querySelectorAll('.acc-filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        // 直接走对外导出的入口（和手动调用一致），并 await 避免竞态覆盖
        const fn = (window.GangziApp && window.GangziApp.loadAccuracyPanel) ? window.GangziApp.loadAccuracyPanel : loadAccuracyPanel;
        await fn(days);
    });
}
