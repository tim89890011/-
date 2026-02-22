/**
 * 分析数据（独立新栏目）
 * - 不影响现有 AI 分析栏目
 * - 提供筛选、搜索、时间轴、差异对比、一键复制、导出
 * - 所有 CSS 类名使用 ax- 前缀（避开广告拦截规则）
 */
import { authFetch, escapeHtml as escapeHtmlImported } from './auth.js';

const API_BASE = window.location.origin;
const escapeText = escapeHtmlImported || ((s) => {
    const str = String(s ?? "");
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
});

const PAGE_SIZE = 20;
const ROOT_ID = "analysisDataDynamic";

const state = {
    inited: false,
    history: [],
    filtered: [],
    keyword: "",
    signal: "ALL",
    symbol: "ALL",
    page: 1,
};

function ensureStyles() {
    if (document.getElementById("analysisDataStyles")) return;
    const style = document.createElement("style");
    style.id = "analysisDataStyles";
    style.textContent = `
      #analysisDataDynamic .ax-toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
      #analysisDataDynamic .ax-input,#analysisDataDynamic .ax-select{height:36px;border:1px solid var(--border);background:var(--bg2);color:var(--text);border-radius:10px;padding:0 10px;font-size:13px}
      #analysisDataDynamic .ax-input{min-width:180px;flex:1}
      #analysisDataDynamic .ax-card{display:block;border:1px solid var(--border);background:var(--bg2);border-radius:14px;padding:14px 16px;margin-bottom:10px}
      #analysisDataDynamic .ax-card.ax-new{border-color:var(--blue);box-shadow:0 0 12px rgba(59,130,246,.15)}
      #analysisDataDynamic .ax-head{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}
      #analysisDataDynamic .ax-title{display:flex;align-items:center;gap:8px;font-weight:800}
      #analysisDataDynamic .ax-meta{font-size:12px;color:var(--text3)}
      #analysisDataDynamic .ax-badge{display:inline-flex;align-items:center;border:1px solid rgba(148,163,184,.25);padding:3px 10px;border-radius:999px;font-size:12px;font-weight:800}
      #analysisDataDynamic .ax-badge.buy,#analysisDataDynamic .ax-badge.cover{color:var(--green)}
      #analysisDataDynamic .ax-badge.sell,#analysisDataDynamic .ax-badge.short{color:var(--red)}
      #analysisDataDynamic .ax-badge.hold{color:var(--text3)}
      #analysisDataDynamic .ax-row{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}
      #analysisDataDynamic .ax-kv{font-size:12px;color:var(--text3)}
      #analysisDataDynamic .ax-kv b{color:var(--text)}
      #analysisDataDynamic .ax-digest{margin-top:8px;white-space:pre-wrap;line-height:1.65;font-size:13px;color:var(--text2)}
      #analysisDataDynamic .ax-actions{display:flex;gap:6px;margin-top:10px;flex-wrap:wrap}
      #analysisDataDynamic .ax-box{margin-top:10px;border:1px solid var(--border);border-radius:12px;overflow:hidden}
      #analysisDataDynamic .ax-box summary{padding:10px 14px;cursor:pointer;font-size:13px;font-weight:600;color:var(--text3);user-select:none}
      #analysisDataDynamic .ax-box summary:hover{color:var(--text)}
      #analysisDataDynamic .ax-box-inner{padding:0 14px 14px}
      #analysisDataDynamic .ax-step{padding:8px 0;border-bottom:1px dashed var(--border)}
      #analysisDataDynamic .ax-step:last-child{border-bottom:none}
      #analysisDataDynamic .ax-step-label{font-size:12px;color:var(--text3);font-weight:800;margin-bottom:4px;display:flex;justify-content:space-between;align-items:center}
      #analysisDataDynamic .ax-pre{margin:0;white-space:pre-wrap;word-break:break-word;font-size:12px;line-height:1.55;color:var(--text2);max-height:240px;overflow-y:auto}
      #analysisDataDynamic .ax-btn{height:32px;border:1px solid var(--border);background:transparent;color:var(--text3);border-radius:8px;padding:0 14px;cursor:pointer;font-size:13px;white-space:nowrap}
      #analysisDataDynamic .ax-btn:hover{color:#fff;background:var(--blue);border-color:var(--blue)}
      #analysisDataDynamic .ax-btn-sm{height:26px;font-size:11px;padding:0 8px;border-radius:6px}
      #analysisDataDynamic .ax-empty{padding:24px;text-align:center;color:var(--text3);font-size:13px}
      #analysisDataDynamic .ax-diff-add{color:#22c55e;font-size:12px}
      #analysisDataDynamic .ax-diff-del{color:#ef4444;font-size:12px}
      #analysisDataDynamic .ax-pager{display:flex;gap:8px;justify-content:center;margin-top:12px}
      #analysisDataDynamic .ax-toast{position:fixed;top:20px;left:50%;transform:translateX(-50%);background:#22c55e;color:#fff;padding:8px 20px;border-radius:8px;font-size:13px;z-index:9999;opacity:0;transition:opacity .3s}
      #analysisDataDynamic .ax-toast.show{opacity:1}
      #analysisDataDynamic .ax-badge.error{color:#ef4444;border-color:rgba(239,68,68,.3)}
      #analysisDataDynamic .ax-badge.degraded{color:#f59e0b;border-color:rgba(245,158,11,.3)}
      #analysisDataDynamic .ax-timing{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
      #analysisDataDynamic .ax-timing-chip{font-size:11px;padding:2px 8px;border-radius:6px;background:var(--bg);color:var(--text3);border:1px solid var(--border)}
      #analysisDataDynamic .ax-timing-chip b{color:var(--text)}
      @media (max-width: 768px) {
        #analysisDataDynamic .ax-toolbar { flex-direction: column; }
        #analysisDataDynamic .ax-input { min-width: 100%; }
        #analysisDataDynamic .ax-head { flex-direction: column; gap: 4px; }
        #analysisDataDynamic .ax-actions { flex-direction: column; }
        #analysisDataDynamic .ax-row { flex-direction: column; gap: 4px; }
      }
    `;
    document.head.appendChild(style);
}

function parseMaybeJson(raw, fallback = []) {
    if (!raw) return fallback;
    if (Array.isArray(raw) || typeof raw === "object") return raw;
    try { return JSON.parse(raw); } catch { return fallback; }
}

function sigClass(sig) { return String(sig || "HOLD").toLowerCase(); }

function sigCn(sig) {
    const m = { BUY: "开多", SELL: "平多", SHORT: "开空", COVER: "平空", HOLD: "观望" };
    return m[String(sig || "HOLD").toUpperCase()] || "观望";
}

function fmtTime(s) {
    if (!s) return "--";
    const d = new Date(s);
    if (isNaN(d.getTime())) return String(s);
    return d.toLocaleString("zh-CN", { hour12: false });
}

function truncate(s, max) {
    const str = String(s || "");
    return str.length > max ? str.substring(0, max) + "\u2026" : str;
}

function isNewRecord(item) {
    if (!item.created_at) return false;
    const created = new Date(item.created_at).getTime();
    return Date.now() - created < 5 * 60 * 1000;
}

function findPrevSameSymbol(history, item) {
    const idx = history.findIndex((x) => Number(x.id) === Number(item.id));
    if (idx < 0) return null;
    for (let i = idx + 1; i < history.length; i += 1) {
        if (history[i].symbol === item.symbol) return history[i];
    }
    return null;
}

function diffLines(a, b) {
    const aa = String(a || "").split("\n");
    const bb = String(b || "").split("\n");
    const max = Math.max(aa.length, bb.length);
    const lines = [];
    for (let i = 0; i < max; i += 1) {
        const x = aa[i] ?? "";
        const y = bb[i] ?? "";
        if (x === y) continue;
        if (x) lines.push(`<div class="ax-diff-del">- ${escapeText(x)}</div>`);
        if (y) lines.push(`<div class="ax-diff-add">+ ${escapeText(y)}</div>`);
    }
    return lines.join("") || `<div class="ax-empty">无差异</div>`;
}

function itemText(item) {
    return [item.symbol, item.signal, item.final_reason, item.risk_assessment,
            item.debate_log, item.final_raw_output, item.error_text || ""].join("\n").toLowerCase();
}

function showToast(msg) {
    let t = document.getElementById("axToast");
    if (!t) {
        t = document.createElement("div");
        t.id = "axToast";
        t.className = "ax-toast";
        const root = document.getElementById(ROOT_ID);
        if (root) root.appendChild(t);
        else document.body.appendChild(t);
    }
    t.textContent = msg;
    t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), 1500);
}

function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => showToast("已复制")).catch(() => fallbackCopy(text));
    } else {
        fallbackCopy(text);
    }
}

function fallbackCopy(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.cssText = "position:fixed;left:-9999px";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); showToast("已复制"); } catch { showToast("复制失败"); }
    document.body.removeChild(ta);
}

function exportItemText(item) {
    const roles = parseMaybeJson(item.role_opinions, []);
    const roleInputs = parseMaybeJson(item.role_input_messages, []);
    const finalInputs = parseMaybeJson(item.final_input_messages, []);
    let text = `===== 分析记录 =====\n`;
    text += `币种: ${item.symbol || "--"}\n`;
    text += `信号: ${item.signal || "HOLD"} | 置信度: ${item.confidence || 0}% | 风险: ${item.risk_level || "中"}\n`;
    text += `时间: ${fmtTime(item.created_at)}\n`;
    text += `交易状态: ${item.trade_status || "无"}\n`;
    if (item.error_text) text += `错误: ${item.error_text}\n`;
    const stageTs = parseMaybeJson(item.stage_timestamps, {});
    if (Object.keys(stageTs).length) {
        text += `耗时: ${Object.entries(stageTs).map(([k, v]) => `${k}=${Number(v).toFixed(1)}s`).join(", ")}\n`;
    }
    text += `\n`;
    text += `--- 综合裁决理由 ---\n${item.final_reason || "无"}\n\n`;
    text += `--- 风险评估 ---\n${item.risk_assessment || "无"}\n\n`;
    roles.forEach((r, i) => {
        const ri = findRoleInput(roleInputs, r.name);
        if (ri && Array.isArray(ri.messages) && ri.messages.length) {
            text += `--- 系统 → ${r.name || "分析师"}（发送的提示词）---\n`;
            text += fmtMessages(ri.messages) + "\n\n";
        }
        text += `--- ${r.name || "分析师"} → 系统（输出）(${r.signal || "HOLD"} ${r.confidence || 0}%) ---\n`;
        text += `${r.analysis || "无"}\n\n`;
    });
    if (finalInputs.length) {
        text += `--- 系统 → 最终裁决（发送的提示词）---\n`;
        text += fmtMessages(finalInputs) + "\n\n";
    }
    if (item.final_raw_output) {
        text += `--- 最终裁决原始输出 ---\n${item.final_raw_output}\n\n`;
    }
    if (item.debate_log) {
        text += `--- 辩论日志 ---\n${truncate(item.debate_log, 3000)}\n`;
    }
    return text;
}

function applyFilter() {
    const kw = state.keyword.trim().toLowerCase();
    state.filtered = state.history.filter((x) => {
        if (state.signal !== "ALL" && String(x.signal || "").toUpperCase() !== state.signal) return false;
        if (state.symbol !== "ALL" && x.symbol !== state.symbol) return false;
        if (kw && !itemText(x).includes(kw)) return false;
        return true;
    });
    state.page = 1;
}

function bindToolbarEvents() {
    const kw = document.getElementById("axKeyword");
    const sig = document.getElementById("axSignal");
    const sym = document.getElementById("axSymbol");
    const refresh = document.getElementById("axRefresh");
    if (kw) kw.addEventListener("input", () => { state.keyword = kw.value || ""; applyFilter(); render(); });
    if (sig) sig.addEventListener("change", () => { state.signal = sig.value || "ALL"; applyFilter(); render(); });
    if (sym) sym.addEventListener("change", () => { state.symbol = sym.value || "ALL"; applyFilter(); render(); });
    if (refresh) refresh.addEventListener("click", () => loadData());
}

function fmtMessages(messages) {
    if (!Array.isArray(messages) || !messages.length) return "无";
    return messages.map((m) => {
        const role = String(m.role || "unknown").toUpperCase();
        const content = String(m.content || "");
        return `[${role}]\n${content}`;
    }).join("\n\n---\n\n");
}

function findRoleInput(roleInputs, roleName) {
    if (!Array.isArray(roleInputs)) return null;
    return roleInputs.find((ri) => ri && ri.name === roleName) || null;
}

function buildTimelineHtml(item) {
    const roles = parseMaybeJson(item.role_opinions, []);
    const roleInputs = parseMaybeJson(item.role_input_messages, []);
    const finalInputs = parseMaybeJson(item.final_input_messages, []);
    let html = "";

    html += `<div class="ax-step"><div class="ax-step-label"><span>综合裁决理由</span><button class="ax-btn ax-btn-sm" data-copy-target="next">复制</button></div><pre class="ax-pre">${escapeText(String(item.final_reason || "无"))}</pre></div>`;
    html += `<div class="ax-step"><div class="ax-step-label"><span>风险评估</span><button class="ax-btn ax-btn-sm" data-copy-target="next">复制</button></div><pre class="ax-pre">${escapeText(String(item.risk_assessment || "无"))}</pre></div>`;

    roles.forEach((r) => {
        const ri = findRoleInput(roleInputs, r.name);
        if (ri && Array.isArray(ri.messages) && ri.messages.length) {
            html += `<div class="ax-step"><div class="ax-step-label"><span>系统 → ${escapeText(r.name || "分析师")}（发送的提示词）</span><button class="ax-btn ax-btn-sm" data-copy-target="next">复制</button></div><pre class="ax-pre">${escapeText(fmtMessages(ri.messages))}</pre></div>`;
        }
        html += `<div class="ax-step"><div class="ax-step-label"><span>${escapeText(r.name || "分析师")} → 系统（输出）· ${escapeText(String(r.signal || "HOLD"))} ${Number(r.confidence || 0)}%</span><button class="ax-btn ax-btn-sm" data-copy-target="next">复制</button></div><pre class="ax-pre">${escapeText(String(r.analysis || "无"))}</pre></div>`;
    });

    if (finalInputs.length) {
        const inputText = fmtMessages(finalInputs);
        html += `<div class="ax-step"><div class="ax-step-label"><span>系统 → 最终裁决（发送的提示词）</span><button class="ax-btn ax-btn-sm" data-copy-target="next">复制</button></div><pre class="ax-pre">${escapeText(inputText)}</pre></div>`;
    }

    if (item.final_raw_output) {
        html += `<div class="ax-step"><div class="ax-step-label"><span>最终裁决 → 系统（原始输出）</span><button class="ax-btn ax-btn-sm" data-copy-target="next">复制</button></div><pre class="ax-pre">${escapeText(String(item.final_raw_output))}</pre></div>`;
    }

    html += `<div class="ax-step"><div class="ax-step-label"><span>辩论日志</span><button class="ax-btn ax-btn-sm" data-copy-target="next">复制</button></div><pre class="ax-pre">${escapeText(truncate(item.debate_log, 3000))}</pre></div>`;
    return html;
}

function bindDetailLazy() {
    const root = document.getElementById(ROOT_ID);
    if (!root) return;
    root.querySelectorAll("details[data-lazy]").forEach((det) => {
        if (det._lazyBound) return;
        det._lazyBound = true;
        det.addEventListener("toggle", () => {
            if (!det.open) return;
            const inner = det.querySelector(".ax-box-inner");
            if (!inner || inner.dataset.loaded) return;
            inner.dataset.loaded = "1";
            const idx = Number(det.dataset.idx);
            const type = det.dataset.type;
            const item = state.filtered[idx];
            if (!item) return;
            if (type === "timeline") {
                inner.innerHTML = buildTimelineHtml(item);
                bindCopyButtons(inner);
            } else if (type === "diff") {
                const prev = findPrevSameSymbol(state.history, item);
                inner.innerHTML = `<div class="ax-step-label"><span>final_reason 差异</span></div>` + diffLines(prev?.final_reason || "", item.final_reason || "");
            }
        });
    });
}

function bindCopyButtons(container) {
    container.querySelectorAll("[data-copy-target]").forEach((btn) => {
        if (btn._copyBound) return;
        btn._copyBound = true;
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            const pre = btn.closest(".ax-step")?.querySelector(".ax-pre");
            if (pre) copyText(pre.textContent || "");
        });
    });
}

function bindCardActions() {
    const root = document.getElementById(ROOT_ID);
    if (!root) return;
    root.querySelectorAll("[data-action]").forEach((btn) => {
        if (btn._actionBound) return;
        btn._actionBound = true;
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            const action = btn.dataset.action;
            const idx = Number(btn.dataset.idx);
            const item = state.filtered[idx];
            if (!item) return;
            if (action === "copy-summary") {
                copyText(`${item.symbol} ${sigCn(item.signal)} 置信度${item.confidence}% | ${item.final_reason || "无"}`);
            } else if (action === "export") {
                const text = exportItemText(item);
                const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `analysis_${item.symbol || "unknown"}_${item.id || Date.now()}.txt`;
                a.click();
                URL.revokeObjectURL(url);
                showToast("已导出");
            } else if (action === "copy-all") {
                copyText(exportItemText(item));
            }
        });
    });
}

function bindPagerEvents() {
    const root = document.getElementById(ROOT_ID);
    if (!root) return;
    root.querySelectorAll("[data-page-action]").forEach((btn) => {
        btn.addEventListener("click", () => {
            const action = btn.dataset.pageAction;
            const totalPages = Math.ceil(state.filtered.length / PAGE_SIZE);
            if (action === "prev" && state.page > 1) state.page--;
            if (action === "next" && state.page < totalPages) state.page++;
            render();
            root.scrollIntoView({ behavior: "smooth", block: "start" });
        });
    });
}

function render() {
    const root = document.getElementById(ROOT_ID);
    if (!root) return;
    root.style.cssText = "display:block;visibility:visible;min-height:50px";

    const totalPages = Math.ceil(state.filtered.length / PAGE_SIZE) || 1;
    if (state.page > totalPages) state.page = totalPages;
    const start = (state.page - 1) * PAGE_SIZE;
    const pageItems = state.filtered.slice(start, start + PAGE_SIZE);

    const pager = state.filtered.length > PAGE_SIZE
      ? `<div class="ax-pager">` +
          `<button class="ax-btn" data-page-action="prev" ${state.page <= 1 ? "disabled" : ""}>上一页</button>` +
          `<span class="ax-meta" style="line-height:32px">第 ${state.page}/${totalPages} 页</span>` +
          `<button class="ax-btn" data-page-action="next" ${state.page >= totalPages ? "disabled" : ""}>下一页</button>` +
        `</div>`
      : "";

    const symbolOpts = Array.from(new Set(state.history.map((x) => x.symbol))).map((s) =>
        `<option value="${escapeText(s)}" ${state.symbol === s ? "selected" : ""}>${escapeText(s)}</option>`).join("");

    root.innerHTML =
      `<div class="ax-toolbar">` +
        `<input id="axKeyword" class="ax-input" placeholder="搜索关键词（理由/角色/日志/输出）" value="${escapeText(state.keyword)}" />` +
        `<select id="axSignal" class="ax-select">` +
          `<option value="ALL" ${state.signal === "ALL" ? "selected" : ""}>全部信号</option>` +
          `<option value="BUY" ${state.signal === "BUY" ? "selected" : ""}>BUY</option>` +
          `<option value="SELL" ${state.signal === "SELL" ? "selected" : ""}>SELL</option>` +
          `<option value="SHORT" ${state.signal === "SHORT" ? "selected" : ""}>SHORT</option>` +
          `<option value="COVER" ${state.signal === "COVER" ? "selected" : ""}>COVER</option>` +
          `<option value="HOLD" ${state.signal === "HOLD" ? "selected" : ""}>HOLD</option>` +
        `</select>` +
        `<select id="axSymbol" class="ax-select">` +
          `<option value="ALL">全部币种</option>` +
          symbolOpts +
        `</select>` +
        `<button type="button" class="ax-btn" id="axRefresh">刷新</button>` +
      `</div>` +
      `<div class="ax-meta" style="margin-bottom:10px">共 ${state.filtered.length} 条（原始 ${state.history.length} 条）</div>` +
      `<div id="axCardList" style="display:block;visibility:visible;min-height:80px"></div>` +
      pager;

    const cardList = document.getElementById("axCardList");
    if (!cardList) return;
    if (!pageItems.length) {
        cardList.innerHTML = `<div class="ax-empty">当前筛选条件下没有记录</div>`;
    } else {
        const frag = document.createDocumentFragment();
        pageItems.forEach((item, i) => {
            const globalIdx = start + i;
            const isNew = isNewRecord(item);
            const card = document.createElement("div");
            card.className = "ax-card" + (isNew ? " ax-new" : "");
            const hasError = !!item.error_text;
            const stageTs = parseMaybeJson(item.stage_timestamps, {});
            const stageCn = {fetch:"采集数据",roles:"角色分析",r1:"最终裁决",total:"总耗时"};
            const timingHtml = Object.keys(stageTs).length
              ? `<div class="ax-timing">` +
                  Object.entries(stageTs).map(([k, v]) => `<span class="ax-timing-chip">${escapeText(stageCn[k]||k)} <b>${Number(v).toFixed(1)}s</b></span>`).join("") +
                `</div>`
              : "";

            card.innerHTML =
              `<div class="ax-head">` +
                `<div class="ax-title">` +
                  `<span class="ax-badge ${sigClass(item.signal)}">${escapeText(sigCn(item.signal))}</span>` +
                  `<span>${escapeText(item.symbol || "--")}</span>` +
                  (isNew ? `<span style="font-size:11px;color:var(--blue);font-weight:400">NEW</span>` : "") +
                  (hasError ? `<span class="ax-badge error">${escapeText(item.error_text)}</span>` : "") +
                `</div>` +
                `<div class="ax-meta">${escapeText(fmtTime(item.created_at))}</div>` +
              `</div>` +
              `<div class="ax-row">` +
                `<div class="ax-kv">置信度 <b>${Number(item.confidence || 0)}%</b></div>` +
                `<div class="ax-kv">风险 <b>${escapeText(item.risk_level || "中")}</b></div>` +
                `<div class="ax-kv">交易 <b>${escapeText(item.trade_status || "无")}</b></div>` +
                (item.prev_same_symbol_id ? `<div class="ax-kv">上一条 <b>#${item.prev_same_symbol_id}</b></div>` : "") +
              `</div>` +
              timingHtml +
              `<div class="ax-digest">${escapeText(truncate(item.final_reason, 200))}</div>` +
              `<div class="ax-actions">` +
                `<button class="ax-btn ax-btn-sm" data-action="copy-summary" data-idx="${globalIdx}">复制摘要</button>` +
                `<button class="ax-btn ax-btn-sm" data-action="copy-all" data-idx="${globalIdx}">复制全文</button>` +
                `<button class="ax-btn ax-btn-sm" data-action="export" data-idx="${globalIdx}">导出TXT</button>` +
              `</div>` +
              `<details class="ax-box" data-lazy="1" data-idx="${globalIdx}" data-type="timeline">` +
                `<summary>展开完整分析（输入+输出+时间轴）</summary>` +
                `<div class="ax-box-inner">加载中...</div>` +
              `</details>` +
              `<details class="ax-box" data-lazy="1" data-idx="${globalIdx}" data-type="diff">` +
                `<summary>与上一条同币种对比</summary>` +
                `<div class="ax-box-inner">加载中...</div>` +
              `</details>`;
            frag.appendChild(card);
        });
        cardList.appendChild(frag);
    }

    bindToolbarEvents();
    bindDetailLazy();
    bindPagerEvents();
    bindCardActions();
}

async function loadData() {
    const root = document.getElementById(ROOT_ID);
    if (!root) return;
    root.style.cssText = "display:block;visibility:visible;min-height:50px";
    root.innerHTML = `<div class="ax-empty">加载中...</div>`;
    try {
        const resp = await authFetch(`${API_BASE}/api/ai/history-all?page=1&limit=50`);
        if (!resp.ok) {
            root.innerHTML = `<div class="ax-empty">加载失败：接口返回 ${resp.status}</div>`;
            return;
        }
        const payload = await resp.json();
        const data = payload.data || payload;
        state.history = Array.isArray(data.history) ? data.history : [];
        applyFilter();
        render();
    } catch (e) {
        root.innerHTML = `<div class="ax-empty">加载失败：${escapeText(e.message || "未知错误")}</div>`;
    }
}

export function initAnalysisDataPanel() {
    if (state.inited) return;
    const panel = document.getElementById(ROOT_ID);
    if (!panel) return;
    ensureStyles();
    state.inited = true;
    loadData();
}

export { loadData as refreshAnalysisDataPanel };

window.GangziApp = window.GangziApp || {};
Object.assign(window.GangziApp, {
    initAnalysisDataPanel,
    refreshAnalysisDataPanel: loadData,
});
