/**
 * 钢子出击 - 交易面板 HTML 模板
 * 构建交易面板的完整 HTML 结构
 */

export function buildTradingHTML() {
  return `
    <!-- 账户总览 + 交易开关 -->
    <div class="card mb">
      <div class="card-head">
        <h3><i class="ri-wallet-3-line"></i> 账户总览</h3>
        <div class="trade-toggle-wrap">
          <span class="badge badge-blue" id="tradeStatusBadge">加载中...</span>
          <button type="button" class="trade-toggle-btn" id="tradeToggleBtn" disabled>
            <span class="toggle-icon" id="toggleIcon"><i class="ri-pause-line"></i></span>
            <span id="toggleText">加载中</span>
          </button>
        </div>
      </div>
      <div class="card-body">
        <!-- 资产概览 -->
        <div class="account-hero" id="accountHero">
          <div class="account-hero-main">
            <div class="account-hero-label">总资产估值 (USDT)</div>
            <div class="account-hero-value" id="totalAssetValue">--</div>
            <div class="account-hero-sub" id="totalPnlText">加载中...</div>
          </div>
          <div class="account-hero-grid">
            <div class="account-stat">
              <span class="account-stat-label">可用余额</span>
              <span class="account-stat-value" id="usdtFreeText">--</span>
            </div>
            <div class="account-stat">
            <span class="account-stat-label">持仓市值</span>
              <span class="account-stat-value" id="totalCostText">--</span>
            </div>
            <div class="account-stat">
              <span class="account-stat-label">持仓保证金</span>
              <span class="account-stat-value" id="positionValueText">--</span>
            </div>
            <div class="account-stat">
              <span class="account-stat-label">浮动盈亏</span>
              <span class="account-stat-value" id="floatPnlText">--</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 交易记录 + 持仓盈亏（并排） -->
    <div class="grid-2 mb">
      <div class="card">
        <div class="card-head">
          <h3><i class="ri-file-list-3-line"></i> 交易记录</h3>
          <div style="display:flex;align-items:center;gap:8px;">
            <span class="badge badge-green" id="tradeTodayFilledBadge">今日成交 --</span>
            <span class="badge badge-gray" id="tradeTodayStatusBadge">本轮 --</span>
            <span class="badge badge-cyan" id="tradeCountBadge">--</span>
            <span class="badge badge-red" id="tradeUnreadBadge" style="display:none;">未读 0</span>
            <label class="trade-filter-toggle" title="包含失败和跳过的记录">
              <input type="checkbox" id="showAllTrades" onchange="window._tradeShowAll=this.checked;window._refreshTradeList&&window._refreshTradeList()">
              <span>显示全部</span>
            </label>
          </div>
        </div>
        <div class="card-body compact">
          <div class="trade-history-list" id="tradeHistoryList">
            <div class="no-data">加载中...</div>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <h3><i class="ri-pie-chart-2-line"></i> 持仓盈亏</h3>
          <div style="display:flex;align-items:center;gap:8px;">
            <span class="badge badge-blue" id="positionSummaryBadge">加载中...</span>
            <button type="button" id="closeAllBtn" class="btn-close-all" title="一键平仓所有持仓">
              <i class="ri-close-circle-line"></i> 一键平仓
            </button>
          </div>
        </div>
        <div class="card-body">
          <div class="pos-list" id="positionList">
            <div class="no-data" style="font-size:13px;">加载中...</div>
          </div>
          <div class="sl-pause-status" id="slPauseStatus"></div>
        </div>
      </div>
    </div>

    <!-- 最强大脑状态 -->
    <div class="card mb superbrain-card" id="superbrainCard" style="display:none;">
      <div class="card-head">
        <h3><i class="ri-brain-line"></i> 最强大脑</h3>
        <span class="badge badge-purple" id="sbSessionBadge">--</span>
      </div>
      <div class="card-body">
        <div class="sb-grid">
          <div class="sb-item">
            <span class="sb-label">市场状态</span>
            <span class="sb-value" id="sbMarketRegime">--</span>
          </div>
          <div class="sb-item">
            <span class="sb-label">BTC方向</span>
            <span class="sb-value" id="sbBtcDirection">--</span>
          </div>
          <div class="sb-item">
            <span class="sb-label">BTC价格</span>
            <span class="sb-value" id="sbBtcPrice">--</span>
          </div>
          <div class="sb-item">
            <span class="sb-label">1h / 4h变化</span>
            <span class="sb-value" id="sbBtcChange">--</span>
          </div>
        </div>
        <div class="sb-position-bar" id="sbPositionBar">
          <div class="sb-bar-label">
            <span>多 <b id="sbLongVal">0</b></span>
            <span id="sbBiasTag" class="sb-bias-tag">--</span>
            <span>空 <b id="sbShortVal">0</b></span>
          </div>
          <div class="sb-bar-track">
            <div class="sb-bar-long" id="sbBarLong" style="width:50%"></div>
          </div>
          <div class="sb-pos-details" id="sbPosDetails"></div>
        </div>
        <div class="sb-streaks" id="sbStreaks"></div>
        <div class="sb-advice" id="sbAdvice"></div>
      </div>
    </div>

    <!-- 今日战绩 + AI 信号准确率（并排） -->
    <div class="grid-2 mb">
      <div class="card">
        <div class="card-head"><h3><i class="ri-line-chart-line"></i> 今日战绩</h3></div>
        <div class="card-body">
          <div class="stats-grid" id="todayStatsGrid">
            <div class="stat-item">
              <div class="stat-number" id="todayTradesNum">0</div>
              <div class="stat-label">今日交易</div>
            </div>
            <div class="stat-item">
              <div class="stat-number" id="todayBuyNum">0</div>
              <div class="stat-label">开仓次数</div>
            </div>
            <div class="stat-item">
              <div class="stat-number" id="todaySellNum">0</div>
              <div class="stat-label">平仓次数</div>
            </div>
            <div class="stat-item">
              <div class="stat-number" id="todayVolumeNum">$0</div>
              <div class="stat-label">今日成交额</div>
            </div>
            <div class="stat-item">
              <div class="stat-number" id="todayTpNum" style="color:var(--green)">0</div>
              <div class="stat-label">止盈次数</div>
            </div>
            <div class="stat-item">
              <div class="stat-number" id="todaySlNum" style="color:var(--red)">0</div>
              <div class="stat-label">止损次数</div>
            </div>
            <div class="stat-item">
              <div class="stat-number" id="todayBlockedNum" style="color:var(--yellow, #f59e0b)">0</div>
              <div class="stat-label" title="因连续止损暂停而被拦截的开仓次数">暂停拦截</div>
            </div>
          </div>
          <div class="trade-section-title">已实现盈亏</div>
          <div class="stats-grid small" id="realizedPnlGrid">
            <div class="stat-item-sm">
              <span class="stat-sm-label">净盈亏</span>
              <span class="stat-sm-value" id="realizedPnlNum">--</span>
            </div>
            <div class="stat-item-sm">
              <span class="stat-sm-label" title="价差毛利：不含手续费和资金费">价差毛利</span>
              <span class="stat-sm-value" id="grossPnlNum">--</span>
            </div>
            <div class="stat-item-sm">
              <span class="stat-sm-label" title="开仓+平仓的交易手续费">手续费</span>
              <span class="stat-sm-value" id="commissionCostNum" style="color:var(--red)">--</span>
            </div>
            <div class="stat-item-sm">
              <span class="stat-sm-label" title="合约持仓资金费率（正=支出，负=收入）">资金费</span>
              <span class="stat-sm-value" id="fundingFeeNum">--</span>
            </div>
            <div class="stat-item-sm">
              <span class="stat-sm-label" title="交易胜率：按已平仓交易统计；净盈亏>0 记为赢（扣除手续费后）。">交易胜率</span>
              <span class="stat-sm-value" id="winRateNum">--</span>
            </div>
            <div class="stat-item-sm">
              <span class="stat-sm-label">盈利/平仓</span>
              <span class="stat-sm-value" id="winClosedNum">--</span>
            </div>
          </div>
          <div class="trade-section-title">累计统计</div>
          <div class="stats-grid small" id="totalStatsGrid">
            <div class="stat-item-sm">
              <span class="stat-sm-label">累计交易</span>
              <span class="stat-sm-value" id="totalTradesNum">--</span>
            </div>
            <div class="stat-item-sm">
              <span class="stat-sm-label">累计成交额</span>
              <span class="stat-sm-value" id="totalVolumeNum">--</span>
            </div>
            <div class="stat-item-sm">
              <span class="stat-sm-label">累计手续费</span>
              <span class="stat-sm-value" id="totalCommissionNum">--</span>
            </div>
            <div class="stat-item-sm">
              <span class="stat-sm-label">最近交易</span>
              <span class="stat-sm-value" id="lastTradeTime">--</span>
            </div>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <h3><i class="ri-focus-3-line"></i> AI 信号准确率</h3>
          <div style="display:flex;gap:10px;align-items:center;">
            <div class="acc-filter-group" id="tradeAccFilterGroup" aria-label="准确率筛选">
              <button type="button" class="acc-filter-btn active" data-days="1">今日</button>
              <button type="button" class="acc-filter-btn" data-days="7">7日</button>
              <button type="button" class="acc-filter-btn" data-days="0">全部</button>
            </div>
            <span class="badge badge-blue" id="accuracyTotalBadge">--</span>
          </div>
        </div>
        <div class="card-body">
          <div class="stats-grid" id="accuracyGrid">
            <div class="stat-item">
              <div class="stat-number" id="accuracyPctNum">--</div>
              <div class="stat-label" title="方向准确率：统计 AI 信号方向是否判断正确（涨/跌方向），不是交易盈利胜率。">方向准确率（信号方向）</div>
            </div>
            <div class="stat-item">
              <div class="stat-number" id="accuracyWeightedNum">--</div>
              <div class="stat-label" title="加权准确率：在方向准确率基础上，对近期信号给予更高权重（时间衰减加权）。">加权准确率（近期更重）</div>
            </div>
            <div class="stat-item">
              <div class="stat-number" id="accuracyCorrectNum">0</div>
              <div class="stat-label">预测正确</div>
            </div>
            <div class="stat-item">
              <div class="stat-number" id="accuracyWrongNum">0</div>
              <div class="stat-label">预测错误</div>
            </div>
          </div>
          <div class="accuracy-by-type" id="accuracyByType"></div>
          <div class="accuracy-by-symbol" id="accuracyBySymbol"></div>
          <div class="accuracy-by-symbol" style="margin-top:10px;">
            <div class="accuracy-section-title">按天准确率变化</div>
            <div class="chart-h chart-h-160">
              <canvas id="tradeAccuracyDailyChart"></canvas>
            </div>
            <div class="text-muted" style="margin-top:6px;font-size:12px;" id="tradeAccuracyDailyHint">--</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 分析流水（由 ai-debate.js initAnalysisFeed 填充） -->
    <div id="tradingFeedSlot"></div>

    <!-- 信号统计 -->
    <div class="card mb" id="signalStatsCard">
      <div class="card-head">
        <h3><i class="ri-bar-chart-2-line"></i> 信号统计</h3>
        <span class="badge badge-blue" id="signalStatsTotalBadge">--</span>
      </div>
      <div class="card-body compact" id="signalStatsBody">
        <div class="skeleton skeleton-line"></div>
      </div>
    </div>

    <!-- 验证度量（双轨/基准/归因） -->
    <div class="card mb">
      <div class="card-head">
        <h3><i class="ri-radar-line"></i> 验证度量（双轨/基准/归因）</h3>
        <span class="badge badge-blue">测试阶段</span>
      </div>
      <div class="card-body">
        <div class="cost-analysis-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:12px">
          <div class="cost-item" style="background:var(--bg2);border-radius:10px;padding:12px;text-align:center">
            <div class="cost-value" id="pfAgreedRate" style="font-size:20px;font-weight:700;color:var(--text)">--</div>
            <div class="cost-label" style="font-size:11px;color:var(--text3);margin-top:4px">预筛一致率(%)</div>
          </div>
          <div class="cost-item" style="background:var(--bg2);border-radius:10px;padding:12px;text-align:center">
            <div class="cost-value" id="pfStrongCount" style="font-size:20px;font-weight:700;color:var(--text)">--</div>
            <div class="cost-label" style="font-size:11px;color:var(--text3);margin-top:4px">预筛STRONG数量</div>
          </div>
          <div class="cost-item" style="background:var(--bg2);border-radius:10px;padding:12px;text-align:center">
            <div class="cost-value" id="benchBtc" style="font-size:20px;font-weight:700;color:var(--text)">--</div>
            <div class="cost-label" style="font-size:11px;color:var(--text3);margin-top:4px">BTC累计涨跌(%)</div>
          </div>
        </div>
        <div class="metrics-summary" style="display:flex;flex-direction:column;gap:8px">
          <div class="metric-item" style="display:flex;justify-content:space-between;align-items:center">
            <span class="metric-label" style="font-size:12px;color:var(--text3)">策略累计净盈亏(USDT)</span>
            <span class="metric-value" id="benchStrategy" style="font-size:14px;font-weight:700;color:var(--text)">--</span>
          </div>
          <div class="metric-item" style="display:flex;justify-content:space-between;align-items:center">
            <span class="metric-label" style="font-size:12px;color:var(--text3)">最准角色(近14天)</span>
            <span class="metric-value" id="topRoleAcc" style="font-size:14px;font-weight:700;color:var(--text)">--</span>
          </div>
          <div class="metric-item" style="display:flex;justify-content:space-between;align-items:center">
            <span class="metric-label" style="font-size:12px;color:var(--text3)">最佳币种(近14天)</span>
            <span class="metric-value" id="topSymbolAcc" style="font-size:14px;font-weight:700;color:var(--text)">--</span>
          </div>
        </div>
        <div class="health-timestamp" id="validationTimestamp" style="font-size:11px;color:var(--text3);margin-top:8px;text-align:center">--</div>
      </div>
    </div>

    <!-- 策略配置（独占一行） -->
    <div class="card mb">
      <div class="card-head"><h3><i class="ri-settings-3-line"></i> 策略配置</h3></div>
      <div class="card-body">
        <div class="strategy-info" id="strategyInfo">
          <div class="strategy-name" id="strategyName">加载中...</div>
          <div class="strategy-items">
            <div class="strategy-item">
              <span class="strategy-icon"><i class="ri-money-dollar-circle-line"></i></span>
              <div class="strategy-detail">
                <div class="strategy-item-label">每单金额</div>
                <div class="strategy-item-value" id="stratAmountText">--</div>
              </div>
            </div>
            <div class="strategy-item">
              <span class="strategy-icon"><i class="ri-focus-3-line"></i></span>
              <div class="strategy-detail">
                <div class="strategy-item-label">置信度门槛</div>
                <div class="strategy-item-value" id="stratConfText">--</div>
              </div>
            </div>
            <div class="strategy-item">
              <span class="strategy-icon"><i class="ri-timer-line"></i></span>
              <div class="strategy-detail">
                <div class="strategy-item-label">冷却时间</div>
                <div class="strategy-item-value" id="stratCooldownText">--</div>
              </div>
            </div>
            <div class="strategy-item">
              <span class="strategy-icon"><i class="ri-refresh-line"></i></span>
              <div class="strategy-detail">
                <div class="strategy-item-label">分析频率</div>
                <div class="strategy-item-value" id="stratIntervalText">--</div>
              </div>
            </div>
            <div class="strategy-item">
              <span class="strategy-icon"><i class="ri-forbid-line"></i></span>
              <div class="strategy-detail">
                <div class="strategy-item-label">单币种持仓上限</div>
                <div class="strategy-item-value" id="stratMaxPosText">--</div>
              </div>
            </div>
            <div class="strategy-item">
              <span class="strategy-icon"><i class="ri-calendar-check-line"></i></span>
              <div class="strategy-detail">
                <div class="strategy-item-label">每日交易限额</div>
                <div class="strategy-item-value" id="stratDailyLimitText">--</div>
              </div>
            </div>
            <div class="strategy-item">
              <span class="strategy-icon"><i class="ri-crosshair-2-line"></i></span>
              <div class="strategy-detail">
                <div class="strategy-item-label">止盈 / 止损</div>
                <div class="strategy-item-value" id="stratTpSlText">--</div>
              </div>
            </div>
            <div class="strategy-item">
              <span class="strategy-icon"><i class="ri-scales-3-line"></i></span>
              <div class="strategy-detail">
                <div class="strategy-item-label">杠杆 / 保证金</div>
                <div class="strategy-item-value" id="stratLeverageText">--</div>
              </div>
            </div>
            <div class="strategy-item">
              <span class="strategy-icon"><i class="ri-shield-check-line"></i></span>
              <div class="strategy-detail">
                <div class="strategy-item-label">移动止损</div>
                <div class="strategy-item-value" id="stratTrailingText">--</div>
              </div>
            </div>
            <div class="strategy-item">
              <span class="strategy-icon"><i class="ri-hourglass-line"></i></span>
              <div class="strategy-detail">
                <div class="strategy-item-label">持仓超时</div>
                <div class="strategy-item-value" id="stratTimeoutText">--</div>
              </div>
            </div>
            <div class="strategy-item strategy-item-wide">
              <span class="strategy-icon"><i class="ri-coin-line"></i></span>
              <div class="strategy-detail">
                <div class="strategy-item-label">交易币种</div>
                <div class="strategy-item-value" id="stratSymbolsText">--</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 引擎状态 -->
    <div class="card mb" id="engineStatusCard" style="display:none;">
      <div class="card-head">
        <h3><i class="ri-dashboard-3-line"></i> 引擎状态</h3>
      </div>
      <div class="card-body">
        <div class="engine-status-grid" id="engineStatusGrid">加载中...</div>
      </div>
    </div>

    <!-- 资产净值 + 策略对比（并排） -->
    <div class="grid-2 mb">
      <div class="card">
        <div class="card-head"><h3><i class="ri-line-chart-line"></i> 资产净值曲线</h3></div>
        <div class="card-body pnl-chart-wrap">
          <canvas id="dailyPnlChart"></canvas>
          <div class="no-data" id="dailyPnlEmpty" style="display:none;font-size:12px;">暂无数据</div>
        </div>
      </div>
      <div class="card">
        <div class="card-head"><h3><i class="ri-bar-chart-grouped-line"></i> 策略 vs BTC</h3></div>
        <div class="card-body pnl-chart-wrap">
          <canvas id="benchmarkChart"></canvas>
          <div class="no-data" id="benchmarkEmpty" style="display:none;font-size:12px;">暂无数据</div>
        </div>
      </div>
    </div>


  `;
}
