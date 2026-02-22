/**
 * 钢子出击 - AI 信号英雄卡片
 * 在总览面板顶部显示最新 AI 信号
 */

// 全局依赖（由 auth.js IIFE 暴露到 window）
// authFetch, API_BASE, escapeHtml, drawGauge

let currentSignal = null;
const SIGNAL_DEBUG = false;

// #HIGH-6 修复：请求竞态条件防护
let latestSignalRequestId = 0;

// 初始化状态管理
let initState = {
    isInitializing: false,
    progress: 0,
    pollInterval: null,
    progressInterval: null,
    startTime: null,
    estimatedDuration: 45000, // 预计45秒
};

/**
 * 加载最新信号
 * 优化：首次启动显示精美的骨架屏和进度动画
 */
export async function loadLatestSignal() {
    const requestId = ++latestSignalRequestId;
    const container = document.getElementById('aiSignalHero');
    if (!container) return;

    try {
        const resp = await authFetch(`${API_BASE}/api/ai/latest-signal?symbol=BTCUSDT`);
        if (!resp.ok) return;

        // 检查是否是最新请求
        if (requestId !== latestSignalRequestId) return;

        const data = await resp.json();

        // 清除轮询定时器（如果存在）
        clearInitPolling();

        if (!data.signal) {
            // 检查是否正在初始化
            const isInitializing = data.is_initializing || false;

            if (isInitializing && !currentSignal) {
                // 系统正在初始化，显示初始化状态
                initState.isInitializing = true;
                renderInitState(container);
                startInitPolling(container);
            } else {
                // 正常空状态（已有信号后清空）
                renderEmptyState(container);
            }
            return;
        }

        // 有信号，重置初始化状态
        initState.isInitializing = false;
        initState.progress = 100;

        // 检查是否是最新请求
        if (requestId !== latestSignalRequestId) return;

        currentSignal = data.signal;
        renderSignalHero(container, data.signal);

        // 更新每日一句
        if (data.signal.daily_quote) {
            const quoteEl = document.getElementById('dailyQuote');
            const textEl = document.getElementById('quoteText');
            if (quoteEl && textEl) {
                textEl.textContent = `「${data.signal.daily_quote}」`;
                quoteEl.classList.remove('hidden');
            }
        }

    } catch (e) {
        if (SIGNAL_DEBUG) console.warn('加载信号失败:', e);
        // 出错时显示空状态
        const container = document.getElementById('aiSignalHero');
        if (container) renderEmptyState(container);
    }
}

/**
 * 渲染初始化状态（骨架屏 + 进度动画）
 */
function renderInitState(container) {
    initState.startTime = Date.now();

    container.innerHTML = `
    <div class="ai-hero signal-hold init-state">
        <div class="init-animation">
            <div class="ai-thinking">
                <span class="thinking-icon">🤔</span>
                <span class="thinking-text">AI 正在初始化分析...</span>
            </div>

            <!-- 骨架屏卡片 -->
            <div class="skeleton-card">
                <div class="skeleton skeleton-badge"></div>
                <div class="skeleton skeleton-info"></div>
            </div>

            <!-- 进度条 -->
            <div class="progress-bar-container">
                <div class="progress-bar">
                    <div class="progress-fill" id="initProgressBar" style="width: 0%"></div>
                </div>
                <div class="progress-stats">
                    <span class="progress-percent" id="initProgressText">0%</span>
                    <span class="progress-time" id="initTimeText">预计剩余 45 秒</span>
                </div>
            </div>

            <!-- 提示信息 -->
            <div class="init-hints">
                <div class="init-hint">
                    <span class="hint-icon"><i class="ri-timer-line"></i></span>
                    <span>首次分析预计需要 30-60 秒</span>
                </div>
                <div class="init-hint">
                    <span class="hint-icon"><i class="ri-refresh-line"></i></span>
                    <span>正在收集市场数据...</span>
                </div>
            </div>

            <!-- 立即分析按钮 -->
            <button class="init-btn" id="startAnalysisBtn" onclick="startAnalysisNow()">
                <span class="btn-icon"><i class="ri-flashlight-line"></i></span>
                <span>立即分析</span>
            </button>

            <!-- 自动刷新提示 -->
            <div class="auto-refresh-hint">
                <span class="refresh-dot"></span>
                <span>自动检测中...</span>
            </div>
        </div>
    </div>`;

    // 启动进度条动画
    startProgressAnimation();
}

/**
 * 渲染空状态（无信号且无初始化）
 */
function renderEmptyState(container) {
    container.innerHTML = `
    <div class="ai-hero signal-hold">
        <div class="ai-hero-top">
            <div class="ai-hero-signal">
                <span class="signal-badge hold">等待</span>
                <div class="signal-info">
                    <div class="signal-symbol">AI 分析系统</div>
                    <div class="signal-time">暂无信号 - 等待首次分析...</div>
                </div>
            </div>
        </div>
        <div class="empty-state-actions" style="margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border);">
            <button class="init-btn" onclick="startAnalysisNow()">
                <span class="btn-icon"><i class="ri-flashlight-line"></i></span>
                <span>立即分析</span>
            </button>
        </div>
    </div>`;
}

/**
 * 启动进度条动画
 */
function startProgressAnimation() {
    // 清除旧的进度定时器
    if (initState.progressInterval) {
        clearInterval(initState.progressInterval);
    }

    const progressBar = document.getElementById('initProgressBar');
    const progressText = document.getElementById('initProgressText');
    const timeText = document.getElementById('initTimeText');

    if (!progressBar || !progressText || !timeText) return;

    initState.progressInterval = setInterval(() => {
        const elapsed = Date.now() - (initState.startTime || Date.now());
        const estimated = initState.estimatedDuration;

        // 计算进度（非线性增长，先快后慢）
        let progress = Math.min(95, (elapsed / estimated) * 100);
        // 应用缓动函数使进度更自然
        progress = easeOutCubic(progress / 100) * 100;

        initState.progress = progress;

        // 更新UI
        progressBar.style.width = `${progress}%`;
        progressText.textContent = `${Math.round(progress)}%`;

        const remaining = Math.max(0, Math.ceil((estimated - elapsed) / 1000));
        if (remaining > 0) {
            timeText.textContent = `预计剩余 ${remaining} 秒`;
        } else {
            timeText.textContent = '即将完成...';
        }

        // 更新提示文字（根据进度阶段）
        updateHintByProgress(progress);

    }, 500);
}

/**
 * 根据进度更新提示
 */
function updateHintByProgress(progress) {
    const hints = document.querySelectorAll('.init-hint span:last-child');
    if (hints.length < 2) return;

    if (progress < 30) {
        hints[1].textContent = '正在收集市场数据...';
    } else if (progress < 60) {
        hints[1].textContent = 'AI 角色正在进行市场分析...';
    } else if (progress < 90) {
        hints[1].textContent = '综合研判中，生成交易信号...';
    } else {
        hints[1].textContent = '即将完成，请稍候...';
    }
}

/**
 * 缓动函数：easeOutCubic
 */
function easeOutCubic(x) {
    return 1 - Math.pow(1 - x, 3);
}

/**
 * 启动初始化轮询（每5秒检查一次）
 */
function startInitPolling(container) {
    // 清除旧定时器
    clearInitPolling();

    // 每5秒轮询一次
    initState.pollInterval = setInterval(async () => {
        try {
            const resp = await authFetch(`${API_BASE}/api/ai/latest-signal?symbol=BTCUSDT`);
            if (!resp.ok) return;
            const data = await resp.json();

            if (data.signal) {
                // 有新信号了！清除轮询并渲染
                clearInitPolling();
                initState.isInitializing = false;
                currentSignal = data.signal;
                renderSignalHero(container, data.signal);
            }
        } catch (e) {
            if (SIGNAL_DEBUG) console.warn('轮询检查失败:', e);
        }
    }, 5000);
}

/**
 * 清除初始化轮询和进度动画
 */
function clearInitPolling() {
    if (initState.pollInterval) {
        clearInterval(initState.pollInterval);
        initState.pollInterval = null;
    }
    if (initState.progressInterval) {
        clearInterval(initState.progressInterval);
        initState.progressInterval = null;
    }
}

// 注意：用户要求"只保留成交提示音"，因此本模块不提供任何发声能力。

/**
 * 立即开始分析（全局函数供按钮调用）
 */
async function startAnalysisNow() {
    const btn = document.getElementById('startAnalysisBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="btn-icon spinning">⏳</span><span>分析中...</span>';
    }

    try {
        const resp = await authFetch(`${API_BASE}/api/ai/analyze-now`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol: 'BTCUSDT' })
        });

        if (resp.ok) {
            const data = await resp.json();
            if (data.data?.signal) {
                // 分析完成，立即显示
                clearInitPolling();
                const container = document.getElementById('aiSignalHero');
                if (container) {
                    currentSignal = data.data.signal;
                    renderSignalHero(container, data.data.signal);
                }
                showToast('分析完成！', 'success');
            }
        } else if (resp.status === 429) {
            const error = await resp.json();
            const detail = error.detail || {};
            const remaining = Number(detail.remaining_seconds || 0);
            const message = typeof detail === 'string'
                ? detail
                : (detail.message || '冷却中，请稍后再试');
            showToast(message, 'warning');

            if (remaining > 0 && btn) {
                let countdown = remaining;
                btn.disabled = true;
                btn.innerHTML = `<span class="btn-icon"><i class="ri-timer-line"></i></span><span>${countdown}s 后可重试</span>`;
                const timer = setInterval(() => {
                    countdown -= 1;
                    if (countdown <= 0) {
                        clearInterval(timer);
                        btn.disabled = false;
                        btn.innerHTML = '<span class="btn-icon"><i class="ri-flashlight-line"></i></span><span>立即分析</span>';
                        return;
                    }
                    btn.innerHTML = `<span class="btn-icon"><i class="ri-timer-line"></i></span><span>${countdown}s 后可重试</span>`;
                }, 1000);
                return;
            }

            // 恢复按钮状态
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<span class="btn-icon"><i class="ri-flashlight-line"></i></span><span>立即分析</span>';
            }
        } else {
            throw new Error('分析请求失败');
        }
    } catch (e) {
        console.warn('立即分析失败:', e);
        showToast('分析失败，请稍后重试', 'error');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<span class="btn-icon"><i class="ri-flashlight-line"></i></span><span>立即分析</span>';
        }
    }
}
// HTML onclick 需要全局访问
window.startAnalysisNow = startAnalysisNow;

/**
 * 显示提示消息
 */
function showToast(message, type = 'info') {
    // 如果页面已有 toast 系统，使用它
    if (window.GangziApp?.showToast) {
        window.GangziApp.showToast(message, type);
        return;
    }

    // 否则创建简单的 toast
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 8px;
        background: ${type === 'success' ? 'var(--green)' : type === 'error' ? 'var(--red)' : 'var(--blue)'};
        color: white;
        font-size: 14px;
        z-index: 9999;
        animation: slideInRight 0.3s ease;
    `;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// #51 修复：使用全局 escapeHtml（定义在 auth.js）
const escapeSignalHtml = escapeHtml;

function renderSignalHero(container, signal) {
    const sig = signal.signal || 'HOLD';
    const sigLower = sig.toLowerCase();
    const sigCn = { BUY: '买入', SELL: '卖出', HOLD: '观望' }[sig] || '观望';
    const confidence = signal.confidence || 0;
    const symbol = signal.symbol || 'BTCUSDT';
    const timeStr = signal.created_at ? new Date(signal.created_at).toLocaleString('zh-CN') : '--';

    // #3 修复：统一 role_opinions 类型判断（可能是 string 或 array）
    let opinions = signal.role_opinions || [];
    if (typeof opinions === 'string') { try { opinions = JSON.parse(opinions); } catch(_) { opinions = []; } }
    if (!Array.isArray(opinions)) opinions = [];
    const buyCount = opinions.filter(o => o.signal === 'BUY').length;
    const sellCount = opinions.filter(o => o.signal === 'SELL').length;
    const holdCount = opinions.length - buyCount - sellCount;

    // 风险评估文本
    const riskAssessment = signal.risk_assessment || '暂无风险评估数据';

    container.innerHTML = `
    <div class="ai-hero signal-${sigLower} pulse-glow">
        <div class="ai-hero-top">
            <div class="ai-hero-signal">
                <span class="signal-badge ${sigLower}">${sigCn}</span>
                <div class="signal-info">
                    <div class="signal-symbol">${symbol} · AI 综合研判</div>
                    <div class="signal-time">${timeStr}</div>
                </div>
            </div>
            <div class="ai-hero-gauge">
                <canvas id="heroGauge" width="160" height="90"></canvas>
            </div>
        </div>

        <div class="vote-bar">
            <div class="buy-segment" data-flex="${buyCount}"></div>
            <div class="sell-segment" data-flex="${sellCount || 0.01}"></div>
            <div class="hold-segment" data-flex="${holdCount || 0.01}"></div>
        </div>
        <div class="vote-label">
            <span class="vote-buy">买入 ${buyCount}</span>
            <span>投票结果 ${buyCount}买 ${sellCount}卖 ${holdCount}观望</span>
            <span class="vote-sell">卖出 ${sellCount}</span>
        </div>

        <div class="ai-hero-details">
            <div class="detail-item">
                <div class="d-label">置信度</div>
                <div class="d-value d-value-blue">${confidence}%</div>
            </div>
            <div class="detail-item">
                <div class="d-label">风险等级</div>
                <div class="d-value">${signal.risk_level || '中'}</div>
            </div>
        </div>

        <!-- 风险评估描述 -->
        <div class="risk-assessment-block">
            <div class="risk-assessment-title"><i class="ri-shield-check-line"></i> 风险评估</div>
            <div class="risk-assessment-content">${escapeSignalHtml(riskAssessment)}</div>
        </div>

        ${signal.final_reason ? `<div class="final-reason-block">${escapeSignalHtml(signal.final_reason)}</div>` : ''}

        <!-- 免责声明 -->
        <div class="disclaimer-block">
            <div class="disclaimer-icon"><i class="ri-error-warning-line"></i></div>
            <div class="disclaimer-text">
                <strong>免责声明：</strong>本分析仅供参考，不构成投资建议。加密货币投资有风险，入市需谨慎。
            </div>
        </div>
    </div>`;

    container.querySelectorAll('.vote-bar [data-flex]').forEach((el) => {
        el.style.flex = el.dataset.flex || '0.01';
    });

    // 渲染仪表盘
    setTimeout(() => {
        const gaugeCanvas = document.getElementById('heroGauge');
        if (gaugeCanvas && typeof drawGauge === 'function') {
            drawGauge(gaugeCanvas, confidence);
        }
    }, 100);

    // 当收到新的英雄信号时，重新加载最近信号列表来刷新头部滚动条
    if (typeof loadRecentSignals === 'function') loadRecentSignals();
}

// 从信号列表生成头部滚动条（多条信号滚动）
export function updateSignalTickerFromList(history) {
    const track = document.getElementById('signalTickerTrack');
    if (!track || !history || history.length === 0) return;

    // 构建所有信号 item
    const items = history.map(s => {
        const sig = s.signal || 'HOLD';
        const sigCn = { BUY: '买入', SELL: '卖出', HOLD: '观望' }[sig] || '观望';
        const sigClass = sig === 'BUY' ? 'sig-buy' : sig === 'SELL' ? 'sig-sell' : 'sig-hold';
        const time = s.created_at ? new Date(s.created_at).toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'}) : '--:--';
        const price = Number(s.price_at_signal) || 0;
        const conf = Number(s.confidence) || 0;

        return `<span class="signal-ticker-item ${sigClass}">` +
            `<span class="sig-dot"></span>` +
            `<span class="sig-label">${sigCn}</span>` +
            `<span class="sig-sep">·</span>` +
            `${s.symbol || ''}` +
            `<span class="sig-sep">·</span>` +
            `置信度 <b>${conf}%</b>` +
            `<span class="sig-sep">·</span>` +
            `$${price}` +
            `<span class="sig-sep">·</span>` +
            `<i class="ri-time-line"></i> ${time}` +
            `</span>`;
    }).join('');

    // 测量一组宽度，动态重复填满屏幕
    track.classList.remove('animating');
    track.style.animation = 'none';
    track.innerHTML = items;
    requestAnimationFrame(() => {
        const oneGroupW = track.scrollWidth;
        const viewW = window.innerWidth;
        const repeatCount = Math.max(1, Math.ceil((viewW * 1.5) / oneGroupW));
        track.innerHTML = items.repeat(repeatCount) + items.repeat(repeatCount);
        requestAnimationFrame(() => {
            const halfW = track.scrollWidth / 2;
            const speed = 50;
            const duration = halfW / speed;
            track.style.setProperty('--signal-duration', duration + 's');
            track.style.animation = '';
            track.classList.add('animating');
        });
    });
}

// 信号更新（实时更新）
export function updateSignalFromWs(signalData) {
    const container = document.getElementById('aiSignalHero');
    if (container && signalData) {
        // 清除初始化状态（如果还在初始化中）
        clearInitPolling();
        initState.isInitializing = false;

        currentSignal = signalData;
        renderSignalHero(container, signalData);
    }
}

// 加载信号历史
export async function loadRecentSignals() {
    const container = document.getElementById('recentSignals');
    if (!container) return;

    try {
        const resp = await authFetch(`${API_BASE}/api/ai/history?limit=10`);
        if (!resp.ok) return;
        const data = await resp.json();

        if (!data.history || data.history.length === 0) {
            container.innerHTML = '<div class="no-data">暂无信号记录</div>';
            return;
        }

        container.innerHTML = data.history.map(s => {
            const dotCls = s.signal === 'BUY' ? 'dot-buy' : s.signal === 'SELL' ? 'dot-sell' : 'dot-hold';
            const sigCn = { BUY: '买入', SELL: '卖出', HOLD: '观望' }[s.signal] || '观望';
            const time = s.created_at ? new Date(s.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '--';

            return `<div class="signal-item">
                <div class="signal-dot ${dotCls}"></div>
                <span class="signal-time">${escapeHtml(time)}</span>
                <span class="signal-msg"><strong>${escapeHtml(s.symbol)}</strong> ${escapeHtml(sigCn)} · 置信度 ${Number(s.confidence) || 0}% · $${Number(s.price_at_signal) || 0}</span>
            </div>`;
        }).join('');

        // 同步更新头部信号滚动条（多条信号）
        updateSignalTickerFromList(data.history);

    } catch (e) {
        if (SIGNAL_DEBUG) console.warn('加载信号历史失败:', e);
    }
}

// 监听 WebSocket 新信号
window.addEventListener('ws-signal', (e) => {
    updateSignalFromWs(e.detail);
});

// 页面卸载时清理定时器
window.addEventListener('beforeunload', () => {
    clearInitPolling();
});

window.GangziApp = window.GangziApp || {};
Object.assign(window.GangziApp, {
    loadLatestSignal,
    loadRecentSignals,
});
