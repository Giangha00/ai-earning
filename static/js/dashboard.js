// AI Earning Trading Terminal - Frontend Logic
let mainChart = null;
let candleSeries = null;
let volumeSeries = null;
let sma20Series = null;
let sma50Series = null;

let rsiChart = null;
let rsiSeries = null;

let currentSymbol = "EURUSD";
let currentTimeframe = "M5";
let lastCandleData = [];

document.addEventListener("DOMContentLoaded", () => {
  initCharts();
  initTabs();
  initControls();
  loadAllData();

  // Auto refresh live data every 10 seconds
  setInterval(() => {
    loadAccountData();
    loadTablesData();
  }, 10000);
});

// 1. Initialize TradingView Charts
function initCharts() {
  const chartContainer = document.getElementById("chart-container");
  const rsiContainer = document.getElementById("rsi-container");

  // Chart configuration
  const chartOptions = {
    layout: {
      background: { color: "#0a0d14" },
      textColor: "#94a3b8",
      fontSize: 12,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    },
    grid: {
      vertLines: { color: "rgba(255, 255, 255, 0.04)" },
      horzLines: { color: "rgba(255, 255, 255, 0.04)" },
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: {
        color: "rgba(6, 182, 212, 0.4)",
        width: 1,
        style: LightweightCharts.LineStyle.Dashed,
      },
      horzLine: {
        color: "rgba(6, 182, 212, 0.4)",
        width: 1,
        style: LightweightCharts.LineStyle.Dashed,
      },
    },
    timeScale: {
      borderColor: "rgba(255, 255, 255, 0.08)",
      timeVisible: true,
      secondsVisible: false,
    },
    rightPriceScale: {
      borderColor: "rgba(255, 255, 255, 0.08)",
      autoScale: true,
    },
  };

  // Create Main Chart
  mainChart = LightweightCharts.createChart(chartContainer, chartOptions);

  // Candlestick Series
  candleSeries = mainChart.addCandlestickSeries({
    upColor: "#10b981",
    downColor: "#f43f5e",
    borderUpColor: "#10b981",
    borderDownColor: "#f43f5e",
    wickUpColor: "#10b981",
    wickDownColor: "#f43f5e",
  });

  // Volume Series
  volumeSeries = mainChart.addHistogramSeries({
    priceFormat: { type: "volume" },
    priceScaleId: "",
    scaleMargins: {
      top: 0.8,
      bottom: 0,
    },
  });

  // SMA 20 Series
  sma20Series = mainChart.addLineSeries({
    color: "#06b6d4",
    lineWidth: 1.5,
    title: "SMA 20",
  });

  // SMA 50 Series
  sma50Series = mainChart.addLineSeries({
    color: "#f59e0b",
    lineWidth: 1.5,
    title: "SMA 50",
  });

  // Create RSI Sub-Chart
  const rsiOptions = {
    ...chartOptions,
    rightPriceScale: {
      borderColor: "rgba(255, 255, 255, 0.08)",
      scaleMargins: { top: 0.1, bottom: 0.1 },
    },
  };
  rsiChart = LightweightCharts.createChart(rsiContainer, rsiOptions);

  rsiSeries = rsiChart.addLineSeries({
    color: "#a855f7",
    lineWidth: 1.5,
    title: "RSI 14",
  });

  // RSI Overbought (70) and Oversold (30) lines
  rsiSeries.createPriceLine({
    price: 70,
    color: "rgba(244, 63, 94, 0.6)",
    lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    axisLabelVisible: true,
    title: "Overbought (70)",
  });
  rsiSeries.createPriceLine({
    price: 30,
    color: "rgba(16, 185, 129, 0.6)",
    lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    axisLabelVisible: true,
    title: "Oversold (30)",
  });

  // Synchronize time scales
  mainChart.timeScale().subscribeVisibleLogicalRangeChange(range => {
    if (range) rsiChart.timeScale().setVisibleLogicalRange(range);
  });
  rsiChart.timeScale().subscribeVisibleLogicalRangeChange(range => {
    if (range) mainChart.timeScale().setVisibleLogicalRange(range);
  });

  // Crosshair Legend update
  mainChart.subscribeCrosshairMove(param => {
    if (!param || !param.time || !param.seriesData.get(candleSeries)) {
      updateLegendWithLastCandle();
      return;
    }
    const candle = param.seriesData.get(candleSeries);
    const vol = param.seriesData.get(volumeSeries);
    displayCandleLegend(candle, vol ? vol.value : 0, param.time);
  });

  // Handle Window Resize
  window.addEventListener("resize", () => {
    mainChart.applyOptions({ width: chartContainer.clientWidth });
    rsiChart.applyOptions({ width: rsiContainer.clientWidth });
  });
}

function displayCandleLegend(candle, volume, timestamp) {
  const dateStr = new Date(timestamp * 1000).toLocaleString("vi-VN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });

  const change = candle.close - candle.open;
  const pct = (change / candle.open) * 100;
  const isPos = change >= 0;

  document.getElementById("legend-time").innerText = dateStr;
  document.getElementById("legend-open").innerText = candle.open.toFixed(5);
  document.getElementById("legend-high").innerText = candle.high.toFixed(5);
  document.getElementById("legend-low").innerText = candle.low.toFixed(5);
  document.getElementById("legend-close").innerText = candle.close.toFixed(5);

  const changeEl = document.getElementById("legend-change");
  changeEl.innerText = `${isPos ? "+" : ""}${change.toFixed(5)} (${isPos ? "+" : ""}${pct.toFixed(2)}%)`;
  changeEl.style.color = isPos ? "#10b981" : "#f43f5e";

  document.getElementById("legend-vol").innerText = Number(volume).toLocaleString();
}

function updateLegendWithLastCandle() {
  if (lastCandleData.length === 0) return;
  const last = lastCandleData[lastCandleData.length - 1];
  displayCandleLegend(last, 0, last.time);
}

// 2. Fetch and Load All Data
async function loadAllData() {
  await Promise.all([
    loadAccountData(),
    loadCandleData(),
    loadTablesData()
  ]);
}

async function loadAccountData() {
  try {
    const res = await fetch("/api/account");
    const data = await res.json();

    const badge = document.getElementById("connection-badge");
    const badgeText = document.getElementById("connection-text");

    if (data.is_simulation) {
      badge.className = "status-badge simulation";
      badgeText.innerText = `Giả lập MT5 • ${data.server} (#${data.login})`;
    } else {
      badge.className = "status-badge";
      badgeText.innerText = `MT5 Đã kết nối • ${data.server} (#${data.login})`;
    }

    document.getElementById("account-currency").innerText = data.currency;
    document.getElementById("val-balance").innerText = `$${Number(data.balance).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
    document.getElementById("val-equity").innerText = `$${Number(data.equity).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;

    const flPnl = Number(data.floating_pnl);
    const flBadge = document.getElementById("floating-badge");
    flBadge.innerText = `${flPnl >= 0 ? "+" : ""}$${flPnl.toFixed(2)}`;
    flBadge.className = `badge ${flPnl >= 0 ? "badge-buy" : "badge-sell"}`;
    document.getElementById("floating-desc").innerText = `PnL thả nổi: ${flPnl >= 0 ? "+" : ""}$${flPnl.toFixed(2)}`;

    document.getElementById("val-winrate").innerText = `${data.win_rate}%`;
    document.getElementById("val-trades-count").innerText = `Tổng ${data.closed_trades} lệnh đã đóng`;

    const realizedProfit = Number(data.total_profit);
    const realizedEl = document.getElementById("val-realized-profit");
    realizedEl.innerText = `${realizedProfit >= 0 ? "+" : ""}$${realizedProfit.toFixed(2)}`;
    realizedEl.className = `metric-value ${realizedProfit >= 0 ? "text-green" : "text-red"}`;

    document.getElementById("val-leverage").innerText = `Đòn bẩy: 1:${data.leverage}`;
  } catch (err) {
    console.error("Lỗi tải thông tin tài khoản:", err);
  }
}

async function loadCandleData() {
  try {
    const res = await fetch(`/api/candles?symbol=${currentSymbol}&timeframe=${currentTimeframe}&limit=1200`);
    const data = await res.json();

    if (!data.candles || data.candles.length === 0) return;

    lastCandleData = data.candles;
    candleSeries.setData(data.candles);
    volumeSeries.setData(data.volume);
    sma20Series.setData(data.sma20);
    sma50Series.setData(data.sma50);
    rsiSeries.setData(data.rsi);

    mainChart.timeScale().fitContent();
    rsiChart.timeScale().fitContent();

    updateLegendWithLastCandle();
  } catch (err) {
    console.error("Lỗi tải nến Parquet:", err);
  }
}

async function loadTablesData() {
  loadSignals();
  loadOrders();
  loadEquity();
  loadLogs();
  loadFiles();
}

async function loadSignals() {
  try {
    const res = await fetch("/api/signals");
    const signals = await res.json();
    document.getElementById("count-signals").innerText = signals.length;

    const tbody = document.getElementById("tbody-signals");
    if (signals.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: var(--text-muted);">Chưa có tín hiệu nào</td></tr>`;
      return;
    }

    tbody.innerHTML = signals.map(s => {
      const typeBadge = s.signal_type === "BUY" ? "badge-buy" : (s.signal_type === "SELL" ? "badge-sell" : "badge-hold");
      return `
        <tr>
          <td>#${s.id}</td>
          <td>${s.timestamp}</td>
          <td><strong>${s.symbol}</strong></td>
          <td><span class="badge ${typeBadge}">${s.signal_type}</span></td>
          <td>
            <div class="conf-bar"><div class="conf-fill" style="width: ${s.confidence || 0}%;"></div></div>
            <span>${(s.confidence || 0).toFixed(1)}%</span>
          </td>
          <td style="color: ${s.rsi_value < 30 ? 'var(--color-green)' : (s.rsi_value > 70 ? 'var(--color-red)' : 'inherit')}">${(s.rsi_value || 0).toFixed(1)}</td>
          <td>${(s.atr_value || 0).toFixed(4)}</td>
          <td>${(s.adx_value || 0).toFixed(1)}</td>
          <td>${s.executed ? '<span class="text-green">✓ Khớp lệnh</span>' : '<span class="text-muted">Chờ</span>'}</td>
          <td>${s.order_ticket ? `<span class="text-cyan">#${s.order_ticket}</span>` : '--'}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error(err);
  }
}

async function loadOrders() {
  try {
    const res = await fetch("/api/orders");
    const orders = await res.json();
    document.getElementById("count-orders").innerText = orders.length;

    const tbody = document.getElementById("tbody-orders");
    if (orders.length === 0) {
      tbody.innerHTML = `<tr><td colspan="12" style="text-align: center; color: var(--text-muted);">Chưa có lệnh giao dịch nào</td></tr>`;
      return;
    }

    tbody.innerHTML = orders.map(o => {
      const isBuy = o.order_type === "BUY";
      const isClosed = o.status === "CLOSED";
      const pnl = Number(o.profit || 0);
      return `
        <tr>
          <td><strong class="text-cyan">#${o.ticket_id}</strong></td>
          <td>${o.symbol}</td>
          <td><span class="badge ${isBuy ? "badge-buy" : "badge-sell"}">${o.order_type}</span></td>
          <td>${o.lot_size.toFixed(2)}</td>
          <td>${o.open_time}</td>
          <td>${o.open_price.toFixed(5)}</td>
          <td>${o.close_price ? o.close_price.toFixed(5) : '--'}</td>
          <td>${o.stop_loss ? o.stop_loss.toFixed(5) : '--'}</td>
          <td>${o.take_profit ? o.take_profit.toFixed(5) : '--'}</td>
          <td class="${pnl >= 0 ? 'text-green' : 'text-red'}"><strong>${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</strong></td>
          <td>${o.close_reason || '--'}</td>
          <td><span class="badge ${isClosed ? "badge-hold" : "badge-buy"}">${o.status}</span></td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error(err);
  }
}

async function loadEquity() {
  try {
    const res = await fetch("/api/equity");
    const equity = await res.json();
    document.getElementById("count-equity").innerText = equity.length;

    const tbody = document.getElementById("tbody-equity");
    if (equity.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">Chưa có dữ liệu</td></tr>`;
      return;
    }

    tbody.innerHTML = equity.map(e => `
      <tr>
        <td><strong>${e.date}</strong></td>
        <td>$${Number(e.balance).toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
        <td class="text-green">$${Number(e.equity).toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
        <td>${Number(e.floating_pnl) >= 0 ? '+' : ''}$${Number(e.floating_pnl).toFixed(2)}</td>
        <td>${e.total_trades}</td>
        <td>${e.win_trades}</td>
      </tr>
    `).join("");
  } catch (err) {
    console.error(err);
  }
}

async function loadLogs() {
  try {
    const res = await fetch("/api/logs");
    const logs = await res.json();
    document.getElementById("count-logs").innerText = logs.length;

    const container = document.getElementById("log-container");
    if (logs.length === 0) {
      container.innerHTML = `<div style="padding: 20px; color: var(--text-muted);">Không có nhật ký</div>`;
      return;
    }

    container.innerHTML = logs.map(l => {
      const levelColor = l.log_level === "ERROR" ? "text-red" : (l.log_level === "WARNING" ? "text-amber" : "text-green");
      return `
        <div class="log-item">
          <span class="log-time">[${l.timestamp}]</span>
          <span class="${levelColor}">[${l.log_level}]</span>
          <span class="log-module">${l.module}:</span>
          <span class="log-msg">${l.message}</span>
        </div>
      `;
    }).join("");
  } catch (err) {
    console.error(err);
  }
}

async function loadFiles() {
  try {
    const res = await fetch("/api/files");
    const files = await res.json();
    document.getElementById("count-files").innerText = files.length;

    const tbody = document.getElementById("tbody-files");
    if (files.length === 0) {
      tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-muted);">Chưa có tệp nén nào trong data/</td></tr>`;
      return;
    }

    tbody.innerHTML = files.map(f => `
      <tr>
        <td><strong class="text-cyan">${f.name}</strong></td>
        <td>${f.size_mb} MB</td>
        <td>${f.modified}</td>
      </tr>
    `).join("");
  } catch (err) {
    console.error(err);
  }
}

// 3. UI Controls and Tab Switching
function initTabs() {
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabContents = document.querySelectorAll(".tab-content");

  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      tabBtns.forEach(b => b.classList.remove("active"));
      tabContents.forEach(c => c.classList.remove("active"));

      btn.classList.add("active");
      const target = document.getElementById(btn.dataset.tab);
      if (target) target.classList.add("active");
    });
  });
}

function initControls() {
  // Refresh button
  document.getElementById("btn-refresh").addEventListener("click", () => {
    loadAllData();
  });

  // Timeframe buttons
  const tfBtns = document.querySelectorAll(".tf-btn");
  tfBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      tfBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentTimeframe = btn.dataset.tf;
      document.getElementById("active-tf").innerText = currentTimeframe;
      loadCandleData();
    });
  });

  // Indicator Toggles
  document.getElementById("toggle-sma20").addEventListener("change", (e) => {
    sma20Series.applyOptions({ visible: e.target.checked });
  });

  document.getElementById("toggle-sma50").addEventListener("change", (e) => {
    sma50Series.applyOptions({ visible: e.target.checked });
  });

  document.getElementById("toggle-vol").addEventListener("change", (e) => {
    volumeSeries.applyOptions({ visible: e.target.checked });
  });

  document.getElementById("toggle-rsi").addEventListener("change", (e) => {
    const rsiCont = document.getElementById("rsi-container");
    rsiCont.style.display = e.target.checked ? "block" : "none";
  });
}
