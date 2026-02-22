/**
 * 钢子出击 - 行情数据展示
 * 行情条 + 概览卡片 + 价格闪烁动画
 * #19/#20/#22 修复：增量 DOM 更新，避免全量 innerHTML 导致的动画重置和性能问题
 */
import { authFetch, escapeHtml, API_BASE } from './auth.js';

const MARKET_DEBUG = false;

const COIN_COLORS = {
    BTCUSDT: '#f7931a', ETHUSDT: '#627eea', BNBUSDT: '#f3ba2f',
    SOLUSDT: '#00ffa3', XRPUSDT: '#23292f', ADAUSDT: '#0033ad',
    DOGEUSDT: '#c2a633', AVAXUSDT: '#e84142', DOTUSDT: '#e6007a',
    MATICUSDT: '#8247e5',
};

const COIN_NAMES = {
    BTCUSDT: 'BTC', ETHUSDT: 'ETH', BNBUSDT: 'BNB', SOLUSDT: 'SOL',
    XRPUSDT: 'XRP', ADAUSDT: 'ADA', DOGEUSDT: 'DOGE', AVAXUSDT: 'AVAX',
    DOTUSDT: 'DOT', MATICUSDT: 'MATIC',
};

let lastPrices = {};
let _tickerInitialized = false;
// #22 修复：存储当前 animatePrice 的 rAF id，同一元素只保留一个动画
const _priceAnimFrames = {};

// 连接状态跟踪
let _wsConnected = false;
let _connectionWarningShown = false;

// ============ 连接状态警告 ============
function showConnectionWarning(show) {
    let warningEl = document.getElementById('market-connection-warning');

    if (show) {
        if (!warningEl) {
            warningEl = document.createElement('div');
            warningEl.id = 'market-connection-warning';
            warningEl.className = 'connection-warning';
            warningEl.innerHTML = `
                <span class="warning-icon"><i class="ri-error-warning-line"></i></span>
                <span class="warning-text">行情连接已断开，数据可能不是最新的</span>
                <button class="warning-close" onclick="this.parentElement.style.display='none'">×</button>
            `;

            // 插入到页面顶部或行情区域
            const marketSection = document.getElementById('marketSection');
            const container = marketSection || document.querySelector('.main-content') || document.body;
            container.insertBefore(warningEl, container.firstChild);
        }
        warningEl.style.display = 'flex';
        _connectionWarningShown = true;
    } else if (warningEl) {
        warningEl.style.display = 'none';
        _connectionWarningShown = false;
    }
}

// 监听 WebSocket 连接状态变化
window.addEventListener('ws-connection-change', (e) => {
    const { connected, text } = e.detail;
    _wsConnected = connected;

    if (!connected && text !== '已连接') {
        // 连接断开或重连中，显示警告
        showConnectionWarning(true);

        // 更新行情显示为"连接中"状态
        updateMarketStatusIndicator(false);
    } else if (connected) {
        // 连接恢复，隐藏警告
        showConnectionWarning(false);
        updateMarketStatusIndicator(true);
    }
});

// 更新行情状态指示器
function updateMarketStatusIndicator(connected) {
    // 更新行情条样式
    const track = document.getElementById('tickerTrack');
    if (track) {
        track.style.opacity = connected ? '1' : '0.5';
        if (!connected) {
            track.classList.add('paused');
        } else {
            track.classList.remove('paused');
        }
    }

    // 更新概览卡片
    const cards = document.querySelectorAll('#overviewCards .stat-card');
    cards.forEach(card => {
        if (!connected) {
            card.classList.add('stale');
        } else {
            card.classList.remove('stale');
        }
    });
}

// 底部行情滚动条 — 真正无缝循环
function updateTickerBar(prices) {
    const track = document.getElementById('tickerTrack');
    if (!track || !prices) return;

    if (!_tickerInitialized || track.children.length === 0) {
        let html = '';
        for (const [symbol, data] of Object.entries(prices)) {
            const name = COIN_NAMES[symbol] || symbol;
            const price = parseFloat(data.price || 0);
            const change = parseFloat(data.change_24h || 0);
            const isUp = change >= 0;
            html += `<div class="ticker-item" data-sym="${symbol}">
                <span class="sym">${escapeHtml(name)}</span>
                <span class="price ${isUp ? 'g' : 'r'}">$${formatPrice(price)}</span>
                <span class="chg ${isUp ? 'g-bg' : 'r-bg'}">${isUp ? '▲' : '▼'} ${Math.abs(change).toFixed(2)}%</span>
            </div>`;
        }
        // 动态重复填满屏幕，再复制一份做无缝
        track.innerHTML = html;
        _tickerInitialized = true;
        requestAnimationFrame(() => {
            const oneGroupW = track.scrollWidth;
            const viewW = window.innerWidth;
            const repeatCount = Math.max(1, Math.ceil((viewW * 1.5) / oneGroupW));
            track.innerHTML = html.repeat(repeatCount) + html.repeat(repeatCount);
            requestAnimationFrame(() => {
                const halfW = track.scrollWidth / 2;
                const speed = 50;
                const duration = halfW / speed;
                track.style.setProperty('--scroll-duration', duration + 's');
                track.classList.add('animating');
            });
        });
    } else {
        const items = track.querySelectorAll('.ticker-item');
        items.forEach(item => {
            const sym = item.dataset.sym;
            const data = prices[sym];
            if (!data) return;
            const price = parseFloat(data.price || 0);
            const change = parseFloat(data.change_24h || 0);
            const isUp = change >= 0;
            const priceEl = item.querySelector('.price');
            const chgEl = item.querySelector('.chg');
            if (priceEl) {
                priceEl.textContent = `$${formatPrice(price)}`;
                priceEl.className = `price ${isUp ? 'g' : 'r'}`;
            }
            if (chgEl) {
                chgEl.textContent = `${isUp ? '▲' : '▼'} ${Math.abs(change).toFixed(2)}%`;
                chgEl.className = `chg ${isUp ? 'g-bg' : 'r-bg'}`;
            }
        });
    }
}

// #20 修复：概览卡片首次 innerHTML，后续只更新价格和涨跌文字
let _cardsInitialized = false;

function updateOverviewCards(prices) {
    const container = document.getElementById('overviewCards');
    if (!container || !prices) return;

    const topSymbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'];

    if (!_cardsInitialized || container.children.length === 0) {
        let html = '';
        for (const symbol of topSymbols) {
            const data = prices[symbol];
            if (!data) continue;
            const name = COIN_NAMES[symbol];
            const price = parseFloat(data.price || 0);
            const change = parseFloat(data.change_24h || 0);
            const isUp = change >= 0;
            html += `<div class="stat-card ${isUp ? 'up' : 'down'}" data-sym="${symbol}">
                <div class="icon ${isUp ? 'up' : 'down'}">${isUp ? '<i class="ri-arrow-up-line"></i>' : '<i class="ri-arrow-down-line"></i>'}</div>
                <div class="label">${escapeHtml(name)}/USDT</div>
                <div class="value" id="price-${symbol}">$${formatPrice(price)}</div>
                <div class="change ${isUp ? 'g-bg' : 'r-bg'}">${isUp ? '▲' : '▼'} ${Math.abs(change).toFixed(2)}%</div>
            </div>`;
        }
        container.innerHTML = html;
        _cardsInitialized = true;
    } else {
        // 增量更新
        for (const symbol of topSymbols) {
            const data = prices[symbol];
            if (!data) continue;
            const card = container.querySelector(`[data-sym="${symbol}"]`);
            if (!card) continue;
            const price = parseFloat(data.price || 0);
            const change = parseFloat(data.change_24h || 0);
            const isUp = change >= 0;
            // 不更新 price textContent — 由 animatePrice 处理
            const chgEl = card.querySelector('.change');
            const iconEl = card.querySelector('.icon');
            if (chgEl) {
                chgEl.textContent = `${isUp ? '▲' : '▼'} ${Math.abs(change).toFixed(2)}%`;
                chgEl.className = `change ${isUp ? 'g-bg' : 'r-bg'}`;
            }
            card.classList.toggle('up', isUp);
            card.classList.toggle('down', !isUp);
            if (iconEl) {
                iconEl.classList.toggle('up', isUp);
                iconEl.classList.toggle('down', !isUp);
                iconEl.innerHTML = isUp ? '<i class="ri-arrow-up-line"></i>' : '<i class="ri-arrow-down-line"></i>';
            }
        }
    }
}

// 价格格式化
function formatPrice(price) {
    if (price >= 1000) return price.toLocaleString('en-US', { maximumFractionDigits: 2 });
    if (price >= 1) return price.toFixed(2);
    if (price >= 0.01) return price.toFixed(4);
    return price.toFixed(6);
}

/**
 * #22 修复：数字滚动过渡动画 — 同一元素只保留一个动画
 */
const _isMobile = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent);

function animatePrice(el, fromVal, toVal, duration = 600) {
    if (!el || fromVal === toVal) return;
    // 移动端跳过动画，直接赋值
    if (_isMobile) {
        el.textContent = '$' + formatPrice(toVal);
        return;
    }
    const elId = el.id || '';
    // 取消同一元素上的旧动画
    if (_priceAnimFrames[elId]) cancelAnimationFrame(_priceAnimFrames[elId]);

    const startTime = performance.now();
    const diff = toVal - fromVal;

    function tick(now) {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 4);
        const current = fromVal + diff * eased;
        el.textContent = '$' + formatPrice(current);
        if (progress < 1) {
            _priceAnimFrames[elId] = requestAnimationFrame(tick);
        } else {
            delete _priceAnimFrames[elId];
        }
    }
    _priceAnimFrames[elId] = requestAnimationFrame(tick);
}

// 监听 WebSocket 价格更新
window.addEventListener('ws-prices', (e) => {
    const prices = e.detail;

    // 连接恢复时隐藏警告
    if (!_wsConnected) {
        _wsConnected = true;
        showConnectionWarning(false);
        updateMarketStatusIndicator(true);
    }

    updateTickerBar(prices);
    updateOverviewCards(prices);

    // 对概览卡片中的价格做滚动动画
    for (const sym of ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT']) {
        const data = prices[sym];
        if (!data) continue;
        const newPrice = parseFloat(data.price || 0);
        const oldPrice = lastPrices[sym] || 0;
        if (oldPrice > 0 && newPrice !== oldPrice) {
            const el = document.getElementById(`price-${sym}`);
            if (el) animatePrice(el, oldPrice, newPrice);
        }
    }

    // 保存旧价格
    for (const [sym, data] of Object.entries(prices)) {
        lastPrices[sym] = parseFloat(data.price || 0);
    }
});

// 监听信号更新（显示通知）
window.addEventListener('ws-signal', (e) => {
    const signal = e.detail;
    if (MARKET_DEBUG) console.debug('[Market] 收到新信号:', signal);

    // 可以在这里添加信号提示动画或通知
    showSignalNotification(signal);
});

// 显示信号通知
function showSignalNotification(signal) {
    let notifContainer = document.getElementById('signal-notifications');
    if (!notifContainer) {
        notifContainer = document.createElement('div');
        notifContainer.id = 'signal-notifications';
        notifContainer.className = 'signal-notifications';
        document.body.appendChild(notifContainer);
    }

    const notif = document.createElement('div');
    notif.className = `signal-notification ${signal.direction || 'buy'}`;
    notif.innerHTML = `
        <div class="signal-icon"><i class="ri-bar-chart-2-line"></i></div>
        <div class="signal-content">
            <div class="signal-title">${signal.symbol || '未知'} - ${signal.direction === 'buy' ? '买入' : '卖出'}信号</div>
            <div class="signal-desc">${signal.reason || 'AI生成交易信号'}</div>
        </div>
    `;

    notifContainer.appendChild(notif);

    // 3秒后自动移除
    setTimeout(() => {
        notif.classList.add('fade-out');
        setTimeout(() => notif.remove(), 300);
    }, 3000);
}

// 初始加载
export async function loadMarketData() {
    try {
        const resp = await authFetch(`${API_BASE}/api/market/prices`);
        if (resp.ok) {
            const data = await resp.json();
            if (data.prices && Object.keys(data.prices).length > 0) {
                updateTickerBar(data.prices);
                updateOverviewCards(data.prices);
            }
        }
    } catch (e) {
        if (MARKET_DEBUG) console.warn('加载行情失败:', e);
    }
}

window.GangziApp = window.GangziApp || {};
window.GangziApp.loadMarketData = loadMarketData;
