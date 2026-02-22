/**
 * 钢子出击 - 回测报告（风控分析Tab）
 */
import { authFetch, escapeHtml, API_BASE } from '../auth.js';

// showToast 由 app.js 定义在 window 上，模块内通过 window 访问
function _showToast(msg) {
    if (typeof window.showToast === 'function') {
        window.showToast(msg);
    }
}

// ============ (e) 回测报告（风控分析Tab） ============
function ensureBacktestReportStyles() {
    if (document.getElementById('backtestReportStyles')) return;
    const styles = document.createElement('style');
    styles.id = 'backtestReportStyles';
    styles.textContent = `
      /* 让回测报告弹窗"像阅读器"：高对比 + 大字号（移动端优先） */
      .bt-report-actions{display:flex;gap:8px;flex-wrap:wrap}
      .bt-report-actions .header-btn{min-height:34px}
      .bt-report-list{display:flex;flex-direction:column;gap:8px}
      .bt-report-row{display:flex;align-items:center;justify-content:space-between;gap:10px;
        padding:12px 12px;border-radius:14px;background:rgba(255,255,255,.06);
        border:1px solid rgba(255,255,255,.10);
      }
      .bt-report-name{font-weight:700;font-size:13px;color:var(--text);word-break:break-all}
      .bt-report-meta{font-size:12px;color:var(--text-muted, rgba(148, 163, 184, .95))}
      .bt-report-row .header-btn{white-space:nowrap}
      /* 覆盖默认确认弹窗：将这个 modal 变成浅色阅读面板 */
      #backtestReportMask{background:rgba(0,0,0,.62)}
      .bt-report-modal-box{
        width:min(980px,96vw);
        max-height:min(88vh,780px);
        overflow:hidden;
        background:#ffffff;
        color:#0f172a;
        border:1px solid rgba(15,23,42,.12);
      }
      .bt-report-modal-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}
      .bt-report-modal-title{font-size:14px;font-weight:800;color:#0f172a;word-break:break-all}
      .bt-report-modal-tabs{display:flex;gap:8px;flex-wrap:wrap}
      .bt-report-tab-btn{min-height:34px}
      .bt-report-modal-box .header-btn{
        background:#f1f5f9;
        color:#0f172a;
        border:1px solid rgba(15,23,42,.16);
      }
      .bt-report-modal-box .header-btn:hover{background:#e2e8f0}
      .bt-report-modal-body{
        border:1px solid rgba(15,23,42,.10);
        background:#f8fafc;
        border-radius:12px;
        padding:12px;
        max-height:calc(min(88vh,780px) - 92px);
        overflow:auto;
        -webkit-overflow-scrolling: touch;
      }
      .bt-report-pre{
        margin:0;
        font-size:14px;
        line-height:1.6;
        white-space:pre-wrap;
        word-break:break-word;
        color:#0f172a;
      }
      .bt-report-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:10px}
      .bt-report-sum-card{padding:12px;border-radius:14px;border:1px solid rgba(15,23,42,.10);background:#ffffff}
      .bt-report-sum-k{font-size:12px;color:rgba(15,23,42,.72)}
      .bt-report-sum-v{font-size:22px;font-weight:900;margin-top:6px;letter-spacing:-0.02em}
      .bt-report-sum-v.pos{color:#16a34a}
      .bt-report-sum-v.neg{color:#dc2626}
      @media (max-width: 520px){ .bt-report-summary{grid-template-columns:1fr} }
      .bt-report-table{width:100%;border-collapse:separate;border-spacing:0 8px}
      .bt-report-table th{font-size:12px;color:rgba(15,23,42,.70);text-align:left;padding:0 10px}
      .bt-report-table td{padding:12px 10px;font-size:14px;color:#0f172a}
      .bt-report-table tr.data-row td{background:#ffffff;border-top:1px solid rgba(15,23,42,.10);border-bottom:1px solid rgba(15,23,42,.10)}
      .bt-report-table tr.data-row td:first-child{border-left:1px solid rgba(15,23,42,.10);border-top-left-radius:14px;border-bottom-left-radius:14px}
      .bt-report-table tr.data-row td:last-child{border-right:1px solid rgba(15,23,42,.10);border-top-right-radius:14px;border-bottom-right-radius:14px}
      .bt-pill{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;font-size:12px;border:1px solid rgba(15,23,42,.12);background:#f1f5f9}
      .bt-pill.pos{border-color:rgba(22,163,74,.25);color:#15803d;background:rgba(22,163,74,.08)}
      .bt-pill.neg{border-color:rgba(220,38,38,.25);color:#b91c1c;background:rgba(220,38,38,.08)}

      /* 移动端：表格改成"卡片列表"更易读 */
      .bt-m-list{display:none}
      .bt-m-row{border:1px solid rgba(15,23,42,.10);background:#ffffff;border-radius:14px;padding:12px;margin:10px 0}
      .bt-m-top{display:flex;align-items:center;justify-content:space-between;gap:10px}
      .bt-m-title{font-weight:900;font-size:14px;color:#0f172a}
      .bt-m-kpis{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
      .bt-m-kpi{display:flex;align-items:center;justify-content:space-between;gap:10px;
        width:100%;padding:10px;border-radius:12px;background:#f8fafc;border:1px solid rgba(15,23,42,.08)}
      .bt-m-k{font-size:12px;color:rgba(15,23,42,.70)}
      .bt-m-v{font-size:14px;font-weight:900;color:#0f172a}
      @media (max-width: 640px){
        .bt-report-table{display:none}
        .bt-m-list{display:block}
        .bt-report-modal-box{width:96vw}
      }
    `;
    document.head.appendChild(styles);
}

function ensureBacktestReportPanel() {
    const tradingPage = document.getElementById('page-trading');
    if (!tradingPage) return null;

    // 已存在就直接返回
    const existing = document.getElementById('backtestReportsPanel');
    if (existing) return existing;

    ensureBacktestReportStyles();

    const card = document.createElement('div');
    card.className = 'card mb';
    card.id = 'backtestReportsPanel';
    card.style.marginTop = '16px';
    card.innerHTML = `
        <div class="card-head" style="display:flex;align-items:center;justify-content:space-between;gap:10px">
          <h3><i class="ri-file-chart-line"></i> 回测报告</h3>
          <div class="bt-report-actions">
            <button type="button" class="header-btn" id="btRefreshBtn"><i class="ri-refresh-line"></i> 刷新</button>
            <button type="button" class="header-btn" id="btViewLatestBtn"><i class="ri-book-open-line"></i> 查看最新</button>
          </div>
        </div>
        <div class="card-body">
          <div class="bt-report-list" id="btReportList">
            <div class="skeleton skeleton-line"></div>
            <div class="skeleton skeleton-line"></div>
            <div class="skeleton skeleton-line"></div>
          </div>
          <div class="panel-label-sm" style="margin-top:10px;color:var(--text-muted, rgba(148,163,184,.9))">
            说明：这里只展示服务器 reports/ 下的回测报告（仅登录可见）。
          </div>
        </div>
    `;

    tradingPage.appendChild(card);
    return document.getElementById('backtestReportsPanel');
}

function _formatBytes(bytes) {
    const n = Number(bytes) || 0;
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function _safeText(str) {
    try { return String(str ?? ''); } catch { return ''; }
}

function _parseBacktestKey(name) {
    // backtest_signals_YYYYMMDD-HHMMSS.(md|json)
    const m = /^backtest_signals_(\d{8}-\d{6})\.(md|json)$/i.exec(String(name || ''));
    if (!m) return null;
    return { key: m[1], ext: m[2].toLowerCase() };
}

function _formatReportKey(key) {
    // 20260217-041523 -> 2026-02-17 04:15:23
    const s = String(key || '');
    if (!/^\d{8}-\d{6}$/.test(s)) return s;
    return `${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)} ${s.slice(9,11)}:${s.slice(11,13)}:${s.slice(13,15)}`;
}

function _extractOverallFromMarkdown(mdText) {
    // 从 md 中提取常用指标，失败就返回空对象（不影响显示）
    const t = String(mdText || '');
    const get = (re) => {
        const m = re.exec(t);
        return m ? m[1] : '';
    };
    return {
        trades: get(/- trades_simulated:\s*`([^`]+)`/),
        winrate: get(/- winrate\(net>0\):\s*`([^`]+)`/),
        netMean: get(/- net_mean:\s*`([^`]+)`/),
        netMedian: get(/- net_median:\s*`([^`]+)`/),
        bestWorst: get(/- net_best \/ net_worst:\s*`([^`]+)`/),
    };
}

function _extractMarkdownTable(mdText, sectionTitle) {
    // sectionTitle 例如： "## By Confidence Bucket (net pnl)"
    const text = String(mdText || '');
    const idx = text.indexOf(sectionTitle);
    if (idx < 0) return null;
    const after = text.slice(idx + sectionTitle.length);

    // 找到第一行表头
    const lines = after.split('\n').map((l) => l.trim());
    const tableStart = lines.findIndex((l) => l.startsWith('|') && l.includes('|'));
    if (tableStart < 0) return null;

    // 连续读取表格行（直到遇到空行或不以 | 开头）
    const tableLines = [];
    for (let i = tableStart; i < lines.length; i++) {
        const l = lines[i];
        if (!l) break;
        if (!l.startsWith('|')) break;
        tableLines.push(l);
    }
    if (tableLines.length < 3) return null; // 至少 header + sep + 1 row

    const parseRow = (line) => {
        // | a | b | -> ["a","b"]
        return line
            .split('|')
            .map((x) => x.trim())
            .filter((x) => x.length > 0);
    };

    const headers = parseRow(tableLines[0]);
    // tableLines[1] 是分隔线
    const rows = tableLines.slice(2).map(parseRow).filter((r) => r.length > 0);
    return { headers, rows };
}

function _renderTableHTML(title, headers, rows, headerMap) {
    const mappedHeaders = (headers || []).map((h) => headerMap[h] || h);
    const htmlRows = (rows || []).map((r) => {
        const tds = r.map((cell, idx) => {
            const raw = String(cell || '');
            const val = raw;
            const isPct = val.endsWith('%');
            const num = parseFloat(val.replace('%', ''));
            const cls = isPct && !isNaN(num) ? (num >= 0 ? 'pos' : 'neg') : '';
            // winrate / net_mean / net_median 都以 % 结尾，做个小 pill 强化可读
            if (isPct && idx > 0) {
                return `<td><span class="bt-pill ${cls}">${escapeHtml(val)}</span></td>`;
            }
            return `<td>${escapeHtml(val)}</td>`;
        }).join('');
        return `<tr class="data-row">${tds}</tr>`;
    }).join('');

    // 移动端卡片：第 0 列为标题，其余列为 KPI
    const mobileCards = (rows || []).map((r) => {
        const name = String(r[0] || '');
        const items = r.slice(1).map((cell, idx) => {
            const h = mappedHeaders[idx + 1] || '';
            const v = String(cell || '');
            const isPct = v.endsWith('%');
            const n = parseFloat(v.replace('%', ''));
            const cls = isPct && !isNaN(n) ? (n >= 0 ? 'pos' : 'neg') : '';
            return `<div class="bt-m-kpi"><div class="bt-m-k">${escapeHtml(h)}</div><div class="bt-m-v ${cls}">${escapeHtml(v)}</div></div>`;
        }).join('');
        return `
          <div class="bt-m-row">
            <div class="bt-m-top">
              <div class="bt-m-title">${escapeHtml(name)}</div>
              <span class="bt-pill">详情</span>
            </div>
            <div class="bt-m-kpis">${items}</div>
          </div>
        `;
    }).join('');

    return `
      <div style="margin:12px 0 6px;font-weight:700;font-size:12px;color:var(--text)">${escapeHtml(title)}</div>
      <div class="bt-m-list">${mobileCards}</div>
      <table class="bt-report-table">
        <thead>
          <tr>${mappedHeaders.map((h) => `<th>${escapeHtml(h)}</th>`).join('')}</tr>
        </thead>
        <tbody>
          ${htmlRows || `<tr><td style="padding:10px 0;color:var(--text-muted, rgba(148,163,184,.9))">暂无数据</td></tr>`}
        </tbody>
      </table>
    `;
}

function _renderOverallSummaryHTML(overall) {
    const trades = overall.trades || '--';
    const winrate = overall.winrate || '--';
    const netMean = overall.netMean || '--';
    const netMedian = overall.netMedian || '--';
    const bestWorst = overall.bestWorst || '--';

    const toNum = (s) => {
        const n = parseFloat(String(s || '').replace('%',''));
        return isNaN(n) ? null : n;
    };
    const meanN = toNum(netMean);
    const meanCls = meanN == null ? '' : (meanN >= 0 ? 'pos' : 'neg');

    return `
      <div class="bt-report-summary">
        <div class="bt-report-sum-card">
          <div class="bt-report-sum-k">样本数（模拟交易）</div>
          <div class="bt-report-sum-v">${escapeHtml(trades)}</div>
        </div>
        <div class="bt-report-sum-card">
          <div class="bt-report-sum-k">胜率（净收益>0）</div>
          <div class="bt-report-sum-v">${escapeHtml(winrate)}</div>
        </div>
        <div class="bt-report-sum-card">
          <div class="bt-report-sum-k">净收益均值</div>
          <div class="bt-report-sum-v ${meanCls}">${escapeHtml(netMean)}</div>
        </div>
        <div class="bt-report-sum-card">
          <div class="bt-report-sum-k">净收益中位数</div>
          <div class="bt-report-sum-v">${escapeHtml(netMedian)}</div>
        </div>
        <div class="bt-report-sum-card" style="grid-column: 1 / -1">
          <div class="bt-report-sum-k">最好 / 最差</div>
          <div class="bt-report-sum-v">${escapeHtml(bestWorst)}</div>
        </div>
      </div>
    `;
}

function showBacktestReportModal(title, mode, payload) {
    ensureBacktestReportStyles();
    let mask = document.getElementById('backtestReportMask');
    if (!mask) {
        mask = document.createElement('div');
        mask.id = 'backtestReportMask';
        mask.className = 'app-confirm-mask';
        mask.innerHTML = `
          <div class="app-confirm-box bt-report-modal-box">
            <div class="bt-report-modal-head">
              <div class="bt-report-modal-title" id="btReportModalTitle"></div>
              <div class="bt-report-modal-tabs">
                <button type="button" class="header-btn bt-report-tab-btn" id="btTabSummary"><i class="ri-bar-chart-2-line"></i> 摘要</button>
                <button type="button" class="header-btn bt-report-tab-btn" id="btTabMarkdown"><i class="ri-markdown-line"></i> 原文</button>
                <button type="button" class="header-btn bt-report-tab-btn" id="btTabJson"><i class="ri-code-line"></i> JSON</button>
                <button type="button" class="header-btn" id="btReportCloseBtn"><i class="ri-close-line"></i> 关闭</button>
              </div>
            </div>
            <div class="bt-report-modal-body">
              <div id="btReportModalBody"></div>
            </div>
          </div>
        `;
        document.body.appendChild(mask);
        // 点遮罩关闭
        mask.addEventListener('click', (e) => {
            if (e.target === mask) mask.classList.remove('show');
        });
    }

    const titleEl = document.getElementById('btReportModalTitle');
    const bodyEl = document.getElementById('btReportModalBody');
    const closeBtn = document.getElementById('btReportCloseBtn');
    const tabSummary = document.getElementById('btTabSummary');
    const tabMarkdown = document.getElementById('btTabMarkdown');
    const tabJson = document.getElementById('btTabJson');

    if (titleEl) titleEl.textContent = title || '回测报告';
    if (closeBtn) closeBtn.onclick = () => mask.classList.remove('show');

    const render = (m, p) => {
        if (!bodyEl) return;
        if (m === 'summary') {
            const md = _safeText(p.markdown || '');
            const overall = _extractOverallFromMarkdown(md);
            // 摘要页：只展示中文摘要 + 两张表（从 md 里解析），不直接铺英文原文
            const conf = _extractMarkdownTable(md, '## By Confidence Bucket (net pnl)');
            const sym = _extractMarkdownTable(md, '## By Symbol (net pnl)');
            const headerMap = {
                bucket: '置信度档',
                symbol: '币种',
                trades: '样本数',
                winrate: '胜率',
                net_mean: '净收益均值',
                net_median: '净收益中位数',
            };
            let html = _renderOverallSummaryHTML(overall);
            if (conf && conf.headers && conf.rows) {
                html += _renderTableHTML('按置信度分桶（净收益）', conf.headers, conf.rows, headerMap);
            }
            if (sym && sym.headers && sym.rows) {
                html += _renderTableHTML('按币种（净收益）', sym.headers, sym.rows, headerMap);
            }
            html += `<div class="panel-label-sm" style="margin-top:10px;color:var(--text-muted, rgba(148,163,184,.9))">提示：想看英文原文可点"原文"，想看原始数据可点"JSON"。</div>`;
            bodyEl.innerHTML = html;
            return;
        }
        if (m === 'markdown') {
            bodyEl.innerHTML = `<pre class="bt-report-pre">${escapeHtml(_safeText(p.markdown || ''))}</pre>`;
            return;
        }
        if (m === 'json') {
            bodyEl.innerHTML = `<pre class="bt-report-pre">${escapeHtml(_safeText(p.json || ''))}</pre>`;
            return;
        }
        bodyEl.innerHTML = `<pre class="bt-report-pre">${escapeHtml(_safeText(p.markdown || ''))}</pre>`;
    };

    // tabs
    if (tabSummary) tabSummary.onclick = () => render('summary', payload);
    if (tabMarkdown) tabMarkdown.onclick = () => render('markdown', payload);
    if (tabJson) tabJson.onclick = () => render('json', payload);

    render(mode || 'summary', payload || {});
    mask.classList.add('show');
}

async function fetchBacktestReportList() {
    const resp = await authFetch(`${API_BASE}/api/reports/backtest/list?limit=50`);
    if (!resp.ok) {
        const e = await resp.json().catch(() => ({}));
        throw new Error(e.detail || '加载报告列表失败');
    }
    const data = await resp.json();
    if (!data || data.success !== true) {
        throw new Error('加载报告列表失败');
    }
    return data.files || [];
}

async function fetchBacktestReportContent(name) {
    const url = `${API_BASE}/api/reports/backtest/read?name=${encodeURIComponent(name)}`;
    const resp = await authFetch(url);
    if (!resp.ok) {
        const e = await resp.json().catch(() => ({}));
        throw new Error(e.detail || '读取报告失败');
    }
    const data = await resp.json();
    if (!data || data.success !== true) {
        throw new Error('读取报告失败');
    }
    return data;
}

export async function loadBacktestReportsPanel() {
    const panel = ensureBacktestReportPanel();
    if (!panel) return;

    const listEl = document.getElementById('btReportList');
    const refreshBtn = document.getElementById('btRefreshBtn');
    const latestBtn = document.getElementById('btViewLatestBtn');
    if (!listEl || !refreshBtn || !latestBtn) return;

    const renderList = (files) => {
        if (!files || files.length === 0) {
            listEl.innerHTML = '<div class="no-data">暂无回测报告（先运行回测脚本生成 reports/backtest_signals_*.md）</div>';
            return;
        }

        // 合并 .md/.json 为一条（按时间戳 key）
        const groups = {};
        (files || []).forEach((f) => {
            const name = _safeText(f.name);
            const parsed = _parseBacktestKey(name);
            if (!parsed) return;
            const key = parsed.key;
            groups[key] = groups[key] || { key, md: null, json: null, mtime_iso: '', mtime: 0, size: 0 };
            const g = groups[key];
            const mtime = Number(f.mtime || 0);
            if (mtime > (g.mtime || 0)) {
                g.mtime = mtime;
                g.mtime_iso = _safeText(f.mtime_iso || '');
            }
            if (parsed.ext === 'md') g.md = f;
            if (parsed.ext === 'json') g.json = f;
        });

        const groupList = Object.values(groups).sort((a, b) => (b.mtime || 0) - (a.mtime || 0));

        listEl.innerHTML = groupList.map((g) => {
            const title = _formatReportKey(g.key);
            const meta = g.mtime_iso ? `${g.mtime_iso}` : '';
            const mdSize = g.md ? _formatBytes(g.md.size) : '--';
            const jsonSize = g.json ? _formatBytes(g.json.size) : '--';
            const badges = `
              <span class="badge badge-cyan" style="margin-left:6px">MD ${escapeHtml(mdSize)}</span>
              <span class="badge badge-purple" style="margin-left:6px">JSON ${escapeHtml(jsonSize)}</span>
            `;
            return `
              <div class="bt-report-row">
                <div>
                  <div class="bt-report-name">${escapeHtml(title)}${badges}</div>
                  <div class="bt-report-meta">${escapeHtml(meta)}</div>
                </div>
                <button type="button" class="header-btn bt-open-btn" data-key="${escapeHtml(g.key)}">
                  <i class="ri-bar-chart-2-line"></i> 查看
                </button>
              </div>
            `;
        }).join('');

        // key -> group 映射
        const groupMap = {};
        groupList.forEach((g) => { groupMap[g.key] = g; });
        listEl.querySelectorAll('.bt-open-btn').forEach((btn) => {
            btn.addEventListener('click', async () => {
                const key = btn.dataset.key;
                const g = groupMap[key];
                if (!g) return;
                try {
                    btn.disabled = true;
                    btn.innerHTML = '<i class="ri-loader-4-line"></i> 打开中...';

                    // 默认：打开 Markdown（更易读）；JSON 作为"原始数据"可切换，按需再加载
                    let markdown = '';
                    if (g.md && g.md.name) {
                        const mdResp = await fetchBacktestReportContent(g.md.name);
                        markdown = _safeText(mdResp.content);
                    } else if (g.json && g.json.name) {
                        // 没有 md 才退化为 json
                        const jsResp = await fetchBacktestReportContent(g.json.name);
                        markdown = _safeText(jsResp.content);
                    } else {
                        _showToast('报告文件不完整');
                        return;
                    }

                    const payload = { markdown, json: '' };
                    const title = `回测报告 · ${_formatReportKey(key)}`;
                    showBacktestReportModal(title, 'summary', payload);

                    // 点击 JSON tab 时再加载 JSON（避免一上来解析大文件卡 Safari）
                    const jsonBtn = document.getElementById('btTabJson');
                    if (jsonBtn) {
                        jsonBtn.onclick = async () => {
                            try {
                                jsonBtn.disabled = true;
                                jsonBtn.innerHTML = '<i class="ri-loader-4-line"></i> 加载中...';
                                if (!payload.json) {
                                    if (g.json && g.json.name) {
                                        const js = await fetchBacktestReportContent(g.json.name);
                                        let txt = _safeText(js.content);
                                        try { txt = JSON.stringify(JSON.parse(txt), null, 2); } catch (_) {}
                                        payload.json = txt;
                                    } else {
                                        payload.json = '暂无 JSON 文件';
                                    }
                                }
                                showBacktestReportModal(title, 'json', payload);
                            } catch (e) {
                                _showToast(`加载 JSON 失败: ${e.message || e}`);
                            } finally {
                                jsonBtn.disabled = false;
                                jsonBtn.innerHTML = '<i class="ri-code-line"></i> JSON';
                            }
                        };
                    }

                } catch (e) {
                    _showToast(`打开失败: ${e.message || e}`);
                } finally {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="ri-bar-chart-2-line"></i> 查看';
                }
            });
        });
    };

    const doRefresh = async () => {
        refreshBtn.disabled = true;
        refreshBtn.innerHTML = '<i class="ri-loader-4-line"></i> 刷新中...';
        try {
            const files = await fetchBacktestReportList();
            renderList(files);
            // 给"查看最新"按钮复用最新 key（优先有 md 的组）
            const groups = {};
            (files || []).forEach((f) => {
                const parsed = _parseBacktestKey(f.name);
                if (!parsed) return;
                groups[parsed.key] = groups[parsed.key] || { key: parsed.key, mtime: 0, hasMd: false };
                groups[parsed.key].mtime = Math.max(groups[parsed.key].mtime, Number(f.mtime || 0));
                if (parsed.ext === 'md') groups[parsed.key].hasMd = true;
            });
            const groupList = Object.values(groups).sort((a, b) => (b.mtime || 0) - (a.mtime || 0));
            const latestGroup = groupList.find((g) => g.hasMd) || groupList[0];
            latestBtn.dataset.latest = latestGroup ? latestGroup.key : '';
        } catch (e) {
            listEl.innerHTML = `<div class="no-data">加载失败：${escapeHtml(e.message || String(e))}</div>`;
        } finally {
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = '<i class="ri-refresh-line"></i> 刷新';
        }
    };

    refreshBtn.onclick = doRefresh;
    latestBtn.onclick = async () => {
        const latest = latestBtn.dataset.latest;
        if (!latest) {
            await doRefresh();
        }
        const latest2 = latestBtn.dataset.latest;
        if (!latest2) {
            _showToast('暂无报告');
            return;
        }
        try {
            latestBtn.disabled = true;
            latestBtn.innerHTML = '<i class="ri-loader-4-line"></i> 打开中...';
            // 直接触发列表里同款逻辑：找对应 key 的 md/json
            const files = await fetchBacktestReportList();
            const md = (files || []).find((f) => String(f.name || '').includes(`_${latest2}.`) && String(f.ext || '').toLowerCase() === 'md');
            const js = (files || []).find((f) => String(f.name || '').includes(`_${latest2}.`) && String(f.ext || '').toLowerCase() === 'json');

            let markdown = '';
            if (md && md.name) {
                const mdResp = await fetchBacktestReportContent(md.name);
                markdown = _safeText(mdResp.content);
            } else if (js && js.name) {
                const jsResp = await fetchBacktestReportContent(js.name);
                markdown = _safeText(jsResp.content);
            } else {
                throw new Error('找不到最新报告文件');
            }

            const payload = { markdown, json: '' };
            const title = `回测报告 · ${_formatReportKey(latest2)}`;
            showBacktestReportModal(title, 'summary', payload);
        } catch (e) {
            _showToast(`打开失败: ${e.message || e}`);
        } finally {
            latestBtn.disabled = false;
            latestBtn.innerHTML = '<i class="ri-book-open-line"></i> 查看最新';
        }
    };

    // 首次加载
    await doRefresh();
}
