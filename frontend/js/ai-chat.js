/**
 * 钢子出击 - AI 聊天悬浮窗
 * 右下角 FAB + 聊天窗口 + 打字机效果
 */

// 全局依赖（由 auth.js IIFE 暴露到 window）
// authFetch, API_BASE, escapeHtml

let chatOpen = false;
let chatSending = false;
const CHAT_DEBUG = false;

export function initChatWidget() {
    const root = document.getElementById('aiChatRoot');
    if (!root) return;

    root.innerHTML = `
    <button class="chat-fab" id="chatFab"><i class="ri-chat-3-line"></i></button>
    <div class="chat-window" id="chatWindow">
        <div class="chat-header">
            <h4><i class="ri-robot-2-line"></i> AI 助手</h4>
            <button class="chat-close" id="chatCloseBtn">✕</button>
        </div>
        <div class="chat-messages" id="chatMessages"></div>
        <div class="chat-input-bar">
            <textarea class="chat-input" id="chatInput" placeholder="问问 AI 行情怎么样..." rows="1"></textarea>
            <button class="chat-send" id="chatSendBtn">发送</button>
        </div>
    </div>`;

    document.getElementById('chatFab')?.addEventListener('click', toggleChat);
    document.getElementById('chatCloseBtn')?.addEventListener('click', toggleChat);
    document.getElementById('chatSendBtn')?.addEventListener('click', sendChatMessage);

    // Enter 发送，Shift+Enter 换行
    const input = document.getElementById('chatInput');
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    });
    // #60 修复：textarea 自动扩展高度
    input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    });

    // 加载历史
    loadChatHistory();
}

export function toggleChat() {
    chatOpen = !chatOpen;
    const win = document.getElementById('chatWindow');
    const fab = document.getElementById('chatFab');
    if (win) {
        win.classList.toggle('open', chatOpen);
    }
    if (fab) {
        fab.innerHTML = chatOpen ? '✕' : '<i class="ri-chat-3-line"></i>';
    }
    if (chatOpen) {
        scrollChatToBottom();
        document.getElementById('chatInput')?.focus();
    }
}

async function loadChatHistory() {
    try {
        const resp = await authFetch(`${API_BASE}/api/chat/history?limit=30`);
        if (!resp.ok) return;
        const data = await resp.json();

        const container = document.getElementById('chatMessages');
        if (!container) return;

        if (data.messages && data.messages.length > 0) {
            container.innerHTML = data.messages.map(m =>
                `<div class="chat-msg ${m.role}">${escapeHtml(m.content)}</div>`
            ).join('');
            scrollChatToBottom();
        }
    } catch (e) {
        if (CHAT_DEBUG) console.warn('加载聊天历史失败:', e);
    }
}

export async function sendChatMessage() {
    if (chatSending) return;

    const input = document.getElementById('chatInput');
    const btn = document.getElementById('chatSendBtn');
    const messages = document.getElementById('chatMessages');
    const text = input.value.trim();

    if (!text) return;

    // 显示用户消息
    messages.innerHTML += `<div class="chat-msg user">${escapeHtml(text)}</div>`;
    input.value = '';
    scrollChatToBottom();

    // Loading 状态
    chatSending = true;
    btn.disabled = true;
    btn.textContent = '...';

    // AI 占位
    const aiMsgEl = document.createElement('div');
    aiMsgEl.className = 'chat-msg assistant';
    aiMsgEl.textContent = '思考中...';
    messages.appendChild(aiMsgEl);
    scrollChatToBottom();

    try {
        const resp = await authFetch(`${API_BASE}/api/chat/send`, {
            method: 'POST',
            body: JSON.stringify({ message: text }),
        });

        if (!resp.ok) {
            const err = await resp.json();
            aiMsgEl.textContent = `[错误] ${err.detail || '发送失败'}`;
            return;
        }

        const data = await resp.json();
        const reply = data.reply || '(空回复)';

        // 打字机效果
        aiMsgEl.textContent = '';
        await typewriterEffect(aiMsgEl, reply);

    } catch (e) {
        aiMsgEl.textContent = `[网络错误] ${e.message}`;
    } finally {
        chatSending = false;
        btn.disabled = false;
        btn.textContent = '发送';
        scrollChatToBottom();
    }
}

async function typewriterEffect(element, text, speed = 20) {
    for (let i = 0; i < text.length; i++) {
        element.textContent += text[i];
        if (i % 3 === 0) scrollChatToBottom();
        await new Promise(r => setTimeout(r, speed));
    }
    scrollChatToBottom();
}

function scrollChatToBottom() {
    const container = document.getElementById('chatMessages');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

// escapeHtml 已在 auth.js 中全局定义

window.GangziApp = window.GangziApp || {};
Object.assign(window.GangziApp, {
    initChatWidget,
    toggleChat,
    sendChatMessage,
});
