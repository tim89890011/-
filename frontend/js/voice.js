/**
 * 钢子出击 - 语音播报
 * 说明：
 * - 不做 TTS，只做"提示音"
 * - 用户要求：只在真实成交（filled）时响，并区分买入/卖出两套声音
 */

const VOICE_ENABLED_KEY = 'gangzi_voice_enabled';
const TRADE_BUY_ENABLED_KEY = 'gangzi_trade_sound_buy_enabled';
const TRADE_SELL_ENABLED_KEY = 'gangzi_trade_sound_sell_enabled';
const PANEL_ID = 'voicePanel';
const PANEL_STYLE_ID = 'voicePanelStyle';

/**
 * 获取语音开关状态
 * @returns {boolean} 是否开启语音，默认 true（首次访问）
 */
export function isVoiceEnabled() {
    const stored = localStorage.getItem(VOICE_ENABLED_KEY);
    // 默认开启（首次访问或从未设置过）
    return stored === null ? true : stored === 'true';
}

function _getBoolSetting(key, defaultValue) {
    const stored = localStorage.getItem(key);
    if (stored === null) return defaultValue;
    return stored === 'true';
}

export function isTradeBuySoundEnabled() {
    return _getBoolSetting(TRADE_BUY_ENABLED_KEY, true);
}

export function isTradeSellSoundEnabled() {
    return _getBoolSetting(TRADE_SELL_ENABLED_KEY, true);
}

function setTradeBuySoundEnabled(enabled) {
    localStorage.setItem(TRADE_BUY_ENABLED_KEY, enabled ? 'true' : 'false');
}

function setTradeSellSoundEnabled(enabled) {
    localStorage.setItem(TRADE_SELL_ENABLED_KEY, enabled ? 'true' : 'false');
}

/**
 * 设置语音开关状态
 * @param {boolean} enabled 是否开启
 */
export function setVoiceEnabled(enabled) {
    localStorage.setItem(VOICE_ENABLED_KEY, enabled ? 'true' : 'false');
    // 派发状态变更事件，供其他组件监听
    window.dispatchEvent(new CustomEvent('voice-setting-changed', {
        detail: { enabled }
    }));
}

/**
 * 切换语音开关状态
 * @returns {boolean} 切换后的状态
 */
export function toggleVoice() {
    const newState = !isVoiceEnabled();
    setVoiceEnabled(newState);
    updateVoiceButtonUI(newState);
    return newState;
}

/**
 * 更新语音按钮 UI
 * @param {boolean} enabled 是否开启
 */
function updateVoiceButtonUI(enabled) {
    const btn = document.getElementById('voiceToggle');
    if (btn) {
        btn.innerHTML = enabled ? '<i class="ri-volume-up-line"></i>' : '<i class="ri-volume-mute-line"></i>';
        btn.title = enabled ? '提示音设置（已开启）' : '提示音设置（已关闭）';
        btn.classList.toggle('voice-disabled', !enabled);
    }
}

let _panelGlobalListenersBound = false;
let _buyBlobUrl = null;
let _sellBlobUrl = null;
let _blobsReady = false;
// 后台未播放的提示音队列：当后台播放失败时记录，回到前台立即补播
const _pendingSounds = [];
const _pendingOrderKeys = new Set();
const _recentPlayedOrderTs = new Map();
let _silentBlobUrl = null;
let _audioGestureUnlocked = false;
const SOUND_PLAY_GAP_MS = 180;
const _playQueue = [];
const _queuedOrderKeys = new Set();
let _isDrainingPlayQueue = false;

/**
 * 生成一段极短（0.5s）无声 WAV 用于保活
 */
function _createSilentWavUrl() {
    const sr = 8000;
    const samples = sr / 2; // 0.5 秒
    const bytesPerSample = 2;
    const dataLength = samples * bytesPerSample;
    const buf = new ArrayBuffer(44 + dataLength);
    const v = new DataView(buf);
    _writeWavString(v, 0, 'RIFF');
    v.setUint32(4, 36 + dataLength, true);
    _writeWavString(v, 8, 'WAVE');
    _writeWavString(v, 12, 'fmt ');
    v.setUint32(16, 16, true);
    v.setUint16(20, 1, true);     // PCM
    v.setUint16(22, 1, true);     // mono
    v.setUint32(24, sr, true);
    v.setUint32(28, sr * bytesPerSample, true);
    v.setUint16(32, bytesPerSample, true);
    v.setUint16(34, 16, true);
    _writeWavString(v, 36, 'data');
    v.setUint32(40, dataLength, true);
    // 数据全 0 = 静音，ArrayBuffer 默认就是 0，无需写入
    return URL.createObjectURL(new Blob([buf], { type: 'audio/wav' }));
}

async function _primeAudioGesture() {
    if (_audioGestureUnlocked) return;
    try {
        if (!_silentBlobUrl) _silentBlobUrl = _createSilentWavUrl();
        const a = new Audio(_silentBlobUrl);
        a.volume = 0;
        await a.play();
        a.pause();
        _audioGestureUnlocked = true;
    } catch (e) {
        // 浏览器可能阻止，等待下一次手势重试
    }
}

function _writeWavString(view, offset, str) {
    for (let i = 0; i < str.length; i++) {
        view.setUint8(offset + i, str.charCodeAt(i));
    }
}

function _audioBufferToWav(buffer) {
    const sampleRate = buffer.sampleRate;
    const data = buffer.getChannelData(0);
    const bytesPerSample = 2;
    const dataLength = data.length * bytesPerSample;
    const buf = new ArrayBuffer(44 + dataLength);
    const v = new DataView(buf);

    _writeWavString(v, 0, 'RIFF');
    v.setUint32(4, 36 + dataLength, true);
    _writeWavString(v, 8, 'WAVE');
    _writeWavString(v, 12, 'fmt ');
    v.setUint32(16, 16, true);
    v.setUint16(20, 1, true);
    v.setUint16(22, 1, true);
    v.setUint32(24, sampleRate, true);
    v.setUint32(28, sampleRate * bytesPerSample, true);
    v.setUint16(32, bytesPerSample, true);
    v.setUint16(34, 16, true);
    _writeWavString(v, 36, 'data');
    v.setUint32(40, dataLength, true);

    let off = 44;
    for (let i = 0; i < data.length; i++) {
        const s = Math.max(-1, Math.min(1, data[i]));
        v.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        off += 2;
    }
    return buf;
}

async function _prerenderSounds() {
    if (_blobsReady) return;
    try {
        const presets = {
            buy:  [523.25, 659.25, 783.99],
            sell: [783.99, 659.25, 523.25]
        };
        for (const [kind, freqs] of Object.entries(presets)) {
            const sr = 44100;
            const offline = new OfflineAudioContext(1, Math.ceil(sr * 0.6), sr);
            const step = 0.13;
            freqs.forEach((f, i) => {
                const osc = offline.createOscillator();
                const gain = offline.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(f, i * step);
                gain.gain.setValueAtTime(0.14, i * step);
                gain.gain.exponentialRampToValueAtTime(0.01, i * step + 0.18);
                osc.connect(gain);
                gain.connect(offline.destination);
                osc.start(i * step);
                osc.stop(i * step + 0.2);
            });
            const rendered = await offline.startRendering();
            const wav = _audioBufferToWav(rendered);
            const blob = new Blob([wav], { type: 'audio/wav' });
            const url = URL.createObjectURL(blob);
            if (kind === 'buy') _buyBlobUrl = url;
            else _sellBlobUrl = url;
        }
        _blobsReady = true;
    } catch (e) {
        // OfflineAudioContext 不可用时降级为仅前台可响
    }
}

/**
 * 初始化语音模块
 * 从 localStorage 读取状态并应用
 */
export function initVoice() {
    const enabled = isVoiceEnabled();
    updateVoiceButtonUI(enabled);

    const btn = document.getElementById('voiceToggle');
    if (btn) {
        // 移除旧的事件监听器（防止重复绑定）
        const newBtn = btn.cloneNode(true);
        btn.parentNode.replaceChild(newBtn, btn);
        // 点击喇叭：打开/关闭设置面板
        newBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            await _primeAudioGesture();
            toggleVoicePanel();
        });
    }

    ensureVoicePanel();

    if (_panelGlobalListenersBound) return;
    _panelGlobalListenersBound = true;

    // 点击空白处关闭面板
    document.addEventListener('click', (e) => {
        const panel = document.getElementById(PANEL_ID);
        const voiceBtn = document.getElementById('voiceToggle');
        if (!panel || !panel.classList.contains('show')) return;
        if (panel.contains(e.target)) return;
        if (voiceBtn && voiceBtn.contains(e.target)) return;
        hideVoicePanel();
    });
    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') hideVoicePanel();
    });
    window.addEventListener('resize', () => {
        const panel = document.getElementById(PANEL_ID);
        if (panel && panel.classList.contains('show')) positionVoicePanel(panel);
    });
    window.addEventListener('scroll', () => {
        const panel = document.getElementById(PANEL_ID);
        if (panel && panel.classList.contains('show')) positionVoicePanel(panel);
    }, { passive: true });
}

/**
 * 显示语音状态提示
 * @param {boolean} enabled 是否开启
 */
function showVoiceToast(enabled) {
    const message = enabled ? '提示音已开启' : '提示音已关闭';
    // 优先使用 app.js 中的 showToast
    if (typeof showToast === 'function') {
        showToast(message);
    } else if (window.GangziApp?.showToast) {
        window.GangziApp.showToast(message);
    }
}

/**
 * 播放成交提示音（预渲染 WAV，统一走 HTMLAudio）
 * - buy: 向上
 * - sell: 向下
 * @returns {boolean} 是否真正播放成功
 */
async function _playTradeSound(kind) {
    try {
        if (!_blobsReady) await _prerenderSounds();
        const url = kind === 'sell' ? _sellBlobUrl : _buyBlobUrl;
        if (url) {
            try {
                await new Audio(url).play();
                return true;
            } catch (e) {
                // HTML5 Audio 也被浏览器拦截（后台标签常见）
            }
        }
    } catch (e) {
        // 静默失败
    }
    return false;
}

/**
 * 对外暴露：成交提示音
 * @param {'buy'|'sell'} kind
 */
export function playTradeSound(kind, meta = {}) {
    if (!isVoiceEnabled()) return;
    if (kind === 'buy' && !isTradeBuySoundEnabled()) return;
    if (kind === 'sell' && !isTradeSellSoundEnabled()) return;
    const orderKey = typeof meta.orderId === 'string' && meta.orderId.trim()
        ? meta.orderId.trim()
        : '';
    const now = Date.now();
    if (_recentPlayedOrderTs.size > 300) {
        const cutoff = now - 10 * 60 * 1000;
        for (const [k, ts] of _recentPlayedOrderTs.entries()) {
            if (ts < cutoff) _recentPlayedOrderTs.delete(k);
        }
    }
    if (orderKey) {
        const lastTs = _recentPlayedOrderTs.get(orderKey) || 0;
        if (now - lastTs < 10 * 60 * 1000) return;
        if (_queuedOrderKeys.has(orderKey) || _pendingOrderKeys.has(orderKey)) return;
    }
    _playQueue.push({ kind, key: orderKey, skipQueue: !!meta.skipQueue, ts: now });
    if (orderKey) _queuedOrderKeys.add(orderKey);
    _drainPlayQueue();
}

async function _drainPlayQueue() {
    if (_isDrainingPlayQueue) return;
    _isDrainingPlayQueue = true;
    try {
        while (_playQueue.length > 0) {
            const item = _playQueue.shift();
            if (!item) continue;
            if (item.key) _queuedOrderKeys.delete(item.key);
            let played = false;
            try {
                played = await _playTradeSound(item.kind);
            } catch (_) {
                played = false;
            }
            if (played) {
                if (item.key) _recentPlayedOrderTs.set(item.key, Date.now());
            } else if (!item.skipQueue) {
                const cutoff = Date.now() - 60000;
                while (_pendingSounds.length > 0 && _pendingSounds[0].ts < cutoff) {
                    const old = _pendingSounds.shift();
                    if (old && old.key) _pendingOrderKeys.delete(old.key);
                }
                if (!item.key || !_pendingOrderKeys.has(item.key)) {
                    if (_pendingSounds.length < 100) {
                        _pendingSounds.push({ kind: item.kind, ts: Date.now(), key: item.key || '' });
                        if (item.key) _pendingOrderKeys.add(item.key);
                    }
                }
            }
            if (_playQueue.length > 0) {
                await new Promise((resolve) => setTimeout(resolve, SOUND_PLAY_GAP_MS));
            }
        }
    } finally {
        _isDrainingPlayQueue = false;
    }
}

/**
 * 回到前台时补播后台期间未能播放的提示音
 */
function _flushPendingSounds() {
    if (_pendingSounds.length === 0) return;
    const snapshot = _pendingSounds.splice(0);
    _pendingOrderKeys.clear();
    const cutoff = Date.now() - 60000;
    const toPlay = snapshot.filter(s => s.ts >= cutoff);
    if (toPlay.length === 0) return;
    toPlay.forEach((s) => {
        playTradeSound(s.kind, { orderId: s.key, skipQueue: true });
    });
}

/**
 * 兼容旧接口：曾用于 AI 信号提示
 * 现在改为静默 no-op：全站只保留"成交（filled）提示音"
 */
export function speakText(text) {
    // Intentionally empty. Old modules may still call speakText(),
    // but user要求：不跟随 AI 信号发声，只在真实成交时提示。
    return;
}

function ensureVoicePanel() {
    if (!document.getElementById(PANEL_STYLE_ID)) {
        const style = document.createElement('style');
        style.id = PANEL_STYLE_ID;
        style.textContent = `
          .voice-panel {
            position: fixed;
            z-index: 9999;
            min-width: 220px;
            padding: 12px 12px 10px;
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,.12);
            background: rgba(20, 22, 28, .92);
            box-shadow: 0 12px 40px rgba(0,0,0,.42);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            color: rgba(255,255,255,.92);
            display: none;
          }
          body.light-theme .voice-panel {
            background: rgba(255,255,255,.92);
            border: 1px solid rgba(0,0,0,.08);
            color: rgba(0,0,0,.86);
          }
          .voice-panel.show { display: block; }
          .vp-title { font-weight: 700; font-size: 13px; margin-bottom: 8px; }
          .vp-row { display:flex; align-items:center; justify-content:space-between; gap:10px; padding: 6px 0; }
          .vp-row + .vp-row { border-top: 1px solid rgba(255,255,255,.08); }
          body.light-theme .vp-row + .vp-row { border-top: 1px solid rgba(0,0,0,.06); }
          .vp-label { font-size: 13px; opacity: .95; }
          .vp-hint { font-size: 12px; opacity: .7; margin-top: 8px; }
          .vp-actions { display:flex; align-items:center; gap:8px; }
          .vp-btn {
            border: 1px solid rgba(255,255,255,.14);
            background: rgba(255,255,255,.06);
            color: inherit;
            border-radius: 10px;
            padding: 6px 10px;
            font-size: 12px;
            cursor: pointer;
          }
          body.light-theme .vp-btn {
            border: 1px solid rgba(0,0,0,.10);
            background: rgba(0,0,0,.04);
          }
          .vp-btn:active { transform: translateY(1px); }
          .vp-switch { display:inline-flex; align-items:center; gap:6px; user-select:none; }
          .vp-switch input { width: 16px; height: 16px; }
          .vp-disabled { opacity: .5; pointer-events: none; }
        `;
        document.head.appendChild(style);
    }

    let panel = document.getElementById(PANEL_ID);
    if (panel) return panel;

    panel = document.createElement('div');
    panel.id = PANEL_ID;
    panel.className = 'voice-panel';
    panel.innerHTML = `
      <div class="vp-title">提示音设置（仅真实成交）</div>
      <div class="vp-row">
        <div class="vp-label">总开关</div>
        <label class="vp-switch">
          <input type="checkbox" id="vpMasterToggle">
          <span>启用</span>
        </label>
      </div>
      <div class="vp-row" id="vpBuyRow">
        <div class="vp-label">下单音</div>
        <div class="vp-actions">
          <label class="vp-switch" title="BUY / SHORT">
            <input type="checkbox" id="vpBuyToggle">
            <span>开启</span>
          </label>
          <button type="button" class="vp-btn" id="vpBuyTest">试听</button>
        </div>
      </div>
      <div class="vp-row" id="vpSellRow">
        <div class="vp-label">卖出音</div>
        <div class="vp-actions">
          <label class="vp-switch" title="SELL / COVER">
            <input type="checkbox" id="vpSellToggle">
            <span>开启</span>
          </label>
          <button type="button" class="vp-btn" id="vpSellTest">试听</button>
        </div>
      </div>
      <div class="vp-hint">仅在交易记录出现新的 filled 成交时触发：BUY/SHORT=下单音，SELL/COVER=卖出音。</div>
    `;

    document.body.appendChild(panel);

    // 阻止 panel 内点击冒泡导致立刻关闭
    panel.addEventListener('click', (e) => e.stopPropagation());

    const master = panel.querySelector('#vpMasterToggle');
    const buy = panel.querySelector('#vpBuyToggle');
    const sell = panel.querySelector('#vpSellToggle');
    const buyTest = panel.querySelector('#vpBuyTest');
    const sellTest = panel.querySelector('#vpSellTest');

    master?.addEventListener('change', () => {
        const enabled = !!master.checked;
        setVoiceEnabled(enabled);
        updateVoiceButtonUI(enabled);
        syncVoicePanelUI(panel);
        showVoiceToast(enabled);
    });
    buy?.addEventListener('change', () => {
        setTradeBuySoundEnabled(!!buy.checked);
    });
    sell?.addEventListener('change', () => {
        setTradeSellSoundEnabled(!!sell.checked);
    });
    buyTest?.addEventListener('click', async (e) => {
        e.preventDefault();
        e.stopPropagation();
        await _primeAudioGesture();
        playTradeSound('buy');
    });
    sellTest?.addEventListener('click', async (e) => {
        e.preventDefault();
        e.stopPropagation();
        await _primeAudioGesture();
        playTradeSound('sell');
    });

    syncVoicePanelUI(panel);
    return panel;
}

function syncVoicePanelUI(panel) {
    const enabled = isVoiceEnabled();
    const master = panel.querySelector('#vpMasterToggle');
    const buy = panel.querySelector('#vpBuyToggle');
    const sell = panel.querySelector('#vpSellToggle');
    const buyRow = panel.querySelector('#vpBuyRow');
    const sellRow = panel.querySelector('#vpSellRow');

    if (master) master.checked = enabled;
    if (buy) buy.checked = isTradeBuySoundEnabled();
    if (sell) sell.checked = isTradeSellSoundEnabled();

    buyRow?.classList.toggle('vp-disabled', !enabled);
    sellRow?.classList.toggle('vp-disabled', !enabled);
}

function positionVoicePanel(panel) {
    const btn = document.getElementById('voiceToggle');
    if (!btn) return;

    const r = btn.getBoundingClientRect();
    const margin = 10;
    const panelRect = panel.getBoundingClientRect();

    let top = r.bottom + 10;
    if (top + panelRect.height > window.innerHeight - margin) {
        top = r.top - panelRect.height - 10;
    }
    top = Math.max(margin, Math.min(top, window.innerHeight - panelRect.height - margin));

    let left = r.right - panelRect.width;
    left = Math.max(margin, Math.min(left, window.innerWidth - panelRect.width - margin));

    panel.style.top = `${Math.round(top)}px`;
    panel.style.left = `${Math.round(left)}px`;
}

function showVoicePanel() {
    const panel = ensureVoicePanel();
    syncVoicePanelUI(panel);
    // 先展示再测量定位：否则 display:none 时面板宽高为 0，导致定位跑偏（看起来像"没弹出"）
    panel.classList.add('show');
    positionVoicePanel(panel);
}

function hideVoicePanel() {
    const panel = document.getElementById(PANEL_ID);
    if (!panel) return;
    panel.classList.remove('show');
}

function toggleVoicePanel() {
    const panel = ensureVoicePanel();
    if (panel.classList.contains('show')) hideVoicePanel();
    else showVoicePanel();
}

// 页面回到前台时补播后台期间未能播放的提示音
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
        setTimeout(_flushPendingSounds, 100);
    }
});

// 用户第一次任意交互时做音频预热（浏览器安全策略要求用户手势）
(function _autoUnlockOnFirstGesture() {
    const events = ['click', 'keydown', 'touchstart', 'pointerdown'];
    function unlock() {
        _primeAudioGesture();
        _prerenderSounds();
        events.forEach(e => document.removeEventListener(e, unlock, true));
    }
    events.forEach(e => document.addEventListener(e, unlock, { once: false, capture: true, passive: true }));
})();

// 兜底：即使未通过 auth 初始化，也能让喇叭弹出设置面板（不涉及任何接口请求）
document.addEventListener('DOMContentLoaded', () => {
    try {
        const btn = document.getElementById('voiceToggle');
        if (!btn) return;
        initVoice();
    } catch (e) {
        // 静默失败，避免影响主页面
    }
});

// 暴露到全局 GangziApp
window.GangziApp = window.GangziApp || {};
Object.assign(window.GangziApp, {
    initVoice,
    speakText,
    isVoiceEnabled,
    setVoiceEnabled,
    toggleVoice,
    playTradeSound,
    isTradeBuySoundEnabled,
    isTradeSellSoundEnabled,
});
