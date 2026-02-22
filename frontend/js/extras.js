/**
 * 钢子出击 - 彩蛋功能
 * 市场情绪温度计 + 巨鲸警报 + AI 方向一致性统计面板
 */
import { authFetch, escapeHtml, API_BASE } from './auth.js';

const EXTRAS_DEBUG = false;

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

// ============ (a) 市场情绪温度计 ============
export async function loadSentimentPanel() {
    const panel = document.getElementById('sentimentPanel');
    if (!panel) return;

    try {
        const resp = await authFetch(`${API_BASE}/api/market/sentiment`);
        if (!resp.ok) {
            panel.innerHTML = '<div class="no-data">情绪数据获取失败</div>';
            return;
        }
        const data = await resp.json();
        const value = parseInt(data.value || 50);
        const label = data.label || 'Neutral';

        // 颜色映射
        let color, bgColor;
        if (value <= 25) { color = '#3b82f6'; bgColor = 'rgba(59,130,246,0.1)'; }
        else if (value <= 45) { color = '#06b6d4'; bgColor = 'rgba(6,182,212,0.1)'; }
        else if (value <= 55) { color = '#ffc107'; bgColor = 'rgba(255,193,7,0.1)'; }
        else if (value <= 75) { color = '#f97316'; bgColor = 'rgba(249,115,22,0.1)'; }
        else { color = '#ff4757'; bgColor = 'rgba(255,71,87,0.1)'; }

        const labelCn = {
            'Extreme Fear': '极度恐惧',
            'Fear': '恐惧',
            'Neutral': '中性',
            'Greed': '贪婪',
            'Extreme Greed': '极度贪婪',
        }[label] || label;

        panel.innerHTML = `
        <div class="sentiment-wrap">
            <div class="sentiment-value">${value}</div>
            <div class="sentiment-label">${labelCn}</div>
            <div class="sentiment-bar">
                <div class="sentiment-pointer" data-left="${value}"></div>
            </div>
            <div class="sentiment-axis">
                <span>极度恐惧</span>
                <span>中性</span>
                <span>极度贪婪</span>
            </div>
        </div>`;
        const valueEl = panel.querySelector('.sentiment-value');
        const labelEl = panel.querySelector('.sentiment-label');
        const pointerEl = panel.querySelector('.sentiment-pointer');
        if (valueEl) valueEl.style.color = color;
        if (labelEl) labelEl.style.color = color;
        if (pointerEl) pointerEl.style.left = `${value}%`;

    } catch (e) {
        panel.innerHTML = '<div class="no-data">情绪指数加载失败</div>';
        if (EXTRAS_DEBUG) console.warn('情绪指数获取失败:', e);
    }
}

// ============ (c) 巨鲸警报 ============
export async function loadWhalePanel() {
    const panel = document.getElementById('whalePanel');
    if (!panel) return;

    try {
        const resp = await authFetch(`${API_BASE}/api/market/large-trades/BTCUSDT`);
        if (!resp.ok) { panel.innerHTML = '<div class="no-data">巨鲸数据加载失败</div>'; return; }
        const data = await resp.json();
        const trades = data.trades || [];

        if (trades.length === 0) {
            panel.innerHTML = '<div class="no-data">暂无大额交易数据</div>';
            return;
        }

        panel.innerHTML = `
        <div class="whale-title">BTC 最近大额交易（按成交额排序）</div>
        ${trades.slice(0, 8).map(t => {
            const isBuy = !t.is_buyer_maker;
            const amountCls = isBuy ? 'text-up' : 'text-down';
            const icon = isBuy ? '🟢' : '🔴';
            const amount = (t.quote_qty / 1000).toFixed(1);
            const time = new Date(t.time).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

            return `<div class="whale-row">
                <span>${icon} ${isBuy ? '买入' : '卖出'}</span>
                <span class="${amountCls} whale-amount">$${escapeHtml(amount)}K</span>
                <span class="text-muted">@ $${escapeHtml(String(Number(t.price) || 0))}</span>
                <span class="whale-time">${escapeHtml(time)}</span>
            </div>`;
        }).join('')}`;

    } catch (e) {
        panel.innerHTML = '<div class="no-data">巨鲸数据加载失败</div>';
    }
}

// ============ (d) AI 方向一致性统计面板（Pro 重设计） ============
let _accCurrentDays = 0; // 当前筛选天数
let _accDailyChart = null;
let _accFilterBound = false;
let _accReqSeq = 0;

export async function loadAccuracyPanel(days) {
    if (typeof days === 'number') _accCurrentDays = days;
    const panel = document.getElementById('accuracyPanel');
    if (!panel) return;

    try {
        const reqId = ++_accReqSeq;
        const url = _accCurrentDays > 0
            ? `${API_BASE}/api/ai/accuracy?days=${_accCurrentDays}`
            : `${API_BASE}/api/ai/accuracy`;
        const resp = await authFetch(url);
        if (!resp.ok) { panel.innerHTML = '<div class="no-data">统计数据加载失败</div>'; return; }
        const stats = await resp.json();
        // 防竞态：只渲染最后一次请求的结果
        if (reqId !== _accReqSeq) return;

        if (stats.total_signals === 0) {
            // 今日可能没有任何已验证信号：仍渲染趋势区块，避免 UI 直接消失/提示不更新
            panel.innerHTML = `
                <div class="acc-banner">
                    <i class="ri-error-warning-line"></i>
                    <span>此统计仅为价格方向预测一致性参考，不构成投资效果保证</span>
                </div>
                <div class="no-data" style="margin:10px 0;">暂无足够数据统计方向一致性（需等待信号验证）</div>
                <div class="acc-section">
                    <div class="acc-section-title">按天准确率变化</div>
                    <div class="chart-h chart-h-200">
                        <canvas id="accDailyTrendChart"></canvas>
                    </div>
                    <div class="acc-meta" id="accDailyTrendHint">--</div>
                </div>
            `;
            try { renderAccDailyTrend(stats); } catch (_) {}
            return;
        }

        const acc = stats.weighted_accuracy || 0;
        const ringAngle = Math.min(acc, 100) / 100 * 360;
        const ringColor = acc >= 60 ? 'var(--green)' : acc >= 40 ? 'var(--blue)' : 'var(--red)';
        const accCls = acc >= 60 ? 'text-up' : acc >= 40 ? 'text-mid' : 'text-down';

        // 币种卡片
        let coinsHtml = '';
        if (stats.by_symbol && Object.keys(stats.by_symbol).length > 0) {
            const coins = Object.entries(stats.by_symbol).map(([symbol, data]) => {
                const pct = data.accuracy || 0;
                const accent = pct >= 55 ? 'var(--green)' : pct >= 45 ? 'var(--blue)' : 'var(--red)';
                return `<div class="acc-coin" style="--coin-accent:${accent}">
                    <div class="acc-coin-name">${escapeHtml(symbol.replace('USDT', ''))}</div>
                    <div class="acc-coin-pct">${pct}%</div>
                    <div class="acc-coin-frac">(${data.correct}/${data.total})</div>
                </div>`;
            }).join('');
            coinsHtml = `<div class="acc-section">
                <div class="acc-section-title">各币种方向一致性</div>
                <div class="acc-coins">${coins}</div>
            </div>`;
        }

        // 信号类型进度条
        let typesHtml = '';
        if (stats.by_signal_type) {
            const typeConfig = {
                'BUY':  { label: '买入', color: 'var(--green)', cls: 'text-up' },
                'SELL': { label: '卖出', color: 'var(--red)',   cls: 'text-down' },
                'HOLD': { label: '观望', color: 'var(--text3)', cls: 'text-muted' },
            };
            const types = Object.entries(stats.by_signal_type)
                .filter(([_, d]) => d.total > 0)
                .map(([type, data]) => {
                    const cfg = typeConfig[type] || { label: type, color: 'var(--text3)', cls: '' };
                    const pct = data.accuracy || 0;
                    return `<div class="acc-type">
                        <div class="acc-type-left">
                            <span class="acc-type-dot" style="background:${cfg.color}"></span>
                            <span class="acc-type-name">${cfg.label}</span>
                        </div>
                        <div class="acc-type-bar-track">
                            <div class="acc-type-bar-fill" style="width:${pct}%;background:${cfg.color}"></div>
                        </div>
                        <div class="acc-type-right">
                            <span class="acc-type-pct ${cfg.cls}">${pct}%</span>
                            <span class="acc-type-count">${data.total}次</span>
                        </div>
                    </div>`;
                }).join('');
            typesHtml = `<div class="acc-section">
                <div class="acc-section-title">各信号类型表现</div>
                <div class="acc-types">${types}</div>
            </div>`;
        }

        // 方法说明
        const methodology = stats.methodology || {};
        const thresholds = methodology.thresholds || {};
        const timeDecay = methodology.time_decay || {};
        const weights = timeDecay.weights || [];
        const disclaimer = stats.disclaimer || {};

        const thresholdTags = Object.entries(thresholds.values || {}).map(([sym, val]) =>
            `<span class="acc-method-tag">${escapeHtml(sym.replace('USDT', ''))}: ${escapeHtml(val)}</span>`
        ).join('') + `<span class="acc-method-tag default">默认: ${escapeHtml(thresholds.default || '2.0%')}</span>`;

        const weightItems = weights.map(w =>
            `<div class="acc-method-weight">
                <span class="acc-method-weight-period">${escapeHtml(w.period)}</span>
                <span class="acc-method-weight-val">${escapeHtml(w.weight)}</span>
            </div>`
        ).join('');

        panel.innerHTML = `
            <div class="acc-banner">
                <i class="ri-error-warning-line"></i>
                <span>此统计仅为价格方向预测一致性参考，不构成投资效果保证</span>
            </div>

            <div class="acc-hero">
                <div class="acc-hero-side">
                    <div class="acc-hero-num text-up">${stats.correct_count}</div>
                    <div class="acc-hero-label">预测正确</div>
                    <div class="acc-hero-sub">次</div>
                </div>
                <div class="acc-ring" style="--ring-color:${ringColor};--ring-angle:${ringAngle}deg">
                    <div class="acc-ring-inner">
                        <div class="acc-ring-val ${accCls}">${acc}%</div>
                        <div class="acc-ring-sub">方向一致性</div>
                    </div>
                </div>
                <div class="acc-hero-side">
                    <div class="acc-hero-num text-down">${stats.incorrect_count}</div>
                    <div class="acc-hero-label">预测错误</div>
                    <div class="acc-hero-sub">次</div>
                </div>
            </div>

            <div class="acc-meta">
                总信号 <b>${stats.total_signals}</b> · 中性 <b>${stats.neutral_count}</b> · 平均价格变化 <b>${stats.avg_price_change > 0 ? '+' : ''}${stats.avg_price_change}%</b>
            </div>

            <div class="acc-section">
                <div class="acc-section-title">按天准确率变化</div>
                <div class="chart-h chart-h-200">
                    <canvas id="accDailyTrendChart"></canvas>
                </div>
                <div class="acc-meta" id="accDailyTrendHint">--</div>
            </div>

            ${coinsHtml}
            ${typesHtml}

            <details class="acc-method">
                <summary>
                    <span class="acc-method-icon"><i class="ri-bar-chart-2-line"></i></span>
                    统计方法说明
                    <span class="acc-method-arrow">▼</span>
                </summary>
                <div class="acc-method-body">
                    <h4>${escapeHtml(methodology.title || '统计方法说明')}</h4>
                    <p>${escapeHtml(methodology.description || '')}</p>

                    <h5>判断规则</h5>
                    <ul>${(methodology.rules || []).map(rule => `<li>${escapeHtml(rule)}</li>`).join('')}</ul>

                    <h5>${escapeHtml(thresholds.description || 'HOLD 信号阈值')}</h5>
                    <div class="acc-method-thresholds">${thresholdTags}</div>

                    <h5>${escapeHtml(timeDecay.description || '时间衰减权重')}</h5>
                    <div class="acc-method-weights">${weightItems}</div>

                    <div class="acc-method-disclaimer">
                        <h4>${escapeHtml(disclaimer.title || '重要免责声明')}</h4>
                        <p>${escapeHtml(disclaimer.content || '')}</p>
                        <p><strong>${escapeHtml(disclaimer.risk_warning || '')}</strong></p>
                    </div>
                </div>
            </details>`;

        // 趋势图（可选）：无数据也会更新 hint，避免保留旧状态
        try { renderAccDailyTrend(stats); } catch (e) {
            if (EXTRAS_DEBUG) console.warn('[准确率] 趋势图渲染失败:', e);
        }

    } catch (e) {
        panel.innerHTML = '<div class="no-data">方向一致性统计加载失败</div>';
        if (EXTRAS_DEBUG) console.error('准确率面板加载失败:', e);
    }
}

function renderAccDailyTrend(stats) {
    const canvas = document.getElementById('accDailyTrendChart');
    const hint = document.getElementById('accDailyTrendHint');
    if (!canvas) return;

    const series = Array.isArray(stats.by_day) ? stats.by_day : [];
    if (typeof Chart === 'undefined') {
        if (hint) hint.textContent = 'Chart.js 未加载，无法绘制趋势图';
        return;
    }

    const w = stats.trend_window_days || (_accCurrentDays || 0);
    const rangeText = _accCurrentDays === 0 ? `最近${w}天` : `${_accCurrentDays}天`;

    if (!series.length) {
        if (hint) hint.textContent = `区间: ${rangeText} · 暂无按天趋势数据`;
        if (_accDailyChart) {
            _accDailyChart.destroy();
            _accDailyChart = null;
        }
        return;
    }

    const labels = series.map((d) => String(d.date || '--').slice(5));
    const values = series.map((d) => Number(d.accuracy || 0));
    const latest = series[series.length - 1] || {};
    if (hint) {
        hint.textContent = `区间: ${rangeText} · 最新 ${Number(latest.accuracy || 0).toFixed(1)}%（${latest.correct || 0}对/${latest.incorrect || 0}错）`;
    }

    if (_accDailyChart) _accDailyChart.destroy();
    _accDailyChart = new Chart(canvas, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: '方向准确率(%)',
                data: values,
                borderColor: '#22c55e',
                backgroundColor: 'rgba(34, 197, 94, 0.12)',
                fill: true,
                tension: 0.32,
                pointRadius: 2,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, max: 100 },
                x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } },
            },
        },
    });
}

// ============ 信号历史完整列表 ============
export async function loadSignalHistory() {
    const container = document.getElementById('signalHistory');
    if (!container) return;

    try {
        const resp = await authFetch(`${API_BASE}/api/ai/history?limit=50`);
        if (!resp.ok) return;
        const data = await resp.json();

        if (!data.history || data.history.length === 0) {
            container.innerHTML = '<div class="no-data">暂无信号记录</div>';
            return;
        }

        container.innerHTML = data.history.map(s => {
            const sigCn = { BUY: '买入', SELL: '卖出', HOLD: '观望' }[s.signal] || '观望';
            const time = s.created_at ? new Date(s.created_at).toLocaleString('zh-CN') : '--';

            const dotCls = s.signal === 'BUY' ? 'dot-buy' : s.signal === 'SELL' ? 'dot-sell' : 'dot-hold';
            return `<div class="signal-item">
                <div class="signal-dot ${dotCls}"></div>
                <span class="signal-time signal-time-wide">${escapeHtml(time)}</span>
                <span class="signal-msg"><strong>${escapeHtml(s.symbol)}</strong> ${escapeHtml(sigCn)} · 置信度 ${Number(s.confidence) || 0}% · $${Number(s.price_at_signal) || 0} · 风险${escapeHtml(s.risk_level || '中')}</span>
            </div>`;
        }).join('');

    } catch (e) {
        container.innerHTML = '<div class="no-data">信号历史加载失败</div>';
    }
}

// ============ (e) API 配额与成本监控面板 ============
export async function loadQuotaPanel() {
    const panel = document.getElementById('quotaPanel');
    if (!panel) return;

    try {
        const callsResp = await authFetch(`${API_BASE}/api/metrics/api-calls?hours=24`);
        const costResp = await authFetch(`${API_BASE}/api/metrics/cost`);
        if (!callsResp.ok || !costResp.ok) {
            panel.innerHTML = '<div class="no-data">配额数据加载失败</div>';
            return;
        }
        const callsData = await callsResp.json();
        const costData = await costResp.json();

        const quota = (callsData.quota_history && callsData.quota_history[0]) || {};
        const strategy = { actions: [] };
        const projected = costData.projected || {};
        const costEstimate = {
            current_cost: Number(costData.today?.estimated_cost_cny || 0),
            projected_daily_cost: Number(projected.daily_cost || 0),
            monthly_estimate: Number(projected.monthly_estimate || 0),
            cost_per_call: Number(costData.today?.estimated_cost_cny || 0) / Math.max(Number(costData.today?.api_calls || 0), 1),
        };

        // 根据状态确定颜色
        const statusColors = {
            normal: { color: '#00ff88', bg: 'rgba(0,255,136,0.1)' },
            warning: { color: '#ffc107', bg: 'rgba(255,193,7,0.1)' },
            critical: { color: '#ff6b6b', bg: 'rgba(255,107,107,0.1)' },
            exceeded: { color: '#ff4757', bg: 'rgba(255,71,87,0.1)' },
        };
        const statusConfig = statusColors[quota.status] || statusColors.normal;

        const statusLabels = {
            normal: '正常',
            warning: '警告',
            critical: '危险',
            exceeded: '已超限',
        };

        // 进度条宽度
        const progressWidth = Math.min(quota.usage_percent || 0, 100);

        panel.innerHTML = `
        <div class="quota-summary">
            <div class="quota-main-stat">
                <div class="quota-ring" style="--progress: ${progressWidth}; --color: ${statusConfig.color}">
                    <div class="quota-ring-inner">
                        <span class="quota-percent">${quota.usage_percent?.toFixed(1) || 0}%</span>
                        <span class="quota-status">${statusLabels[quota.status]}</span>
                    </div>
                </div>
                <div class="quota-text-stats">
                    <div class="quota-stat-row">
                        <span class="stat-label">今日调用</span>
                        <span class="stat-value">${quota.total_calls || 0} / ${quota.quota_limit || 0}</span>
                    </div>
                    <div class="quota-stat-row">
                        <span class="stat-label">剩余配额</span>
                        <span class="stat-value ${quota.remaining < 1000 ? 'text-down' : ''}">${quota.remaining || 0}</span>
                    </div>
                    <div class="quota-stat-row">
                        <span class="stat-label">预估成本</span>
                        <span class="stat-value">\u00A5${costEstimate.current_cost?.toFixed(4) || '0.0000'}</span>
                    </div>
                </div>
            </div>

            <div class="quota-progress-bar">
                <div class="progress-track">
                    <div class="progress-fill" style="width: ${progressWidth}%; background: ${statusConfig.color}"></div>
                </div>
                <div class="progress-marks">
                    <span class="mark-warning" style="left: 80%" title="警告阈值"><i class="ri-error-warning-line"></i></span>
                    <span class="mark-critical" style="left: 90%" title="危险阈值"><i class="ri-alarm-warning-line"></i></span>
                </div>
            </div>

            ${strategy.actions && strategy.actions.length > 0 ? `
            <div class="quota-strategy">
                <div class="strategy-title">
                    <span class="strategy-icon"><i class="ri-file-list-3-line"></i></span>
                    当前策略
                </div>
                <ul class="strategy-list">
                    ${strategy.actions.map(action => `<li>${escapeHtml(action)}</li>`).join('')}
                </ul>
            </div>
            ` : ''}

            <div class="quota-breakdown">
                <div class="breakdown-title">调用类型分布</div>
                <div class="breakdown-grid">
                    <div class="breakdown-item">
                        <span class="breakdown-label">分析调用</span>
                        <span class="breakdown-value">${quota.analysis_calls || 0}</span>
                    </div>
                    <div class="breakdown-item">
                        <span class="breakdown-label">聊天调用</span>
                        <span class="breakdown-value">${quota.chat_calls || 0}</span>
                    </div>
                    <div class="breakdown-item">
                        <span class="breakdown-label">R1裁决</span>
                        <span class="breakdown-value">${quota.reasoner_calls || 0}</span>
                    </div>
                </div>
            </div>

            <div class="quota-cost-projection">
                <div class="projection-title"><i class="ri-money-dollar-circle-line"></i> 成本预估</div>
                <div class="projection-grid">
                    <div class="projection-item">
                        <span class="projection-label">今日预计</span>
                        <span class="projection-value">\u00A5${costEstimate.projected_daily_cost?.toFixed(2) || '0.00'}</span>
                    </div>
                    <div class="projection-item">
                        <span class="projection-label">月度预估</span>
                        <span class="projection-value">\u00A5${costEstimate.monthly_estimate?.toFixed(2) || '0.00'}</span>
                    </div>
                    <div class="projection-item">
                        <span class="projection-label">单次成本</span>
                        <span class="projection-value">\u00A5${costEstimate.cost_per_call?.toFixed(6) || '0.000000'}</span>
                    </div>
                </div>
            </div>
        </div>`;

    } catch (e) {
        panel.innerHTML = '<div class="no-data">配额数据加载失败</div>';
        if (EXTRAS_DEBUG) console.error('配额面板加载失败:', e);
    }
}

// ============ (f) 成本监控详细面板 ============
export async function loadCostPanel() {
    const panel = document.getElementById('costPanel');
    if (!panel) return;

    try {
        const costResp = await authFetch(`${API_BASE}/api/metrics/cost`);
        const callsResp = await authFetch(`${API_BASE}/api/metrics/api-calls?hours=24`);
        if (!costResp.ok || !callsResp.ok) {
            panel.innerHTML = '<div class="no-data">成本数据加载失败</div>';
            return;
        }
        const costData = await costResp.json();
        const callsData = await callsResp.json();
        const currentStats = callsData.current_stats || {};
        const byModelMetrics = currentStats.by_model || {};
        const recent5m = currentStats.recent_5min || {};

        const avgDurations = Object.values(byModelMetrics)
            .map((item) => Number(item.avg_duration_ms || 0))
            .filter((v) => v > 0);
        const avgDurationMs = avgDurations.length > 0
            ? avgDurations.reduce((sum, v) => sum + v, 0) / avgDurations.length
            : 0;

        const today = {
            total_calls: Number(costData.today?.api_calls || 0),
            success_rate: Number(recent5m.success_rate || 0),
            avg_response_time: (avgDurationMs / 1000).toFixed(2),
            total_cost: Number(costData.today?.estimated_cost_cny || 0),
            by_model: costData.today?.by_model || {},
        };

        const errors = {
            total_calls: Number(recent5m.calls || 0),
            failed_calls: Number(recent5m.errors || 0),
            error_rate: Number(recent5m.calls || 0) > 0
                ? Number(((Number(recent5m.errors || 0) / Number(recent5m.calls || 0)) * 100).toFixed(2))
                : 0,
            error_types: {},
        };
        const responseTime = {
            p50: Number((avgDurationMs / 1000).toFixed(2)),
            p90: Number((avgDurationMs / 1000).toFixed(2)),
            p99: Number((avgDurationMs / 1000).toFixed(2)),
            avg: Number((avgDurationMs / 1000).toFixed(2)),
        };

        // 构建模型统计
        let modelStatsHtml = '';
        if (today.by_model) {
            modelStatsHtml = Object.entries(today.by_model).map(([model, stats]) => `
                <div class="model-stat-item">
                    <span class="model-name">${escapeHtml(model)}</span>
                    <span class="model-calls">${stats.total_calls || 0}次</span>
                    <span class="model-cost">\u00A5${Number(stats.estimated_cost_cny || 0).toFixed(4)}</span>
                    <span class="model-tokens">${Number(stats.tokens_in || 0) + Number(stats.tokens_out || 0)}t</span>
                </div>
            `).join('');
        }

        panel.innerHTML = `
        <div class="cost-dashboard">
            <div class="cost-stats-grid">
                <div class="cost-stat-card">
                    <div class="stat-icon"><i class="ri-phone-line"></i></div>
                    <div class="stat-content">
                        <span class="stat-value">${today.total_calls || 0}</span>
                        <span class="stat-label">总调用次数</span>
                    </div>
                </div>
                <div class="cost-stat-card ${today.success_rate >= 95 ? 'good' : today.success_rate >= 80 ? 'warning' : 'bad'}">
                    <div class="stat-icon"><i class="ri-checkbox-circle-line"></i></div>
                    <div class="stat-content">
                        <span class="stat-value">${today.success_rate || 0}%</span>
                        <span class="stat-label">成功率</span>
                    </div>
                </div>
                <div class="cost-stat-card">
                    <div class="stat-icon"><i class="ri-timer-line"></i></div>
                    <div class="stat-content">
                        <span class="stat-value">${today.avg_response_time || 0}s</span>
                        <span class="stat-label">平均响应</span>
                    </div>
                </div>
                <div class="cost-stat-card">
                    <div class="stat-icon"><i class="ri-money-dollar-circle-line"></i></div>
                    <div class="stat-content">
                        <span class="stat-value">\u00A5${today.total_cost?.toFixed(2) || '0.00'}</span>
                        <span class="stat-label">今日成本</span>
                    </div>
                </div>
            </div>

            <div class="cost-details">
                <div class="details-section">
                    <div class="section-title">模型统计</div>
                    <div class="model-stats-list">
                        ${modelStatsHtml || '<div class="no-data">暂无数据</div>'}
                    </div>
                </div>

                <div class="details-section">
                    <div class="section-title">响应时间分布</div>
                    <div class="response-time-stats">
                        <div class="rt-stat">
                            <span class="rt-label">P50</span>
                            <span class="rt-value">${responseTime.p50 || 0}s</span>
                        </div>
                        <div class="rt-stat">
                            <span class="rt-label">P90</span>
                            <span class="rt-value">${responseTime.p90 || 0}s</span>
                        </div>
                        <div class="rt-stat">
                            <span class="rt-label">P99</span>
                            <span class="rt-value">${responseTime.p99 || 0}s</span>
                        </div>
                        <div class="rt-stat">
                            <span class="rt-label">平均</span>
                            <span class="rt-value">${responseTime.avg || 0}s</span>
                        </div>
                    </div>
                </div>

                <div class="details-section">
                    <div class="section-title">错误统计</div>
                    <div class="error-stats">
                        <div class="error-main">
                            <span class="error-rate ${errors.error_rate > 5 ? 'high' : errors.error_rate > 1 ? 'medium' : 'low'}">
                                错误率: ${errors.error_rate || 0}%
                            </span>
                            <span class="error-count">失败: ${errors.failed_calls || 0} / ${errors.total_calls || 0}</span>
                        </div>
                        ${errors.error_types && Object.keys(errors.error_types).length > 0 ? `
                        <div class="error-types">
                            ${Object.entries(errors.error_types).map(([type, count]) => `
                                <span class="error-type-tag ${type}">${escapeHtml(type)}: ${count}</span>
                            `).join('')}
                        </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        </div>`;

    } catch (e) {
        panel.innerHTML = '<div class="no-data">成本数据加载失败</div>';
        if (EXTRAS_DEBUG) console.error('成本面板加载失败:', e);
    }
}

// ============ 准确率筛选按钮绑定 ============
function _initAccFilterButtons() {
    // 事件委托：避免 initExtras 执行时 DOM 还未就绪导致绑定失败
    if (_accFilterBound) return;
    _accFilterBound = true;
    document.addEventListener('click', async (e) => {
        const btn = e.target.closest('#accFilterGroup .acc-filter-btn');
        if (!btn) return;
        const group = document.getElementById('accFilterGroup');
        if (!group) return;
        const days = parseInt(btn.dataset.days, 10) || 0;
        // debug marker for automation / quick inspection
        window.__acc_last_days = days;
        window.__acc_last_ts = Date.now();
        group.querySelectorAll('.acc-filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        // 直接走对外导出的入口（和手动调用一致），并 await 避免竞态覆盖
        const fn = (window.GangziApp && window.GangziApp.loadAccuracyPanel) ? window.GangziApp.loadAccuracyPanel : loadAccuracyPanel;
        await fn(days);
    });
}

// ============ 初始化所有彩蛋 ============
export function initExtras() {
    loadSentimentPanel();
    loadWhalePanel();
    _initAccFilterButtons();
    loadAccuracyPanel(0);
    loadSignalHistory();
    loadQuotaPanel();
    loadCostPanel();
    loadBacktestReportsPanel();
}

window.GangziApp = window.GangziApp || {};
Object.assign(window.GangziApp, {
    loadSentimentPanel,
    loadWhalePanel,
    loadAccuracyPanel,
    loadSignalHistory,
    loadQuotaPanel,
    loadCostPanel,
    loadBacktestReportsPanel,
    initExtras,
});
