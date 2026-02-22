/**
 * 钢子出击 - AI 辩论面板
 * 5 角色并排卡片 + 综合裁决
 */

// 全局依赖（由 auth.js IIFE 暴露到 window）
// authFetch, API_BASE, escapeHtml

const DEBATE_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT'];
let currentDebateSymbol = 'BTCUSDT';
const DEBATE_DEBUG = false;
const FEED_LIMIT = 50;
let _feedPage = 1;
let _feedLoading = false;
let _feedHasNext = true;
let _feedFirstLoaded = false;

function ensureAnalysisFeedStyles() {
    if (document.getElementById('aiAnalysisFeedStyles')) return;
    const el = document.createElement('style');
    el.id = 'aiAnalysisFeedStyles';
    el.textContent = `
      .ai-feed-head{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
      .ai-feed-actions{display:flex;gap:8px;flex-wrap:wrap}
      .ai-feed-meta{font-size:12px;color:var(--text3)}
      .ai-feed-list{display:flex;flex-direction:column;gap:24px}
      .ai-feed-item{border:1px solid var(--border);background:var(--bg2);border-radius:14px;padding:12px}
      .ai-feed-summary{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
      .ai-feed-right{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end}
      .ai-feed-left{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
      .ai-feed-tag{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:800;border:1px solid rgba(148,163,184,.25)}
      .ai-feed-tag.buy{background:rgba(34,197,94,.10);border-color:rgba(34,197,94,.25);color:var(--green)}
      .ai-feed-tag.sell{background:rgba(239,68,68,.10);border-color:rgba(239,68,68,.25);color:var(--red)}
      .ai-feed-tag.short{background:rgba(239,68,68,.10);border-color:rgba(239,68,68,.25);color:var(--red)}
      .ai-feed-tag.cover{background:rgba(34,197,94,.10);border-color:rgba(34,197,94,.25);color:var(--green)}
      .ai-feed-tag.hold{background:rgba(148,163,184,.10);border-color:rgba(148,163,184,.22);color:var(--text3)}
      .ai-feed-kpi{font-size:12px;color:var(--text3);display:flex;gap:10px;flex-wrap:wrap}
      .ai-feed-kpi b{color:var(--text);font-variant-numeric:tabular-nums}
      .ai-feed-details{margin-top:10px}
      .ai-feed-details summary{cursor:pointer;font-weight:800;color:var(--text)}
      .ai-feed-block{margin-top:10px;border:1px solid var(--border);border-radius:12px;background:rgba(0,0,0,.12);padding:10px}
      .ai-feed-block-title{font-size:12px;font-weight:800;color:var(--text3);margin-bottom:8px}
      .ai-feed-pre{margin:0;font-size:13px;line-height:1.6;white-space:pre-wrap;word-break:break-word;color:var(--text)}
      .ai-role-grid{display:grid;grid-template-columns:repeat(5, minmax(0, 1fr));gap:10px}
      @media (max-width: 1100px){ .ai-role-grid{grid-template-columns:repeat(2, minmax(0, 1fr));} }
      @media (max-width: 520px){ .ai-role-grid{grid-template-columns:1fr;} }
      .ai-role-mini{border:1px solid var(--border);border-radius:12px;background:rgba(255,255,255,.04);padding:10px}
      .ai-role-mini .t{display:flex;align-items:center;justify-content:space-between;gap:10px}
      .ai-role-mini .n{font-weight:900}
      .ai-role-mini .s{font-size:12px;color:var(--text3)}
      .ai-role-mini .a{margin-top:8px;font-size:13px;line-height:1.55;white-space:pre-wrap;word-break:break-word}
      .ai-feed-loadmore{width:100%;margin-top:10px}
      .ai-trade-badge{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700;line-height:1.4;white-space:nowrap}
      .ai-trade-badge.filled{background:rgba(34,197,94,.15);color:#16a34a;border:1px solid rgba(34,197,94,.35)}
      .ai-trade-badge.skipped{background:rgba(100,116,139,.12);color:#475569;border:1px solid rgba(100,116,139,.25)}
      .ai-trade-badge.failed{background:rgba(239,68,68,.12);color:#dc2626;border:1px solid rgba(239,68,68,.3)}
      .ai-trade-badge.no-record{background:rgba(100,116,139,.08);color:#64748b;border:1px solid rgba(100,116,139,.2)}
      .ai-trade-badge .reason{font-weight:500;margin-left:2px}
      .ai-feed-deep-btn{display:inline-flex;align-items:center;gap:4px;margin-top:6px;padding:4px 12px;font-size:12px;font-weight:700;border-radius:8px;border:1px solid var(--border);background:transparent;color:var(--text2,#888);cursor:pointer;transition:background .15s,color .15s}
      .ai-feed-deep-btn:hover{background:var(--blue,#3b82f6);color:#fff;border-color:var(--blue,#3b82f6)}
      body.light-theme .ai-feed-item{background:rgba(0,0,0,0.04);border-color:rgba(0,0,0,0.10)}
      body.light-theme .ai-feed-item:hover{background:rgba(0,0,0,0.06)}
      body.light-theme .ai-feed-kpi b{color:#1a1a1a}
      body.light-theme .ai-feed-block{background:rgba(0,0,0,0.04);border-color:rgba(0,0,0,0.08)}
      body.light-theme .ai-feed-pre{color:#222}
      body.light-theme .ai-feed-details summary{color:#1a1a1a}
      body.light-theme .ai-role-mini{background:rgba(0,0,0,0.03);border-color:rgba(0,0,0,0.08)}
      body.light-theme .vote-chip{background:rgba(255,255,255,0.9)}
      body.light-theme .vote-chip-name{color:#333}
      body.light-theme .vote-summary-bar{background:rgba(0,0,0,0.05);border:1px solid rgba(0,0,0,0.10)}
      body.light-theme .vote-chip{background:rgba(255,255,255,0.85);border-color:rgba(0,0,0,0.12)}
      /* vote-chip-sig 颜色由内联 style 控制，亮色下不覆盖 */
      body.light-theme .ai-trade-badge.filled{background:rgba(34,197,94,0.10);color:#15803d}
      body.light-theme .ai-trade-badge.skipped{background:rgba(100,116,139,0.08);color:#334155}
      body.light-theme .ai-trade-badge.failed{background:rgba(239,68,68,0.08);color:#b91c1c}
      body.light-theme .ai-trade-badge.no-record{background:rgba(100,116,139,0.06);color:#475569}
      body.light-theme .ai-feed-tag.hold{color:#64748b;background:rgba(100,116,139,0.08)}
    `;
    document.head.appendChild(el);
}

export function initDebatePanel() {
    const panel = document.getElementById('aiDebatePanel');
    if (!panel) return;

    ensureAnalysisFeedStyles();
    panel.innerHTML = `
    <div class="debate-header">
        <h2 class="debate-title"><i class="ri-robot-2-line"></i> AI 五人辩论会</h2>
        <div class="debate-controls">
            <select class="symbol-select" id="debateSymbolSelect">
                ${DEBATE_SYMBOLS.map(s => `<option value="${s}" ${s === currentDebateSymbol ? 'selected' : ''}>${s.replace('USDT', '/USDT')}</option>`).join('')}
            </select>
            <button class="debate-btn" id="debateStartBtn">
                开始辩论分析
            </button>
        </div>
    </div>
    <div id="debateContent">
        <div class="no-data">选择币种后点击"开始辩论分析"</div>
    </div>

    <div class="card mb" style="margin-top:16px">
      <div class="card-head ai-feed-head">
        <h3><i class="ri-file-list-3-line"></i> 分析流水（全量，不过滤）</h3>
        <div class="ai-feed-actions">
          <button type="button" class="header-btn" id="aiFeedRefreshBtn"><i class="ri-refresh-line"></i> 刷新</button>
          <button type="button" class="header-btn" id="aiFeedToTopBtn"><i class="ri-arrow-up-line"></i> 回到顶部</button>
        </div>
      </div>
      <div class="card-body compact">
        <div class="ai-feed-meta" id="aiFeedMeta">加载中...</div>
        <div class="ai-feed-list" id="aiAnalysisFeedList">
          <div class="skeleton skeleton-line"></div>
          <div class="skeleton skeleton-line"></div>
          <div class="skeleton skeleton-line"></div>
        </div>
        <button type="button" class="header-btn ai-feed-loadmore" id="aiFeedLoadMoreBtn" style="display:none">
          加载更多
        </button>
      </div>
    </div>`;

    document.getElementById('debateSymbolSelect').addEventListener('change', (e) => {
        currentDebateSymbol = e.target.value;
        loadDebateData(currentDebateSymbol);
    });
    document.getElementById('debateStartBtn')?.addEventListener('click', startDebate);

    // 自动加载已有辩论
    loadDebateData(currentDebateSymbol);

    // 分析流水
    document.getElementById('aiFeedRefreshBtn')?.addEventListener('click', () => loadAnalysisFeed(true));
    document.getElementById('aiFeedToTopBtn')?.addEventListener('click', () => {
        try { window.scrollTo({ top: 0, behavior: 'smooth' }); } catch(_) { window.scrollTo(0, 0); }
    });
    document.getElementById('aiFeedLoadMoreBtn')?.addEventListener('click', () => loadAnalysisFeed(false));
    loadAnalysisFeed(true);

    // WS 新信号：只会推送 BUY/SELL/SHORT/COVER（后端对 HOLD 不推送）
    window.addEventListener('ws-signal', (ev) => {
        try {
            const sig = ev.detail || null;
            if (!sig || !sig.id) return;
            if (!_feedFirstLoaded) return;
            prependFeedItems([sig]);
        } catch (_) {}
    });

    // WS 交易状态：实时更新 feed item 的成交/跳过标签
    window.addEventListener('ws-trade-status', (ev) => {
        try {
            const d = ev.detail || {};
            if (!d.signal_id) return;
            _updateFeedItemTradeStatus(d.signal_id, d.status, d.error_msg || '');
        } catch (_) {}
    });
}

export async function loadDebateData(symbol) {
    const content = document.getElementById('debateContent');
    if (!content) return;

    try {
        const resp = await authFetch(`${API_BASE}/api/ai/debate/${symbol}`);
        if (!resp.ok) return;
        const data = await resp.json();

        if (!data.debate) {
            content.innerHTML = '<div class="no-data">暂无辩论数据，点击"开始辩论分析"</div>';
            return;
        }

        renderDebate(content, data.debate);
    } catch (e) {
        if (DEBATE_DEBUG) console.warn('加载辩论失败:', e);
    }
}

let _debateInProgress = false;
export async function startDebate() {
    const btn = document.getElementById('debateStartBtn');
    const content = document.getElementById('debateContent');
    if (!btn || !content) return;
    // #62 修复：双击防抖 — 先 disable，请求完再恢复
    if (_debateInProgress) return;
    _debateInProgress = true;

    btn.textContent = '分析中...';
    btn.classList.add('loading');
    btn.disabled = true;
    content.innerHTML = '<div class="no-data no-data-pad-lg"><i class="ri-refresh-line"></i> 5 位 AI 分析师正在并发分析，请稍候（约 15-30 秒）...</div>';

    try {
        const resp = await authFetch(`${API_BASE}/api/ai/analyze-now`, {
            method: 'POST',
            body: JSON.stringify({ symbol: currentDebateSymbol }),
        });

        if (!resp.ok) {
            let errMsg = '未知错误';
            try { const err = await resp.json(); errMsg = err.detail || errMsg; } catch(_) {}
            // #16 修复：err.detail 需转义防 XSS
            content.innerHTML = `<div class="no-data text-error">分析失败: ${escapeHtml(errMsg)}</div>`;
            return;
        }

        const data = await resp.json();
        if (data.signal) {
            renderDebate(content, data.signal);
            // 同时更新信号卡片
            (window.GangziApp?.loadLatestSignal || function(){})();
            (window.GangziApp?.loadRecentSignals || function(){})();
        }

    } catch (e) {
        content.innerHTML = `<div class="no-data text-error">网络错误: ${escapeHtml(e.message)}</div>`;
    } finally {
        btn.textContent = '开始辩论分析';
        btn.classList.remove('loading');
        btn.disabled = false;
        _debateInProgress = false;
    }
}

// #51 修复：使用全局 escapeHtml（定义在 auth.js）
const escapeDebateHtml = escapeHtml;

export function renderDebate(container, debate) {
    // #3 修复：统一 role_opinions 类型判断
    let opinions = debate.role_opinions || [];
    if (typeof opinions === 'string') { try { opinions = JSON.parse(opinions); } catch(_) { opinions = []; } }
    if (!Array.isArray(opinions)) opinions = [];
    const sig = String(debate.signal || 'HOLD').toUpperCase();
    // 兼容 SHORT/COVER，避免渲染出 "undefined"
    const sigCn = { BUY: '开多', SELL: '平多', SHORT: '开空', COVER: '平空', HOLD: '观望' }[sig] || '观望';

    // #LOW-18 修复：安全截断文本（考虑多字节字符）
    function safeTruncate(str, maxLength) {
        if (!str) return '';
        // 使用 Array.from 正确处理多字节字符
        const chars = Array.from(str);
        if (chars.length <= maxLength) return str;
        return chars.slice(0, maxLength).join('') + '...';
    }

    let rolesHtml = opinions.map(role => {
        const roleSigRaw = String(role.signal || 'HOLD').toUpperCase();
        const roleSig = roleSigRaw.toLowerCase();
        const roleSigCn = { BUY: '开多', SELL: '平多', SHORT: '开空', COVER: '平空', HOLD: '观望' }[roleSigRaw] || '观望';
        const preview = escapeDebateHtml(safeTruncate(role.analysis, 80));
        const full = escapeDebateHtml(role.analysis || '');
        // 冲突高亮：角色信号与最终裁决不同
        const isConflict = roleSigRaw !== sig;
        const conflictClass = isConflict ? 'conflict' : 'agree';

        const modelLabel = escapeDebateHtml(role.model_label || '');
        return `<div class="role-card ${conflictClass}" data-role-color="${escapeDebateHtml(role.color || 'var(--blue)')}" role="button" tabindex="0" onclick="this.classList.toggle('expanded')" onkeydown="if(event.key === 'Enter' || event.key === ' ') { event.preventDefault(); this.classList.toggle('expanded'); }">
            <div class="role-avatar">${role.emoji || '<i class="ri-robot-2-line"></i>'}</div>
            <div class="role-name">${escapeDebateHtml(role.name || '分析师')}</div>
            <div class="role-title">${escapeDebateHtml(role.title || '')}</div>
            ${modelLabel ? `<div class="role-model"><i class="ri-cpu-line"></i> ${modelLabel}</div>` : ''}
            <div class="role-signal ${roleSig}">${roleSigCn}</div>
            <div class="role-confidence">置信度: <span>${role.confidence || 0}%</span></div>
            <div class="role-analysis-preview">${preview}</div>
            <div class="role-full-analysis">${full}</div>
        </div>`;
    }).join('');

    // #69 修复：转义裁决理由和每日一句
    const safeReason = escapeDebateHtml(debate.final_reason || debate.reason || '暂无裁决理由');
    const safeQuote = debate.daily_quote ? escapeDebateHtml(debate.daily_quote) : '';

    // 风险评估描述
    const riskAssessment = debate.risk_assessment ? escapeDebateHtml(debate.risk_assessment) : '暂无风险评估数据';

    container.innerHTML = `
    <div class="debate-roles">${rolesHtml}</div>
    <div class="debate-verdict">
        <div class="verdict-title">
            <i class="ri-scales-3-line"></i> 综合裁决:
            <span class="verdict-signal ${sig === 'BUY' ? 'buy' : sig === 'SELL' ? 'sell' : 'hold'}">
                ${sigCn}
            </span>
            <span class="verdict-confidence">置信度 ${debate.confidence || 0}%</span>
        </div>
        <div class="verdict-reason">${safeReason}</div>
        ${safeQuote ? `<div class="quote-block">「${safeQuote}」</div>` : ''}

        <!-- 风险评估 -->
        <div class="debate-risk-assessment">
            <div class="risk-assessment-title"><i class="ri-shield-check-line"></i> 风险评估</div>
            <div class="risk-assessment-content">${riskAssessment}</div>
        </div>

        <!-- 免责声明 -->
        <div class="debate-disclaimer">
            <div class="disclaimer-icon"><i class="ri-error-warning-line"></i></div>
            <div class="disclaimer-text">
                <strong>免责声明：</strong>本分析仅供参考，不构成投资建议。加密货币投资有风险，入市需谨慎。
            </div>
        </div>
    </div>`;

    container.querySelectorAll('.role-card[data-role-color]').forEach((el) => {
        el.style.setProperty('--role-color', el.dataset.roleColor || 'var(--blue)');
    });
}

window.GangziApp = window.GangziApp || {};
Object.assign(window.GangziApp, {
    initDebatePanel,
    startDebate,
});

/**
 * 按价格量级智能格式化，带 $ 前缀与千分位
 * >=1000 无小数; >=10 2位; >=1 2位; >=0.01 4位; <0.01 6位
 */
function _fmtPrice(value) {
    const n = Number(value);
    if (!isFinite(n)) return '$0.00';
    const abs = Math.abs(n);
    let s, dp;
    if (abs >= 1000) { dp = 0; }
    else if (abs >= 10) { dp = 2; }
    else if (abs >= 1) { dp = 2; }
    else if (abs >= 0.01) { dp = 4; }
    else { dp = 6; }
    s = n.toFixed(dp);
    if (dp === 0 && abs >= 1000) {
        s = n.toLocaleString('en-US', { maximumFractionDigits: 0, minimumFractionDigits: 0 });
    } else if (dp > 0 && abs >= 1000) {
        const intPart = Math.floor(abs);
        const decPart = (abs - intPart).toFixed(dp).slice(1);
        s = (n < 0 ? '-' : '') + intPart.toLocaleString('en-US') + decPart;
    }
    return '$' + s;
}

function _fmtTime(iso) {
    const s = String(iso || '');
    if (!s) return '--';
    const d = new Date(s);
    if (isNaN(d.getTime())) return s.replace('T', ' ').replace('Z', '');
    return d.toLocaleString('zh-CN', { hour12: false });
}

function _sigClass(sig) {
    const v = String(sig || '').toUpperCase();
    if (v === 'BUY') return 'buy';
    if (v === 'SELL') return 'sell';
    if (v === 'SHORT') return 'short';
    if (v === 'COVER') return 'cover';
    return 'hold';
}

function _sigCn(sig) {
    const v = String(sig || '').toUpperCase();
    return { BUY: '开多', SELL: '平多', SHORT: '开空', COVER: '平空', HOLD: '观望' }[v] || v || '观望';
}

function _safeJson(obj) {
    try { return JSON.stringify(obj, null, 2); } catch { return ''; }
}

function _renderFeedItem(item) {
    const symbol = escapeDebateHtml(item.symbol || '--');
    const sig = String(item.signal || 'HOLD').toUpperCase();
    const sigCls = _sigClass(sig);
    const sigText = _sigCn(sig);
    const conf = Number(item.confidence || 0);
    const px = Number(item.price_at_signal || 0);
    const riskLevel = escapeDebateHtml(item.risk_level || '');
    const createdAt = _fmtTime(item.created_at);

    // 成交状态标签
    let tradeBadgeHtml = '';
    const ts = item.trade_status;
    if (ts === 'filled' || ts === 'skipped' || ts === 'failed') {
        tradeBadgeHtml = _buildTradeBadgeHtml(ts, item.trade_skip_reason || '');
    } else if (ts === 'no_record') {
        const _skipR = escapeDebateHtml(item.trade_skip_reason || '');
        tradeBadgeHtml = '<span class="ai-trade-badge no-record"><i class="ri-subtract-line"></i>未执行' + (_skipR ? '<span class="reason"> · ' + _skipR + '</span>' : '') + '</span>';
    }

    // 角色观点
    let roles = item.role_opinions || [];
    if (typeof roles === 'string') { try { roles = JSON.parse(roles); } catch(_) { roles = []; } }
    if (!Array.isArray(roles)) roles = [];

    const roleGrid = roles.length ? `
      <div class="ai-role-grid">
        ${roles.map((r) => {
            const name = escapeDebateHtml(r.name || '分析师');
            const emoji = r.emoji || '<i class="ri-robot-2-line"></i>';
            const rs = _sigCn(r.signal || 'HOLD');
            const rc = Number(r.confidence || 0);
            const ml = escapeDebateHtml(r.model_label || '');
            const analysis = escapeDebateHtml(String(r.analysis || ''));
            return `
              <div class="ai-role-mini">
                <div class="t">
                  <div class="n">${emoji} ${name}${ml ? ` <span style="font-size:10px;color:var(--text3);font-weight:400">(${ml})</span>` : ''}</div>
                  <div class="s">${escapeDebateHtml(rs)} / ${rc}%</div>
                </div>
                <div class="a">${analysis || '--'}</div>
              </div>
            `;
        }).join('')}
      </div>
    ` : '<div class="no-data">暂无角色观点</div>';

    const finalReason = escapeDebateHtml(item.final_reason || '');
    const riskAssessment = escapeDebateHtml(item.risk_assessment || '');
    const debateLog = escapeDebateHtml(item.debate_log || '');
    const dailyQuote = escapeDebateHtml(item.daily_quote || '');
    const voiceText = escapeDebateHtml(item.voice_text || '');

    // pre-filter shadow 字段原样展示（不解释、不判断）
    const pf = {
        pf_direction: item.pf_direction ?? null,
        pf_score: item.pf_score ?? null,
        pf_level: item.pf_level ?? null,
        pf_reasons: item.pf_reasons ?? null,
        pf_agreed_with_ai: item.pf_agreed_with_ai ?? null,
    };

    return `
      <div class="ai-feed-item" data-signal-id="${escapeDebateHtml(String(item.id || ''))}" data-symbol="${symbol}">
        <div class="ai-feed-summary">
          <div class="ai-feed-left">
            <span class="ai-feed-tag ${sigCls}">${escapeDebateHtml(sigText)}</span>
            ${tradeBadgeHtml}
            <div style="font-weight:900">${symbol}</div>
            <div class="ai-feed-kpi">
              <span>置信度 <b>${isFinite(conf) ? conf : 0}%</b></span>
              <span>价格 <b>${_fmtPrice(px)}</b></span>
              ${riskLevel ? `<span>风险 <b>${riskLevel}</b></span>` : ''}
            </div>
          </div>
          <div class="ai-feed-right">
            <div class="ai-feed-meta">${escapeDebateHtml(createdAt)}</div>
            <button type="button" class="ai-feed-deep-btn" onclick="openDeepDebateFromFeed(this)">
              <i class="ri-search-eye-line"></i> 深度研判
            </button>
          </div>
        </div>

        ${roles.length ? `<div class="vote-summary-bar">${roles.map(r => {
          const vSig = String(r.signal || 'HOLD').toUpperCase();
          const vColors = { BUY: 'var(--green)', SELL: 'var(--red)', SHORT: 'var(--red)', COVER: 'var(--green)', HOLD: 'var(--text3)' };
          return `<span class="vote-chip" style="border-color:${vColors[vSig] || 'var(--text3)'}">
            <span class="vote-chip-name">${escapeDebateHtml(r.name || '?')}</span>
            <span class="vote-chip-sig" style="color:${vColors[vSig] || 'var(--text3)'}">${vSig} ${r.confidence || 0}%</span>
          </span>`;
        }).join('')}</div>` : ''}

        <details class="ai-feed-details">
          <summary>展开全部信息（不做过滤）</summary>

          <div class="ai-feed-block">
            <div class="ai-feed-block-title">综合裁决理由</div>
            <pre class="ai-feed-pre">${finalReason || '--'}</pre>
          </div>

          <div class="ai-feed-block">
            <div class="ai-feed-block-title">风险评估</div>
            <pre class="ai-feed-pre">${riskAssessment || '--'}</pre>
          </div>

          <div class="ai-feed-block">
            <div class="ai-feed-block-title">五角色观点（全文）</div>
            ${roleGrid}
          </div>

          <div class="ai-feed-block">
            <div class="ai-feed-block-title">辩论过程（debate_log）</div>
            <pre class="ai-feed-pre">${debateLog || '--'}</pre>
          </div>

          ${(dailyQuote || voiceText) ? `
            <div class="ai-feed-block">
              <div class="ai-feed-block-title">附加文本</div>
              <pre class="ai-feed-pre">${(dailyQuote ? `daily_quote: ${dailyQuote}\n` : '') + (voiceText ? `voice_text: ${voiceText}` : '')}</pre>
            </div>
          ` : ''}

          <div class="ai-feed-block">
            <div class="ai-feed-block-title">pre-filter 字段（影子模式）</div>
            <pre class="ai-feed-pre">${escapeDebateHtml(_safeJson(pf)) || '--'}</pre>
          </div>
        </details>
      </div>
    `;
}

function openDeepDebateFromFeed(btn) {
    try {
        const item = btn?.closest?.('.ai-feed-item');
        const symbol = item?.dataset?.symbol || '';
        if (!symbol) return;
        const sel = document.getElementById('debateSymbolSelect');
        if (sel) {
            sel.value = symbol;
            sel.dispatchEvent(new Event('change'));
        }
        const tab = document.querySelector('[data-tab="ai-analysis"]');
        if (tab) tab.click();
        setTimeout(() => {
            const startBtn = document.getElementById('debateStartBtn');
            if (startBtn) startBtn.click();
        }, 250);
    } catch (_) {}
}
// HTML onclick 需要全局访问
window.openDeepDebateFromFeed = openDeepDebateFromFeed;

function _dedupeAndPrepend(existingRoot, items) {
    if (!existingRoot) return;
    const existingIds = new Set(Array.from(existingRoot.querySelectorAll('[data-signal-id]')).map((el) => el.getAttribute('data-signal-id')));
    const html = items
        .filter((it) => it && String(it.id || '') && !existingIds.has(String(it.id)))
        .map(_renderFeedItem)
        .join('');
    if (html) {
        existingRoot.insertAdjacentHTML('afterbegin', html);
    }
}

function prependFeedItems(items) {
    const listEl = document.getElementById('aiAnalysisFeedList');
    if (!listEl) return;
    _dedupeAndPrepend(listEl, items || []);
}

function _buildTradeBadgeHtml(status, reason) {
    const r = escapeDebateHtml(reason || '');
    if (status === 'filled') {
        return '<span class="ai-trade-badge filled"><i class="ri-checkbox-circle-fill"></i>已成交</span>';
    } else if (status === 'skipped') {
        return `<span class="ai-trade-badge skipped"><i class="ri-skip-forward-fill"></i>未执行${r ? `<span class="reason">· ${r}</span>` : ''}</span>`;
    } else if (status === 'failed') {
        return `<span class="ai-trade-badge failed"><i class="ri-error-warning-fill"></i>失败${r ? `<span class="reason">· ${r}</span>` : ''}</span>`;
    }
    return '';
}

function _updateFeedItemTradeStatus(signalId, status, errorMsg) {
    const el = document.querySelector(`.ai-feed-item[data-signal-id="${signalId}"]`);
    if (!el) return;
    const old = el.querySelector('.ai-trade-badge');
    const html = _buildTradeBadgeHtml(status, errorMsg);
    if (!html) return;
    if (old) {
        old.outerHTML = html;
    } else {
        const tag = el.querySelector('.ai-feed-tag');
        if (tag) tag.insertAdjacentHTML('afterend', html);
    }
}

export async function loadAnalysisFeed(reset) {
    if (_feedLoading) return;
    const listEl = document.getElementById('aiAnalysisFeedList');
    const metaEl = document.getElementById('aiFeedMeta');
    const moreBtn = document.getElementById('aiFeedLoadMoreBtn');
    if (!listEl || !metaEl || !moreBtn) return;

    _feedLoading = true;
    try {
        if (reset) {
            _feedPage = 1;
            _feedHasNext = true;
            listEl.innerHTML = '<div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div>';
            moreBtn.style.display = 'none';
        }

        const url = `${API_BASE}/api/ai/history-all?page=${_feedPage}&limit=${FEED_LIMIT}`;
        const resp = await authFetch(url);
        if (!resp.ok) {
            listEl.innerHTML = '<div class="no-data text-error">加载失败：接口不可用</div>';
            metaEl.textContent = '加载失败';
            return;
        }
        const payload = await resp.json();
        const data = payload.data || payload;
        const history = Array.isArray(data.history) ? data.history : [];
        const pg = data.pagination || {};
        _feedHasNext = !!pg.has_next;

        if (reset) {
            if (!history.length) {
                listEl.innerHTML = '<div class="no-data">暂无分析记录</div>';
            } else {
                listEl.innerHTML = history.map(_renderFeedItem).join('');
            }
            _feedFirstLoaded = true;
        } else {
            // append
            const html = history.map(_renderFeedItem).join('');
            listEl.insertAdjacentHTML('beforeend', html);
        }

        const lastAt = data.last_analysis_at ? _fmtTime(data.last_analysis_at) : '--';
        const total = Number(pg.total || 0);
        metaEl.textContent = `最近分析时间：${lastAt} ｜ 共 ${total} 条（包含 HOLD）`;

        moreBtn.style.display = _feedHasNext ? '' : 'none';
        if (_feedHasNext) _feedPage += 1;
    } catch (e) {
        listEl.innerHTML = `<div class="no-data text-error">网络错误: ${escapeDebateHtml(e.message)}</div>`;
        metaEl.textContent = '网络错误';
    } finally {
        _feedLoading = false;
    }
}


// ============================================================
// initAnalysisFeed — 在首页 #tradingFeedSlot 中渲染分析流水
// ============================================================
let _homeFeedPage = 1;
let _homeFeedLoading = false;
let _homeFeedHasNext = true;
let _homeFeedFilter = 'all'; // all | trade | hold
let _homeFeedAutoTimer = null;
let _homeFeedLatestId = 0;

export function initAnalysisFeed() {
    const slot = document.getElementById('tradingFeedSlot');
    if (!slot) return;

    slot.innerHTML = `
    <div class="card mb">
      <div class="card-head" style="flex-wrap:wrap;gap:8px;">
        <h3 style="display:flex;align-items:center;gap:8px;">
          <i class="ri-discuss-line"></i> 六人讨论决策信号
          <span class="status-pill is-online" style="font-size:11.5px;height:32px;box-sizing:border-box;"><span class="dot"></span>实时监控中</span>
        </h3>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
          <button type="button" class="header-btn home-feed-filter active" data-filter="all">全部</button>
          <button type="button" class="header-btn home-feed-filter" data-filter="trade">交易信号</button>
          <button type="button" class="header-btn home-feed-filter" data-filter="hold">观望信号</button>
          <button type="button" class="header-btn" id="homeFeedRefreshBtn"><i class="ri-refresh-line"></i> 刷新</button>
          <button type="button" class="header-btn" id="homeFeedToTopBtn"><i class="ri-arrow-up-line"></i> 回到顶部</button>
        </div>
      </div>
      <div class="card-body compact">
        <div class="ai-feed-meta" id="homeFeedMeta">加载中...</div>
        <div class="ai-feed-list" id="homeFeedList">
          <div class="skeleton skeleton-line"></div>
          <div class="skeleton skeleton-line"></div>
          <div class="skeleton skeleton-line"></div>
        </div>
        <button type="button" class="header-btn ai-feed-loadmore" id="homeFeedLoadMoreBtn" style="display:none">
          加载更多
        </button>
      </div>
    </div>`;

    // 过滤按钮
    slot.querySelectorAll('.home-feed-filter').forEach(btn => {
        btn.addEventListener('click', () => {
            slot.querySelectorAll('.home-feed-filter').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            _homeFeedFilter = btn.dataset.filter;
            _loadHomeFeed(true);
        });
    });

    document.getElementById('homeFeedRefreshBtn')?.addEventListener('click', () => _loadHomeFeed(true));
    document.getElementById('homeFeedToTopBtn')?.addEventListener('click', () => {
        try { window.scrollTo({ top: 0, behavior: 'smooth' }); } catch(_) { window.scrollTo(0, 0); }
    });
    document.getElementById('homeFeedLoadMoreBtn')?.addEventListener('click', () => _loadHomeFeed(false));

    _loadHomeFeed(true);

    // 自动轮询：每 15 秒检查新数据
    if (_homeFeedAutoTimer) clearInterval(_homeFeedAutoTimer);
    _homeFeedAutoTimer = setInterval(() => _autoRefreshHomeFeed(), 15000);
}

// 自动刷新：只检查是否有新记录，有则平滑追加到顶部
async function _autoRefreshHomeFeed() {
    if (document.hidden) return;
    if (_homeFeedLoading) return;
    const listEl = document.getElementById('homeFeedList');
    const metaEl = document.getElementById('homeFeedMeta');
    if (!listEl || !metaEl) return;

    try {
        const url = `${API_BASE}/api/ai/history-all?page=1&limit=20`;
        const resp = await authFetch(url);
        if (!resp.ok) return;
        const payload = await resp.json();
        const data = payload.data || payload;
        const history = Array.isArray(data.history) ? data.history : [];
        if (!history.length) return;

        // 找到比当前最新 ID 更新的记录
        const newItems = _homeFeedLatestId > 0
            ? history.filter(it => Number(it.id || 0) > _homeFeedLatestId)
            : [];

        if (_homeFeedLatestId === 0) {
            // 首次：记录最新 ID，不做 DOM 更新（初始加载已处理）
            _homeFeedLatestId = Math.max(...history.map(it => Number(it.id || 0)));
            return;
        }

        if (!newItems.length) return;

        // 更新最新 ID
        _homeFeedLatestId = Math.max(...newItems.map(it => Number(it.id || 0)), _homeFeedLatestId);

        // 按 filter 过滤
        let filtered = newItems;
        if (_homeFeedFilter === 'trade') {
            filtered = newItems.filter(it => {
                const s = String(it.signal || '').toUpperCase();
                return s === 'BUY' || s === 'SELL' || s === 'SHORT' || s === 'COVER';
            });
        } else if (_homeFeedFilter === 'hold') {
            filtered = newItems.filter(it => String(it.signal || '').toUpperCase() === 'HOLD');
        }

        if (!filtered.length) return;

        // 平滑插入到顶部（带动画）
        const noDataEl = listEl.querySelector('.no-data');
        if (noDataEl) noDataEl.remove();

        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = filtered.map(_renderFeedItem).join('');
        const newNodes = Array.from(tempDiv.children);

        newNodes.reverse().forEach(node => {
            node.style.opacity = '0';
            node.style.transform = 'translateY(-10px)';
            node.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            listEl.insertBefore(node, listEl.firstChild);
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    node.style.opacity = '1';
                    node.style.transform = 'translateY(0)';
                });
            });
        });

        // 更新 meta
        const lastAt = data.last_analysis_at ? _fmtTime(data.last_analysis_at) : '--';
        const total = Number((data.pagination || {}).total || 0);
        metaEl.textContent = `最近分析时间：${lastAt} ｜ 共 ${total} 条（包含 HOLD）`;

    } catch (_) { /* 静默忽略，不影响用户 */ }
}

async function _loadHomeFeed(reset) {
    if (_homeFeedLoading) return;
    const listEl = document.getElementById('homeFeedList');
    const metaEl = document.getElementById('homeFeedMeta');
    const moreBtn = document.getElementById('homeFeedLoadMoreBtn');
    if (!listEl || !metaEl || !moreBtn) return;

    _homeFeedLoading = true;
    try {
        if (reset) {
            _homeFeedPage = 1;
            _homeFeedHasNext = true;
            listEl.innerHTML = '<div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div>';
            moreBtn.style.display = 'none';
        }

        const url = `${API_BASE}/api/ai/history-all?page=${_homeFeedPage}&limit=${FEED_LIMIT}`;
        const resp = await authFetch(url);
        if (!resp.ok) {
            listEl.innerHTML = '<div class="no-data text-error">加载失败：接口不可用</div>';
            metaEl.textContent = '加载失败';
            return;
        }
        const payload = await resp.json();
        const data = payload.data || payload;
        const history = Array.isArray(data.history) ? data.history : [];
        const pg = data.pagination || {};
        _homeFeedHasNext = !!pg.has_next;

        // 过滤
        let filtered = history;
        if (_homeFeedFilter === 'trade') {
            filtered = history.filter(it => {
                const s = String(it.signal || '').toUpperCase();
                return s === 'BUY' || s === 'SELL' || s === 'SHORT' || s === 'COVER';
            });
        } else if (_homeFeedFilter === 'hold') {
            filtered = history.filter(it => String(it.signal || '').toUpperCase() === 'HOLD');
        }

        if (reset) {
            if (!filtered.length) {
                listEl.innerHTML = '<div class="no-data">暂无分析记录</div>';
            } else {
                listEl.innerHTML = filtered.map(_renderFeedItem).join('');
            }
        } else {
            const html = filtered.map(_renderFeedItem).join('');
            listEl.insertAdjacentHTML('beforeend', html);
        }

        const lastAt = data.last_analysis_at ? _fmtTime(data.last_analysis_at) : '--';
        const total = Number(pg.total || 0);
        metaEl.textContent = `最近分析时间：${lastAt} ｜ 共 ${total} 条（包含 HOLD）`;

        // 记录最新 ID（供自动刷新比对）
        if (history.length && reset) {
            _homeFeedLatestId = Math.max(...history.map(it => Number(it.id || 0)));
        }

        moreBtn.style.display = _homeFeedHasNext ? '' : 'none';
        if (_homeFeedHasNext) _homeFeedPage += 1;
    } catch (e) {
        listEl.innerHTML = `<div class="no-data text-error">网络错误: ${escapeDebateHtml(e.message)}</div>`;
        metaEl.textContent = '网络错误';
    } finally {
        _homeFeedLoading = false;
    }
}

// 暴露给全局（便于其他模块触发刷新）
window.GangziApp = window.GangziApp || {};
Object.assign(window.GangziApp, {
    loadAnalysisFeed,
    initAnalysisFeed,
});
