/**
 * 钢子出击 - 认证模块 (ES Module)
 * 处理登录、Token 管理、登录状态检查
 */

const AUTH_TOKEN_KEY = 'gangzi_token';
const AUTH_REFRESH_KEY = 'gangzi_refresh_token';
const AUTH_USER_KEY = 'gangzi_user';
export const API_BASE = window.API_BASE || window.location.origin;
const AUTH_DEBUG = false;


// ============ Token 管理 ============

// #CRITICAL-3 修复：Safari 隐私模式降级到内存存储
const memoryStorage = { token: null, refreshToken: null, username: null };
let localStorageAvailable = true;

// 检测 localStorage 是否可用
function checkLocalStorage() {
    try {
        const test = '__test__';
        localStorage.setItem(test, test);
        localStorage.removeItem(test);
        localStorageAvailable = true;
        return true;
    } catch (e) {
        localStorageAvailable = false;
        console.warn('[Auth] localStorage 不可用，使用内存存储（隐私模式）');
        return false;
    }
}

// 初始化检测
checkLocalStorage();

export function getToken() {
    try {
        if (localStorageAvailable) {
            return localStorage.getItem(AUTH_TOKEN_KEY);
        }
        return memoryStorage.token;
    } catch (e) {
        return memoryStorage.token;
    }
}

export function getRefreshToken() {
    try {
        if (localStorageAvailable) {
            return localStorage.getItem(AUTH_REFRESH_KEY);
        }
        return memoryStorage.refreshToken;
    } catch (e) {
        return memoryStorage.refreshToken;
    }
}

export function setToken(token, username) {
    setTokenPair(token, getRefreshToken(), username);
}

export function setTokenPair(token, refreshToken, username) {
    try {
        if (localStorageAvailable) {
            localStorage.setItem(AUTH_TOKEN_KEY, token);
            if (refreshToken) localStorage.setItem(AUTH_REFRESH_KEY, refreshToken);
            if (username) localStorage.setItem(AUTH_USER_KEY, username);
        } else {
            memoryStorage.token = token;
            memoryStorage.refreshToken = refreshToken;
            memoryStorage.username = username;
            // 显示隐私模式提示
            showToastSafari('隐私模式：登录状态仅在当前会话有效');
        }
    } catch (e) {
        // Safari 隐私模式降级处理
        memoryStorage.token = token;
        memoryStorage.refreshToken = refreshToken;
        memoryStorage.username = username;
        showToastSafari('隐私模式：登录状态仅在当前会话有效');
    }
}

export function clearToken() {
    try {
        if (localStorageAvailable) {
            localStorage.removeItem(AUTH_TOKEN_KEY);
            localStorage.removeItem(AUTH_REFRESH_KEY);
            localStorage.removeItem(AUTH_USER_KEY);
        }
    } catch (e) {
        // 忽略
    }
    memoryStorage.token = null;
    memoryStorage.refreshToken = null;
    memoryStorage.username = null;
}

// Safari 隐私模式下的 Toast 提示（避免循环依赖）
function showToastSafari(message) {
    if (typeof window.showToast === 'function') {
        window.showToast(message);
    } else {
        console.log('[Toast]', message);
    }
}

export function getUsername() {
    try {
        if (localStorageAvailable) {
            return localStorage.getItem(AUTH_USER_KEY) || '';
        }
        return memoryStorage.username || '';
    } catch (e) {
        return memoryStorage.username || '';
    }
}

async function validateTokenOnServer(token) {
    if (!token) return false;
    try {
        const resp = await fetch(`${API_BASE}/api/auth/me`, {
            headers: { 'Authorization': `Bearer ${token}` },
        });
        return resp.ok;
    } catch (e) {
        return false;
    }
}

async function ensureValidSession() {
    const token = getToken();
    if (!token) return false;

    const directValid = await validateTokenOnServer(token);
    if (directValid) return true;

    const refreshed = await tryRefreshToken();
    if (!refreshed) return false;

    const refreshedToken = getToken();
    return validateTokenOnServer(refreshedToken);
}

// ============ #15 全局 HTML 转义 (统一替代三个重复定义) ============
export function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

// ============ API 请求工具 ============

// #HIGH-7 修复：防止多次跳转
let isRedirecting = false;
let redirectTimer = null;

export async function authFetch(url, options = {}) {
    const { _skipRefresh = false, ...requestOptions } = options;
    const token = getToken();
    const headers = {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        ...requestOptions.headers,
    };
    const resp = await fetch(url, { ...requestOptions, headers });
    if (resp.status === 401) {
        if (!_skipRefresh) {
            const refreshed = await tryRefreshToken();
            if (refreshed) {
                return authFetch(url, { ...requestOptions, _skipRefresh: true });
            }
        }

        clearToken();
        // 清理应用状态
        if (window.cleanupApp) {
            window.cleanupApp();
        }
        // 防止多次跳转
        if (!isRedirecting) {
            isRedirecting = true;
            window.location.href = '/login.html';
            // 3秒后重置标志（防止跳转被阻止后无法再次跳转）
            clearTimeout(redirectTimer);
            redirectTimer = setTimeout(() => {
                isRedirecting = false;
            }, 3000);
        }
        throw new Error('Token 过期，请重新登录');
    }
    if (AUTH_DEBUG && (resp.status === 429 || resp.status === 403)) {
        console.debug('[API] status=', resp.status);
    }
    return resp;
}

async function tryRefreshToken() {
    const refreshToken = getRefreshToken();
    if (!refreshToken) return false;

    try {
        const resp = await fetch(`${API_BASE}/api/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!resp.ok) return false;

        const data = await resp.json();
        if (!data.access_token || !data.refresh_token) return false;

        setTokenPair(data.access_token, data.refresh_token, data.username || getUsername());
        return true;
    } catch (e) {
        return false;
    }
}

// ============ 检查登录状态 ============

export async function checkAuth() {
    const token = getToken();
    const isLoginPage = window.location.pathname.includes('login');

    if (!token && !isLoginPage) {
        window.location.href = '/login.html';
        return false;
    }

    if (!token && isLoginPage) {
        return true;
    }

    const validSession = await ensureValidSession();

    if (!validSession) {
        clearToken();
        if (!isLoginPage) {
            window.location.href = '/login.html';
            return false;
        }
        return true;
    }

    if (token && isLoginPage) {
        window.location.href = '/index.html';
        return false;
    }
    return true;
}

// ============ 退出登录 ============

export async function logout() {
    // #44 修复：退出前二次确认
    let confirmed = false;
    if (typeof window.showAppConfirm === 'function') {
        confirmed = await window.showAppConfirm('确定要退出登录吗？');
    } else {
        confirmed = confirm('确定要退出登录吗？');
    }
    if (!confirmed) return;

    // #HIGH-4 修复：清理应用状态
    if (window.cleanupApp) {
        window.cleanupApp();
    }

    try {
        const token = getToken();
        if (token) {
            await fetch(`${API_BASE}/api/auth/logout`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ refresh_token: getRefreshToken() || '' }),
            });
        }
    } catch (_) { }
    clearToken();
    window.location.href = '/login.html';
}

// ============ 登录表单处理（仅在 login.html 生效） ============

document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('loginForm');
    if (!loginForm) return;

    // 如果已登录则跳转
    if (getToken()) {
        checkAuth();
    }

    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value;
        const errorMsg = document.getElementById('errorMsg');
        const loginBtn = document.getElementById('loginBtn');
        const loginCard = document.getElementById('loginCard');
        const btnText = loginBtn.querySelector('.btn-text');
        const btnLoading = loginBtn.querySelector('.btn-loading');

        if (!username || !password) {
            showError('请输入用户名和密码');
            return;
        }

        // 显示 loading
        btnText.style.display = 'none';
        btnLoading.style.display = 'inline';
        loginBtn.classList.add('loading');
        loginBtn.disabled = true; // #P0 修复：禁用按钮防键盘回车重放
        errorMsg.classList.remove('show');

        try {
            const resp = await fetch(`${API_BASE}/api/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });

            let data = {};
            try {
                data = await resp.json();
            } catch (_) {
                // 响应体非 JSON（如 nginx 502/503 错误页）
            }

            if (resp.ok) {
                setTokenPair(data.access_token, data.refresh_token || '', data.username);

                loginCard.classList.add('fly-out');
                setTimeout(() => {
                    window.location.href = '/index.html';
                }, 500);

            } else {
                showError(mapLoginError(resp.status, data));
                loginCard.classList.add('shake');
                setTimeout(() => loginCard.classList.remove('shake'), 500);
            }

        } catch (err) {
            showError('网络连接失败，请检查网络后重试');
            if (AUTH_DEBUG) console.error('登录异常:', err);
        } finally {
            btnText.style.display = 'inline';
            btnLoading.style.display = 'none';
            loginBtn.classList.remove('loading');
            loginBtn.disabled = false; // 恢复按钮
        }
    });

    function showError(msg) {
        const errorMsg = document.getElementById('errorMsg');
        errorMsg.textContent = msg;
        errorMsg.classList.add('show');
    }

    function formatErrorDetail(detail) {
        if (!detail) return '';
        if (typeof detail === 'string') return detail;
        if (Array.isArray(detail)) {
            const first = detail[0] || {};
            // 优先按 type 映射中文，避免直接显示英文 Pydantic 消息
            const typeMap = {
                'string_too_short': '输入长度不足，请检查后重试',
                'string_too_long': '输入长度超限，请缩短后重试',
                'value_error': '输入值无效',
                'missing': '缺少必填字段',
                'json_invalid': '请求格式错误',
            };
            if (first.type && typeMap[first.type]) return typeMap[first.type];
            // 对未知 type，尝试翻译常见英文 msg
            if (first.msg && /^String should have at least/i.test(first.msg)) {
                const m = first.msg.match(/at least (\d+)/);
                return m ? `至少需要输入 ${m[1]} 个字符` : '输入长度不足';
            }
            if (first.msg && /^String should have at most/i.test(first.msg)) {
                const m = first.msg.match(/at most (\d+)/);
                return m ? `最多允许输入 ${m[1]} 个字符` : '输入长度超限';
            }
            if (first.msg) return first.msg;
            return '输入格式不正确';
        }
        return String(detail);
    }

    // 按 HTTP 状态码映射登录错误，给用户明确可操作的提示
    function mapLoginError(status, data) {
        if (status === 401) {
            return '用户名或密码错误，请检查后重试';
        }
        if (status === 429) {
            const remaining = parseRemainingSeconds(data);
            if (remaining > 0) {
                return `操作过于频繁，请 ${remaining} 秒后重试`;
            }
            return '操作过于频繁，请稍后重试';
        }
        if (status >= 500) {
            return '服务暂时不可用，请稍后重试';
        }
        // 其他状态码走原有解析逻辑
        return formatErrorDetail(data.detail) || data.message || '登录失败';
    }

    // 从后端统一错误壳解析剩余等待秒数
    function parseRemainingSeconds(data) {
        // detail 为对象且含 remaining_seconds
        if (data.detail && typeof data.detail === 'object' && !Array.isArray(data.detail)) {
            const sec = data.detail.remaining_seconds;
            if (typeof sec === 'number' && sec > 0) return Math.ceil(sec);
        }
        // detail 字符串中提取秒数
        if (typeof data.detail === 'string') {
            const m = data.detail.match(/(\d+)\s*秒/);
            if (m) return parseInt(m[1], 10);
        }
        // message 字符串中提取秒数（兼容中英文）
        if (typeof data.message === 'string') {
            const m = data.message.match(/(\d+)\s*(?:秒|seconds?)/i);
            if (m) return parseInt(m[1], 10);
        }
        return 0;
    }
});

// ============ 全局兼容层（供非模块脚本访问） ============
window.GangziApp = window.GangziApp || {};
Object.assign(window.GangziApp, {
    API_BASE,
    getToken,
    getRefreshToken,
    setToken,
    setTokenPair,
    clearToken,
    getUsername,
    escapeHtml,
    authFetch,
    checkAuth,
    logout,
});

// 兼容旧调用（逐步迁移）
window.API_BASE = API_BASE;
window.getToken = getToken;
window.getRefreshToken = getRefreshToken;
window.authFetch = authFetch;
window.escapeHtml = escapeHtml;
window.checkAuth = checkAuth;
window.logout = logout;
