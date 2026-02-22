/**
 * 钢子出击 - 信号历史列表 + API 配额面板 + 成本监控详细面板
 */
import { authFetch, escapeHtml, API_BASE } from '../auth.js';

const EXTRAS_DEBUG = false;

// ============ 信号历史完整列表 ============
export async function loadSignalHistory() {
    const container = document.getElementById('signalHistory');
    if (!container) return;

    try {
        const resp = await authFetch(`${API_BASE}/api/ai/history?limit=50`);
        if (!resp.ok) return;
        const data = await resp.json();

        if (!data.history || data.history.length === 0) {
            container.innerHTML = '<div class="no-data">暂无信号记录</div>';
            return;
        }

        container.innerHTML = data.history.map(s => {
            const sigCn = { BUY: '买入', SELL: '卖出', HOLD: '观望' }[s.signal] || '观望';
            const time = s.created_at ? new Date(s.created_at).toLocaleString('zh-CN') : '--';

            const dotCls = s.signal === 'BUY' ? 'dot-buy' : s.signal === 'SELL' ? 'dot-sell' : 'dot-hold';
            return `<div class="signal-item">
                <div class="signal-dot ${dotCls}"></div>
                <span class="signal-time signal-time-wide">${escapeHtml(time)}</span>
                <span class="signal-msg"><strong>${escapeHtml(s.symbol)}</strong> ${escapeHtml(sigCn)} · 置信度 ${Number(s.confidence) || 0}% · $${Number(s.price_at_signal) || 0} · 风险${escapeHtml(s.risk_level || '中')}</span>
            </div>`;
        }).join('');

    } catch (e) {
        container.innerHTML = '<div class="no-data">信号历史加载失败</div>';
    }
}

// ============ (e) API 配额与成本监控面板 ============
export async function loadQuotaPanel() {
    const panel = document.getElementById('quotaPanel');
    if (!panel) return;

    try {
        const callsResp = await authFetch(`${API_BASE}/api/metrics/api-calls?hours=24`);
        const costResp = await authFetch(`${API_BASE}/api/metrics/cost`);
        if (!callsResp.ok || !costResp.ok) {
            panel.innerHTML = '<div class="no-data">配额数据加载失败</div>';
            return;
        }
        const callsData = await callsResp.json();
        const costData = await costResp.json();

        const quota = (callsData.quota_history && callsData.quota_history[0]) || {};
        const strategy = { actions: [] };
        const projected = costData.projected || {};
        const costEstimate = {
            current_cost: Number(costData.today?.estimated_cost_cny || 0),
            projected_daily_cost: Number(projected.daily_cost || 0),
            monthly_estimate: Number(projected.monthly_estimate || 0),
            cost_per_call: Number(costData.today?.estimated_cost_cny || 0) / Math.max(Number(costData.today?.api_calls || 0), 1),
        };

        // 根据状态确定颜色
        const statusColors = {
            normal: { color: '#00ff88', bg: 'rgba(0,255,136,0.1)' },
            warning: { color: '#ffc107', bg: 'rgba(255,193,7,0.1)' },
            critical: { color: '#ff6b6b', bg: 'rgba(255,107,107,0.1)' },
            exceeded: { color: '#ff4757', bg: 'rgba(255,71,87,0.1)' },
        };
        const statusConfig = statusColors[quota.status] || statusColors.normal;

        const statusLabels = {
            normal: '正常',
            warning: '警告',
            critical: '危险',
            exceeded: '已超限',
        };

        // 进度条宽度
        const progressWidth = Math.min(quota.usage_percent || 0, 100);

        panel.innerHTML = `
        <div class="quota-summary">
            <div class="quota-main-stat">
                <div class="quota-ring" style="--progress: ${progressWidth}; --color: ${statusConfig.color}">
                    <div class="quota-ring-inner">
                        <span class="quota-percent">${quota.usage_percent?.toFixed(1) || 0}%</span>
                        <span class="quota-status">${statusLabels[quota.status]}</span>
                    </div>
                </div>
                <div class="quota-text-stats">
                    <div class="quota-stat-row">
                        <span class="stat-label">今日调用</span>
                        <span class="stat-value">${quota.total_calls || 0} / ${quota.quota_limit || 0}</span>
                    </div>
                    <div class="quota-stat-row">
                        <span class="stat-label">剩余配额</span>
                        <span class="stat-value ${quota.remaining < 1000 ? 'text-down' : ''}">${quota.remaining || 0}</span>
                    </div>
                    <div class="quota-stat-row">
                        <span class="stat-label">预估成本</span>
                        <span class="stat-value">\u00A5${costEstimate.current_cost?.toFixed(4) || '0.0000'}</span>
                    </div>
                </div>
            </div>

            <div class="quota-progress-bar">
                <div class="progress-track">
                    <div class="progress-fill" style="width: ${progressWidth}%; background: ${statusConfig.color}"></div>
                </div>
                <div class="progress-marks">
                    <span class="mark-warning" style="left: 80%" title="警告阈值"><i class="ri-error-warning-line"></i></span>
                    <span class="mark-critical" style="left: 90%" title="危险阈值"><i class="ri-alarm-warning-line"></i></span>
                </div>
            </div>

            ${strategy.actions && strategy.actions.length > 0 ? `
            <div class="quota-strategy">
                <div class="strategy-title">
                    <span class="strategy-icon"><i class="ri-file-list-3-line"></i></span>
                    当前策略
                </div>
                <ul class="strategy-list">
                    ${strategy.actions.map(action => `<li>${escapeHtml(action)}</li>`).join('')}
                </ul>
            </div>
            ` : ''}

            <div class="quota-breakdown">
                <div class="breakdown-title">调用类型分布</div>
                <div class="breakdown-grid">
                    <div class="breakdown-item">
                        <span class="breakdown-label">分析调用</span>
                        <span class="breakdown-value">${quota.analysis_calls || 0}</span>
                    </div>
                    <div class="breakdown-item">
                        <span class="breakdown-label">聊天调用</span>
                        <span class="breakdown-value">${quota.chat_calls || 0}</span>
                    </div>
                    <div class="breakdown-item">
                        <span class="breakdown-label">R1裁决</span>
                        <span class="breakdown-value">${quota.reasoner_calls || 0}</span>
                    </div>
                </div>
            </div>

            <div class="quota-cost-projection">
                <div class="projection-title"><i class="ri-money-dollar-circle-line"></i> 成本预估</div>
                <div class="projection-grid">
                    <div class="projection-item">
                        <span class="projection-label">今日预计</span>
                        <span class="projection-value">\u00A5${costEstimate.projected_daily_cost?.toFixed(2) || '0.00'}</span>
                    </div>
                    <div class="projection-item">
                        <span class="projection-label">月度预估</span>
                        <span class="projection-value">\u00A5${costEstimate.monthly_estimate?.toFixed(2) || '0.00'}</span>
                    </div>
                    <div class="projection-item">
                        <span class="projection-label">单次成本</span>
                        <span class="projection-value">\u00A5${costEstimate.cost_per_call?.toFixed(6) || '0.000000'}</span>
                    </div>
                </div>
            </div>
        </div>`;

    } catch (e) {
        panel.innerHTML = '<div class="no-data">配额数据加载失败</div>';
        if (EXTRAS_DEBUG) console.error('配额面板加载失败:', e);
    }
}

// ============ (f) 成本监控详细面板 ============
export async function loadCostPanel() {
    const panel = document.getElementById('costPanel');
    if (!panel) return;

    try {
        const costResp = await authFetch(`${API_BASE}/api/metrics/cost`);
        const callsResp = await authFetch(`${API_BASE}/api/metrics/api-calls?hours=24`);
        if (!costResp.ok || !callsResp.ok) {
            panel.innerHTML = '<div class="no-data">成本数据加载失败</div>';
            return;
        }
        const costData = await costResp.json();
        const callsData = await callsResp.json();
        const currentStats = callsData.current_stats || {};
        const byModelMetrics = currentStats.by_model || {};
        const recent5m = currentStats.recent_5min || {};

        const avgDurations = Object.values(byModelMetrics)
            .map((item) => Number(item.avg_duration_ms || 0))
            .filter((v) => v > 0);
        const avgDurationMs = avgDurations.length > 0
            ? avgDurations.reduce((sum, v) => sum + v, 0) / avgDurations.length
            : 0;

        const today = {
            total_calls: Number(costData.today?.api_calls || 0),
            success_rate: Number(recent5m.success_rate || 0),
            avg_response_time: (avgDurationMs / 1000).toFixed(2),
            total_cost: Number(costData.today?.estimated_cost_cny || 0),
            by_model: costData.today?.by_model || {},
        };

        const errors = {
            total_calls: Number(recent5m.calls || 0),
            failed_calls: Number(recent5m.errors || 0),
            error_rate: Number(recent5m.calls || 0) > 0
                ? Number(((Number(recent5m.errors || 0) / Number(recent5m.calls || 0)) * 100).toFixed(2))
                : 0,
            error_types: {},
        };
        const responseTime = {
            p50: Number((avgDurationMs / 1000).toFixed(2)),
            p90: Number((avgDurationMs / 1000).toFixed(2)),
            p99: Number((avgDurationMs / 1000).toFixed(2)),
            avg: Number((avgDurationMs / 1000).toFixed(2)),
        };

        // 构建模型统计
        let modelStatsHtml = '';
        if (today.by_model) {
            modelStatsHtml = Object.entries(today.by_model).map(([model, stats]) => `
                <div class="model-stat-item">
                    <span class="model-name">${escapeHtml(model)}</span>
                    <span class="model-calls">${stats.total_calls || 0}次</span>
                    <span class="model-cost">\u00A5${Number(stats.estimated_cost_cny || 0).toFixed(4)}</span>
                    <span class="model-tokens">${Number(stats.tokens_in || 0) + Number(stats.tokens_out || 0)}t</span>
                </div>
            `).join('');
        }

        panel.innerHTML = `
        <div class="cost-dashboard">
            <div class="cost-stats-grid">
                <div class="cost-stat-card">
                    <div class="stat-icon"><i class="ri-phone-line"></i></div>
                    <div class="stat-content">
                        <span class="stat-value">${today.total_calls || 0}</span>
                        <span class="stat-label">总调用次数</span>
                    </div>
                </div>
                <div class="cost-stat-card ${today.success_rate >= 95 ? 'good' : today.success_rate >= 80 ? 'warning' : 'bad'}">
                    <div class="stat-icon"><i class="ri-checkbox-circle-line"></i></div>
                    <div class="stat-content">
                        <span class="stat-value">${today.success_rate || 0}%</span>
                        <span class="stat-label">成功率</span>
                    </div>
                </div>
                <div class="cost-stat-card">
                    <div class="stat-icon"><i class="ri-timer-line"></i></div>
                    <div class="stat-content">
                        <span class="stat-value">${today.avg_response_time || 0}s</span>
                        <span class="stat-label">平均响应</span>
                    </div>
                </div>
                <div class="cost-stat-card">
                    <div class="stat-icon"><i class="ri-money-dollar-circle-line"></i></div>
                    <div class="stat-content">
                        <span class="stat-value">\u00A5${today.total_cost?.toFixed(2) || '0.00'}</span>
                        <span class="stat-label">今日成本</span>
                    </div>
                </div>
            </div>

            <div class="cost-details">
                <div class="details-section">
                    <div class="section-title">模型统计</div>
                    <div class="model-stats-list">
                        ${modelStatsHtml || '<div class="no-data">暂无数据</div>'}
                    </div>
                </div>

                <div class="details-section">
                    <div class="section-title">响应时间分布</div>
                    <div class="response-time-stats">
                        <div class="rt-stat">
                            <span class="rt-label">P50</span>
                            <span class="rt-value">${responseTime.p50 || 0}s</span>
                        </div>
                        <div class="rt-stat">
                            <span class="rt-label">P90</span>
                            <span class="rt-value">${responseTime.p90 || 0}s</span>
                        </div>
                        <div class="rt-stat">
                            <span class="rt-label">P99</span>
                            <span class="rt-value">${responseTime.p99 || 0}s</span>
                        </div>
                        <div class="rt-stat">
                            <span class="rt-label">平均</span>
                            <span class="rt-value">${responseTime.avg || 0}s</span>
                        </div>
                    </div>
                </div>

                <div class="details-section">
                    <div class="section-title">错误统计</div>
                    <div class="error-stats">
                        <div class="error-main">
                            <span class="error-rate ${errors.error_rate > 5 ? 'high' : errors.error_rate > 1 ? 'medium' : 'low'}">
                                错误率: ${errors.error_rate || 0}%
                            </span>
                            <span class="error-count">失败: ${errors.failed_calls || 0} / ${errors.total_calls || 0}</span>
                        </div>
                        ${errors.error_types && Object.keys(errors.error_types).length > 0 ? `
                        <div class="error-types">
                            ${Object.entries(errors.error_types).map(([type, count]) => `
                                <span class="error-type-tag ${type}">${escapeHtml(type)}: ${count}</span>
                            `).join('')}
                        </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        </div>`;

    } catch (e) {
        panel.innerHTML = '<div class="no-data">成本数据加载失败</div>';
        if (EXTRAS_DEBUG) console.error('成本面板加载失败:', e);
    }
}
