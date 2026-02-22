/**
 * 钢子出击 - 主应用入口 (ES Module)
 * Tab 切换、时间更新、初始化所有模块
 * #41 修复：保存 setInterval ID 防止泄漏
 * #43 修复：Tab 切换加载标记，避免重复请求
 */
import { checkAuth } from './auth.js';
import { initWebSocket, closeWebSockets, getWebSocketStatus } from './websocket.js';

const App = window.GangziApp || window;

// #41 修复：保存定时器 ID
let _appTimers = [];
const _tabLoadedCache = {}; // #43 修复：Tab 已加载标记
let _lastWsStatus = null;
let _wsToastReady = false;
let _lastWsToastText = '';
let _toastTimer = null;
let _lastToastText = '';
let _lastToastAt = 0;
let _lastReconnectToastAt = 0;

// ============ 页面加载 ============
document.addEventListener('DOMContentLoaded', async () => {
    const allowed = await checkAuth();
    if (!allowed) return;
    initApp();
});

export async function initApp() {
    if (window.__APP_INIT_DONE__) return;
    window.__APP_INIT_DONE__ = true;

    // 清理旧定时器（防止 initApp 被意外重调）
    _appTimers.forEach(id => clearInterval(id));
    _appTimers = [];

    // 主题初始化
    initThemeToggle();

    // Tab 切换
    initTabs();
    activateTabFromHash();

    // 时间更新
    updateHeaderTime();
    _appTimers.push(setInterval(updateHeaderTime, 1000));

    // WebSocket
    initWebSocket();

    // 行情数据
    (App.loadMarketData || loadMarketData)();

    // 图表
    (App.initCharts || initCharts)();

    // AI 信号
    (App.loadLatestSignal || loadLatestSignal)();
    (App.loadRecentSignals || loadRecentSignals)();

    // AI 辩论面板
    (App.initDebatePanel || initDebatePanel)();

    // AI 聊天
    (App.initChatWidget || initChatWidget)();

    // 语音
    (App.initVoice || initVoice)();

    // 自动交易面板（默认首页，立即加载）
    if (window.initTradingPanel) {
        window.initTradingPanel();
        _tabLoadedCache.trading = true;
    }

    // 新增栏目兜底初始化：避免部分浏览器在首次切换时未触发分支
    if (App.initAnalysisDataPanel) {
        App.initAnalysisDataPanel();
    }

    // #53 修复：非关键模块延迟加载，优先渲染核心内容
    setTimeout(() => {
        // 禁用全屏粒子：避免整页 repaint 闪烁
        // (App.initParticles || initParticles)();
        (App.initExtras || initExtras)();
    }, 500);

    // 定期刷新（行情已由 ws-prices 推送，不再 REST 轮询）
    _appTimers.push(setInterval(() => (App.loadLatestSignal || loadLatestSignal)(), 120000));
    _appTimers.push(setInterval(() => (App.loadRecentSignals || loadRecentSignals)(), 60000));

}

// ============ Tab 切换 ============
function initTabs() {
    const tabs = document.querySelectorAll('.nav-tab');
    const pages = document.querySelectorAll('.tab-page');

    const isDevDisabledTab = (tab) => tab.classList.contains('dev-disabled') || tab.getAttribute('aria-disabled') === 'true';

    const activateTab = (tab) => {
        const target = tab.dataset.tab;

        tabs.forEach(t => {
            t.classList.remove('active');
            t.setAttribute('aria-selected', 'false');
            t.setAttribute('tabindex', '-1');
        });
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');
        tab.setAttribute('tabindex', '0');
        tab.focus();

        pages.forEach(p => {
            p.classList.remove('active');
            if (p.id === `page-${target}`) {
                p.classList.add('active');
            }
        });
        window.location.hash = `tab=${target}`;

        if (target === 'trading' && !_tabLoadedCache.trading) {
            if (window.initTradingPanel) {
                window.initTradingPanel();
            }
            _tabLoadedCache.trading = true;
        } else if (target === 'risk' && !_tabLoadedCache.risk) {
            if (App.loadAccuracyPanel) App.loadAccuracyPanel();
            if (App.initRiskCharts) App.initRiskCharts();
            _tabLoadedCache.risk = true;
        } else if (target === 'signal-log' && !_tabLoadedCache.signalLog) {
            if (App.loadWhalePanel) App.loadWhalePanel();
            if (App.loadSignalHistory) App.loadSignalHistory();
            _tabLoadedCache.signalLog = true;
        } else if (target === 'analysis-data' && !_tabLoadedCache.analysisData) {
            if (App.initAnalysisDataPanel) {
                App.initAnalysisDataPanel();
            }
            _tabLoadedCache.analysisData = true;
        } else if (target === 'admin' && !_tabLoadedCache.admin) {
            if (window.initMonitoringPanel) {
                window.initMonitoringPanel();
            }
            _tabLoadedCache.admin = true;
        }
    };

    tabs.forEach(tab => {
        tab.addEventListener('click', (event) => {
            if (isDevDisabledTab(tab)) {
                event.preventDefault();
                event.stopPropagation();
                tab.classList.remove('active');
                tab.setAttribute('aria-selected', 'false');
                showToast('该功能开发中，当前版本暂不可用');
                return;
            }
            activateTab(tab);
        });

        tab.addEventListener('keydown', (event) => {
            if (event.key !== 'Enter' && event.key !== ' ') return;
            event.preventDefault();
            tab.click();
        });
    });
}

// ============ 时间更新 ============
function updateHeaderTime() {
    const el = document.getElementById('headerTime');
    if (el) {
        const now = new Date();
        el.textContent = now.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        });
    }
}

function activateTabFromHash() {
    const raw = (window.location.hash || '').replace(/^#/, '');
    if (!raw.startsWith('tab=')) return;
    const tabName = raw.slice(4);
    // 安全校验：只允许字母、数字、连字符，防止选择器注入
    if (!/^[a-zA-Z0-9-]+$/.test(tabName)) return;
    const targetTab = document.querySelector(`.nav-tab[data-tab="${tabName}"]`);
    if (targetTab && !targetTab.classList.contains('dev-disabled')) {
        targetTab.click();
    }
}

// 支持浏览器前进/后退按钮切换 Tab
window.addEventListener('hashchange', activateTabFromHash);

function showToast(message) {
    const now = Date.now();
    if (message === _lastToastText && now - _lastToastAt < 1200) {
        return;
    }

    let root = document.getElementById('appToast');
    if (!root) {
        root = document.createElement('div');
        root.id = 'appToast';
        root.className = 'app-toast';
        // #P1 修复：添加无障碍属性
        root.setAttribute('role', 'alert');
        root.setAttribute('aria-live', 'assertive');
        document.body.appendChild(root);
    }
    _lastToastText = message;
    _lastToastAt = now;
    root.textContent = message;
    root.classList.add('show');
    if (_toastTimer) {
        clearTimeout(_toastTimer);
    }
    _toastTimer = setTimeout(() => {
        root.classList.remove('show');
        _toastTimer = null;
    }, 1800);
}

// HTML 事件处理器需要的全局函数
window.showToast = showToast;

// #LOW-19 修复：网络恢复后自动刷新
window.addEventListener('online', () => {
    showToast('网络已恢复，正在刷新数据...');
    // 刷新关键数据
    setTimeout(() => {
        if (window.GangziApp?.loadMarketData) {
            window.GangziApp.loadMarketData();
        }
        if (window.GangziApp?.loadLatestSignal) {
            window.GangziApp.loadLatestSignal();
        }
    }, 500);
});

window.addEventListener('ws-connection-change', (event) => {
    const connected = Boolean(event?.detail?.connected);
    const text = String(event?.detail?.text || '');
    if (!_wsToastReady) {
        _wsToastReady = true;
        _lastWsStatus = connected;
        _lastWsToastText = text;
        return;
    }

    if (_lastWsStatus === connected && _lastWsToastText === text) {
        return;
    }
    _lastWsStatus = connected;
    _lastWsToastText = text;

    if (connected) {
        showToast('实时连接已恢复');
        return;
    }

    if (text.includes('重连中')) {
        if (Date.now() - _lastReconnectToastAt < 8000) {
            return;
        }
        _lastReconnectToastAt = Date.now();
        showToast(`实时连接${text}`);
        return;
    }

    showToast('实时连接已断开，正在自动重连...');
});

// #LOW-17 修复：尊重用户减少动画偏好
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
if (prefersReducedMotion.matches) {
    document.documentElement.classList.add('reduce-motion');
}
prefersReducedMotion.addEventListener('change', (e) => {
    if (e.matches) {
        document.documentElement.classList.add('reduce-motion');
    } else {
        document.documentElement.classList.remove('reduce-motion');
    }
});

function showAppConfirm(message) {
    return new Promise((resolve) => {
        let mask = document.getElementById('appConfirmMask');
        if (!mask) {
            mask = document.createElement('div');
            mask.id = 'appConfirmMask';
            mask.className = 'app-confirm-mask';
            mask.innerHTML = `
                <div class="app-confirm-box">
                    <div id="appConfirmText" class="app-confirm-text"></div>
                    <div class="app-confirm-actions">
                        <button type="button" id="appConfirmNo" class="header-btn">取消</button>
                        <button type="button" id="appConfirmYes" class="header-btn">确定</button>
                    </div>
                </div>
            `;
            document.body.appendChild(mask);
        }
        const text = document.getElementById('appConfirmText');
        const noBtn = document.getElementById('appConfirmNo');
        const yesBtn = document.getElementById('appConfirmYes');
        if (text) text.textContent = message;
        mask.classList.add('show');
        const cleanup = (result) => {
            mask.classList.remove('show');
            noBtn?.removeEventListener('click', onNo);
            yesBtn?.removeEventListener('click', onYes);
            resolve(result);
        };
        const onNo = () => cleanup(false);
        const onYes = () => cleanup(true);
        noBtn?.addEventListener('click', onNo);
        yesBtn?.addEventListener('click', onYes);
    });
}

window.showAppConfirm = showAppConfirm;

// #HIGH-4 修复：添加全局清理函数供 logout 调用
function cleanupApp() {
    _appTimers.forEach(id => clearInterval(id));
    _appTimers = [];
    window.removeEventListener('hashchange', activateTabFromHash);

    // 清理 WebSocket
    closeWebSockets();

    // 清理 particles 动画
    if (window.particleAnimId) {
        cancelAnimationFrame(window.particleAnimId);
        window.particleAnimId = null;
    }

    // 清理 ai-signal 轮询
    if (window._signalPollTimer) {
        clearInterval(window._signalPollTimer);
        window._signalPollTimer = null;
    }

}

window.cleanupApp = cleanupApp;

// ============ 主题切换（iOS 26 白天模式） ============
function initThemeToggle() {
    const saved = localStorage.getItem('gangzi-theme');
    const btn = document.getElementById('themeToggle');
    if (saved === 'light') {
        document.body.classList.add('light-theme');
        if (btn) btn.innerHTML = '<i class="ri-moon-line"></i>';
    }
    if (btn) {
        btn.addEventListener('click', () => {
            // 启用过渡动画
            document.body.classList.add('theme-transition');
            const isLight = document.body.classList.toggle('light-theme');
            btn.innerHTML = isLight ? '<i class="ri-moon-line"></i>' : '<i class="ri-sun-line"></i>';
            localStorage.setItem('gangzi-theme', isLight ? 'light' : 'dark');
            // 强制重绘，确保 CSS 变量立即生效
            void document.body.offsetHeight;
            // 更新 Chart.js 图表刻度颜色
            setTimeout(() => {
                document.querySelectorAll('canvas').forEach(c => {
                    const chart = Chart.getChart?.(c);
                    if (chart) {
                        const tickColor = isLight ? '#636366' : '#b0b8c4';
                        ['x','y'].forEach(axis => {
                            if (chart.options.scales?.[axis]?.ticks) {
                                chart.options.scales[axis].ticks.color = tickColor;
                            }
                        });
                        chart.update('none');
                    }
                });
            }, 50);
            // 350ms 后移除过渡类，避免后续操作产生不必要的过渡
            setTimeout(() => document.body.classList.remove('theme-transition'), 400);
        });
    }
}

// === 标签切换处理：不主动断开 WS，避免后台漏掉成交/持仓推送 ===

document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    // 保持 WebSocket 常连。后台时浏览器可能有节流，但不应主动断开。
    return;
  } else {
    // 切回前台时，若 WS 意外断开则补连。
    try {
      const st = getWebSocketStatus();
      if (!st?.market?.connected || !st?.signal?.connected) {
        initWebSocket();
      }
    } catch (_) {}
  }
});
