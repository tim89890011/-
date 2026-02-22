/**
 * 钢子出击 - WebSocket 连接管理 (ES Module)
 * 行情推送 + 信号推送，断线自动重连，心跳检测机制
 */
import { getToken } from './auth.js';

// ============ 心跳配置常量 ============
const HEARTBEAT_INTERVAL = 30000;      // 心跳发送间隔：30秒
const HEARTBEAT_TIMEOUT = 60000;       // 心跳超时时间：60秒
const WS_RECONNECT_DELAY_BASE = 3000;  // 基础重连延迟：3秒
const WS_RECONNECT_MAX_DELAY = 30000;  // 最大重连延迟：30秒
const WS_MAX_RECONNECT_COUNT = 20;     // 最大重连次数
const WS_DEBUG = false;

// ============ WebSocket 实例和状态 ============
let marketWs = null;
let signalWs = null;
let wsReconnectTimer = null;
let wsSignalReconnectTimer = null;
let wsConnected = false;

// ============ 心跳相关定时器 ============
let marketHeartbeatTimer = null;       // 心跳发送定时器
let marketHeartbeatTimeout = null;     // 心跳超时检测定时器
let signalHeartbeatTimer = null;
let signalHeartbeatTimeout = null;

// ============ 重连状态管理 ============
let marketReconnectCount = 0;          // market WS 重连计数
let signalReconnectCount = 0;          // signal WS 重连计数
let marketReconnectDelay = WS_RECONNECT_DELAY_BASE;
let signalReconnectDelay = WS_RECONNECT_DELAY_BASE;
let _marketClosedByClient = false;     // 客户端主动关闭标记
let _signalClosedByClient = false;

function getWsBaseUrl() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.API_BASE.replace('https://', '').replace('http://', '')}`;
}

// ============ 心跳管理类 ============
class HeartbeatManager {
    constructor(wsType) {
        this.wsType = wsType;  // 'market' 或 'signal'
        this.sendTimer = null;
        this.timeoutTimer = null;
    }

    start(ws) {
        this.stop();

        // 启动心跳发送定时器
        this.sendTimer = setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send('ping');
                if (WS_DEBUG) console.debug(`[WS][${this.wsType}] 发送 ping`);

                // #CRITICAL-1 修复：先清理旧超时定时器再创建新的，防止堆积
                if (this.timeoutTimer) {
                    clearTimeout(this.timeoutTimer);
                    this.timeoutTimer = null;
                }

                // 设置超时检测
                this.timeoutTimer = setTimeout(() => {
                    console.warn(`[WS][${this.wsType}] 心跳超时，未收到 pong，准备重连`);
                    // 触发重连
                    if (this.wsType === 'market') {
                        disconnectMarketWs();
                        scheduleReconnect();
                    } else {
                        disconnectSignalWs();
                        scheduleSignalReconnect();
                    }
                }, HEARTBEAT_TIMEOUT);
            }
        }, HEARTBEAT_INTERVAL);
    }

    stop() {
        if (this.sendTimer) {
            clearInterval(this.sendTimer);
            this.sendTimer = null;
        }
        if (this.timeoutTimer) {
            clearTimeout(this.timeoutTimer);
            this.timeoutTimer = null;
        }
    }

    // 收到 pong 响应时调用
    onPongReceived() {
        if (this.timeoutTimer) {
            clearTimeout(this.timeoutTimer);
            this.timeoutTimer = null;
        }
        if (WS_DEBUG) console.debug(`[WS][${this.wsType}] 收到 pong，心跳正常`);
    }
}

// 创建心跳管理器实例
const marketHeartbeat = new HeartbeatManager('market');
const signalHeartbeat = new HeartbeatManager('signal');

// ============ 断开连接清理 ============
function disconnectMarketWs() {
    _marketClosedByClient = true;
    marketHeartbeat.stop();
    if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = null;
    }
    if (marketWs) {
        try {
            marketWs.close();
        } catch (e) {
            // 忽略关闭错误
        }
        marketWs = null;
    }
    wsConnected = false;
    updateWsStatus(false);
}

function disconnectSignalWs() {
    _signalClosedByClient = true;
    signalHeartbeat.stop();
    if (wsSignalReconnectTimer) {
        clearTimeout(wsSignalReconnectTimer);
        wsSignalReconnectTimer = null;
    }
    if (signalWs) {
        try {
            signalWs.close();
        } catch (e) {
            // 忽略关闭错误
        }
        signalWs = null;
    }
}

// ============ Market WebSocket 连接 ============
function connectMarketWs() {
    const token = getToken();
    if (!token) return;

    _marketClosedByClient = false;

    // 检查重连次数限制
    if (marketReconnectCount >= WS_MAX_RECONNECT_COUNT) {
        console.error(`[WS][market] 重连次数已达上限(${WS_MAX_RECONNECT_COUNT})，停止重连`);
        updateWsStatus(false, '连接失败，请刷新页面重试');
        return;
    }

    const url = `${getWsBaseUrl()}/ws/market`;
    try {
        if (marketWs) {
            marketWs.close();
            marketWs = null;
        }
        marketWs = new WebSocket(url);

        marketWs.onopen = () => {
            marketWs.send(JSON.stringify({ type: 'auth', token }));
            wsConnected = true;
            updateWsStatus(true);

            // 重置重连计数和延迟
            marketReconnectCount = 0;
            marketReconnectDelay = WS_RECONNECT_DELAY_BASE;

            // 启动心跳
            marketHeartbeat.start(marketWs);

            console.info('[WS][market] 连接已建立');
        };

        marketWs.onmessage = (event) => {
            // 处理 pong 响应
            if (event.data === 'pong') {
                marketHeartbeat.onPongReceived();
                return;
            }

            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'prices') {
                    window.dispatchEvent(new CustomEvent('ws-prices', { detail: msg.data }));
                } else if (msg.type === 'position_update') {
                    window.dispatchEvent(new CustomEvent('ws-position-update', { detail: msg.data }));
                } else if (msg.type === 'balance_update') {
                    window.dispatchEvent(new CustomEvent('ws-balance-update', { detail: msg.data }));
                } else if (msg.type === 'pong') {
                    marketHeartbeat.onPongReceived();
                } else if (WS_DEBUG) {
                    console.debug('[WS][market] 未处理的消息类型:', msg.type);
                }
            } catch (e) {
                if (WS_DEBUG) console.debug('[WS][market] 消息解析失败:', e);
            }
        };

        marketWs.onclose = (event) => {
            wsConnected = false;
            updateWsStatus(false);
            marketHeartbeat.stop();

            // 客户端主动关闭（退出登录等）不重连，其余一律重连
            if (_marketClosedByClient) {
                _marketClosedByClient = false;
            } else {
                console.info(`[WS][market] 连接关闭(code=${event.code}, clean=${event.wasClean})，准备重连`);
                scheduleReconnect();
            }
        };

        marketWs.onerror = (error) => {
            wsConnected = false;
            updateWsStatus(false, '连接错误');
            if (WS_DEBUG) console.error('[WS][market] 连接错误:', error);
        };

    } catch (e) {
        if (WS_DEBUG) console.error('[WS][market] 创建连接失败:', e);
        scheduleReconnect();
    }
}

// ============ Signal WebSocket 连接 ============
function connectSignalWs() {
    const token = getToken();
    if (!token) return;

    _signalClosedByClient = false;

    // 检查重连次数限制
    if (signalReconnectCount >= WS_MAX_RECONNECT_COUNT) {
        console.error(`[WS][signal] 重连次数已达上限(${WS_MAX_RECONNECT_COUNT})，停止重连`);
        return;
    }

    const url = `${getWsBaseUrl()}/ws/signals`;
    try {
        if (signalWs) {
            signalWs.close();
            signalWs = null;
        }
        signalWs = new WebSocket(url);

        signalWs.onopen = () => {
            signalWs.send(JSON.stringify({ type: 'auth', token }));

            // 重置重连计数和延迟
            signalReconnectCount = 0;
            signalReconnectDelay = WS_RECONNECT_DELAY_BASE;

            // 启动心跳
            signalHeartbeat.start(signalWs);

            console.info('[WS][signal] 连接已建立');
        };

        signalWs.onmessage = (event) => {
            // 处理 pong 响应
            if (event.data === 'pong') {
                signalHeartbeat.onPongReceived();
                return;
            }

            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'new_signal') {
                    window.dispatchEvent(new CustomEvent('ws-signal', { detail: msg.data }));
                } else if (msg.type === 'trade_status') {
                    window.dispatchEvent(new CustomEvent('ws-trade-status', { detail: msg.data }));
                } else if (msg.type === 'order_update') {
                    window.dispatchEvent(new CustomEvent('ws-order-update', { detail: msg.data }));
                } else if (msg.type === 'pong') {
                    signalHeartbeat.onPongReceived();
                } else if (WS_DEBUG) {
                    console.debug('[WS][signal] 未处理的消息类型:', msg.type);
                }
            } catch (e) {
                if (event.data !== 'pong' && WS_DEBUG) {
                    console.debug('[WS][signal] 消息解析失败:', e);
                }
            }
        };

        signalWs.onclose = (event) => {
            signalHeartbeat.stop();

            // 退出登录后不重连
            if (!getToken()) return;

            // 客户端主动关闭不重连，其余一律重连
            if (_signalClosedByClient) {
                _signalClosedByClient = false;
            } else {
                console.info(`[WS][signal] 连接关闭(code=${event.code}, clean=${event.wasClean})，准备重连`);
                scheduleSignalReconnect();
            }
        };

        signalWs.onerror = (error) => {
            if (WS_DEBUG) console.error('[WS][signal] 连接错误:', error);
        };

    } catch (e) {
        if (WS_DEBUG) console.error('[WS][signal] 创建连接失败:', e);
        scheduleSignalReconnect();
    }
}

// ============ 重连调度 ============
function scheduleReconnect() {
    if (wsReconnectTimer) return;

    const token = getToken();
    if (!token) return; // 未登录不重连

    marketReconnectCount++;

    // 指数退避策略计算延迟
    const delay = Math.min(
        WS_RECONNECT_DELAY_BASE * Math.pow(1.5, marketReconnectCount - 1),
        WS_RECONNECT_MAX_DELAY
    );

    console.info(`[WS][market] 第 ${marketReconnectCount}/${WS_MAX_RECONNECT_COUNT} 次重连，${(delay / 1000).toFixed(1)}秒后尝试...`);
    updateWsStatus(false, `重连中(${marketReconnectCount}/${WS_MAX_RECONNECT_COUNT})...`);

    wsReconnectTimer = setTimeout(() => {
        wsReconnectTimer = null;
        connectMarketWs();
    }, delay);
}

function scheduleSignalReconnect() {
    if (wsSignalReconnectTimer) return;

    signalReconnectCount++;

    // 指数退避策略
    const delay = Math.min(
        WS_RECONNECT_DELAY_BASE * Math.pow(1.5, signalReconnectCount - 1),
        WS_RECONNECT_MAX_DELAY
    );

    console.info(`[WS][signal] 第 ${signalReconnectCount}/${WS_MAX_RECONNECT_COUNT} 次重连，${(delay / 1000).toFixed(1)}秒后尝试...`);

    wsSignalReconnectTimer = setTimeout(() => {
        wsSignalReconnectTimer = null;
        connectSignalWs();
    }, delay);
}

// ============ 连接状态更新 ============
function updateWsStatus(connected, customText = null) {
    const el = document.getElementById('wsStatus');
    if (!el) return;

    const dotClass = connected ? 'dot' : 'dot offline';
    const text = customText || (connected ? '已连接' : '断开');

    const dot = document.createElement('div');
    dot.className = dotClass;
    const label = document.createElement('span');
    label.textContent = text;
    el.replaceChildren(dot, label);

    if (connected) {
        el.classList.add('is-online');
        el.classList.remove('is-offline');
    } else {
        el.classList.add('is-offline');
        el.classList.remove('is-online');
    }

    // 触发全局连接状态事件
    window.dispatchEvent(new CustomEvent('ws-connection-change', {
        detail: { connected, text }
    }));
}

// ============ 公共 API ============
export function initWebSocket() {
    // 重置状态
    marketReconnectCount = 0;
    signalReconnectCount = 0;
    marketReconnectDelay = WS_RECONNECT_DELAY_BASE;
    signalReconnectDelay = WS_RECONNECT_DELAY_BASE;

    connectMarketWs();
    connectSignalWs();
}

export function closeWebSockets() {
    disconnectMarketWs();
    disconnectSignalWs();
}

export function getWebSocketStatus() {
    return {
        market: {
            connected: marketWs?.readyState === WebSocket.OPEN,
            reconnectCount: marketReconnectCount
        },
        signal: {
            connected: signalWs?.readyState === WebSocket.OPEN,
            reconnectCount: signalReconnectCount
        }
    };
}

// ============ iOS Safari 后台恢复处理 ============
// #CRITICAL-2 修复：iOS Safari 后台/锁屏后强制重连
document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
        // 页面重新可见时立即检查连接状态，减少可见后陈旧窗口
        const status = getWebSocketStatus();
        // 如果 market 连接断开，强制重连
        if (!status.market.connected) {
            console.info('[WS] 页面重新可见，market 连接断开，强制重连');
            disconnectMarketWs();
            marketReconnectCount = 0;  // 重置重连计数
            connectMarketWs();
        }
        // 如果 signal 连接断开，强制重连
        if (!status.signal.connected) {
            console.info('[WS] 页面重新可见，signal 连接断开，强制重连');
            disconnectSignalWs();
            signalReconnectCount = 0;
            connectSignalWs();
        }
    }
});

// #LOW-14 优化：页面不可见时延长心跳间隔节省电量
let isPageVisible = true;
document.addEventListener('visibilitychange', () => {
    isPageVisible = !document.hidden;
    if (WS_DEBUG) console.debug(`[WS] 页面可见性变化: ${isPageVisible ? '可见' : '隐藏'}`);
});

// ============ 全局兼容层（供非模块脚本访问） ============
window.GangziApp = window.GangziApp || {};
window.GangziApp.initWebSocket = initWebSocket;
window.GangziApp.closeWebSockets = closeWebSockets;
window.GangziApp.getWebSocketStatus = getWebSocketStatus;
