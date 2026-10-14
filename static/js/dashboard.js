// AI Earning Trading Terminal - Dashboard Logic
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
let latestMarketPrice = 1.08500;
let allOrders = [];
let currentOrderFilter = "ALL";
let usdToVndRate = 25450;

document.addEventListener("DOMContentLoaded", () => {
  initCharts();
  initOrderForm();
  initTabs();
  initControls();
  loadAllData();

  // Auto-refresh interval
  setInterval(() => {
    loadAccountData();
    loadOrdersSidebar();
  }, 8000);
});

// 1. Initialize TradingView Lightweight Charts
function initCharts() {
  const chartContainer = document.getElementById("chart-container");
  const rsiContainer = document.getElementById("rsi-container");

  const chartOptions = {
    layout: {
      background: { color: "#090d16" },
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

  // Main Candlestick Chart
  mainChart = LightweightCharts.createChart(chartContainer, chartOptions);

  candleSeries = mainChart.addCandlestickSeries({
    upColor: "#10b981",
    downColor: "#f43f5e",
    borderUpColor: "#10b981",
    borderDownColor: "#f43f5e",
    wickUpColor: "#10b981",
    wickDownColor: "#f43f5e",
  });

  volumeSeries = mainChart.addHistogramSeries({
    priceFormat: { type: "volume" },
    priceScaleId: "",
    scaleMargins: { top: 0.8, bottom: 0 },
  });

  sma20Series = mainChart.addLineSeries({
    color: "#06b6d4",
    lineWidth: 1.5,
    title: "SMA 20",
  });

  sma50Series = mainChart.addLineSeries({
    color: "#f59e0b",
    lineWidth: 1.5,
    title: "SMA 50",
  });

  // RSI Sub-chart
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

  rsiSeries.createPriceLine({
    price: 70,
    color: "rgba(244, 63, 94, 0.6)",
    lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    axisLabelVisible: true,
    title: "70",
  });
  rsiSeries.createPriceLine({
    price: 30,
    color: "rgba(16, 185, 129, 0.6)",
    lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    axisLabelVisible: true,
    title: "30",
  });

  // Synchronize time scales
  mainChart.timeScale().subscribeVisibleLogicalRangeChange(range => {
    if (range) rsiChart.timeScale().setVisibleLogicalRange(range);
  });
  rsiChart.timeScale().subscribeVisibleLogicalRangeChange(range => {
    if (range) mainChart.timeScale().setVisibleLogicalRange(range);
  });

  // Crosshair Legend
  mainChart.subscribeCrosshairMove(param => {
    if (!param || !param.time || !param.seriesData.get(candleSeries)) {
      updateLegendWithLastCandle();
      return;
    }
    const candle = param.seriesData.get(candleSeries);
    const vol = param.seriesData.get(volumeSeries);
    displayCandleLegend(candle, vol ? vol.value : 0, param.time);
  });

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

// 2. Fetch Data
async function loadAllData() {
  await Promise.all([
    loadAccountData(),
    loadCandleData(),
    loadOrdersSidebar(),
    loadSecondaryTables()
  ]);
}

async function loadAccountData() {
  try {
    const res = await fetch("/api/account");
    const data = await res.json();

    if (data.usd_vnd_rate) {
      usdToVndRate = data.usd_vnd_rate;
    }

    const badge = document.getElementById("connection-badge");
    const badgeText = document.getElementById("connection-text");

    if (data.is_simulation) {
      badge.className = "status-badge simulation";
      badgeText.innerText = `Giả lập MT5 • ${data.server} (#${data.login})`;
    } else {
      badge.className = "status-badge";
      badgeText.innerText = `MT5 Đã kết nối • ${data.server} (#${data.login})`;
    }

    // Hiển thị số dư trong ví dạng VNĐ (Dưới chart)
    const balVnd = Number(data.balance_vnd || (data.balance * usdToVndRate));
    document.getElementById("wallet-balance-vnd").innerText = `${balVnd.toLocaleString("vi-VN")} ₫`;
    document.getElementById("wallet-balance-usd").innerText = `$${Number(data.balance).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;

    const eqVnd = Number(data.equity_vnd || (data.equity * usdToVndRate));
    document.getElementById("wallet-equity-vnd").innerText = `${eqVnd.toLocaleString("vi-VN")} ₫`;
    document.getElementById("wallet-equity-usd").innerText = `$${Number(data.equity).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;

    const flVnd = Number(data.floating_pnl_vnd || (data.floating_pnl * usdToVndRate));
    const flVndEl = document.getElementById("wallet-floating-vnd");
    flVndEl.innerText = `${flVnd >= 0 ? "+" : ""}${flVnd.toLocaleString("vi-VN")} ₫`;
    flVndEl.style.color = flVnd >= 0 ? "var(--color-green)" : "var(--color-red)";

    document.getElementById("wallet-leverage").innerText = `1:${data.leverage}`;
    document.getElementById("wallet-winrate").innerText = `${data.win_rate}%`;

    const realizedVnd = Number(data.total_profit_vnd || (data.total_profit * usdToVndRate));
    const realizedEl = document.getElementById("wallet-realized-vnd");
    realizedEl.innerText = `${realizedVnd >= 0 ? "+" : ""}${realizedVnd.toLocaleString("vi-VN")} ₫`;
    realizedEl.style.color = realizedVnd >= 0 ? "var(--color-gold)" : "var(--color-red)";

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

    latestMarketPrice = data.latest_price || data.candles[data.candles.length - 1].close;

    // Cập nhật giá mẫu vào ô nhập lệnh quy đổi ra VNĐ nếu người dùng chưa sửa
    const entryInput = document.getElementById("input-entry-price-vnd");
    if (entryInput && !entryInput.dataset.modified) {
      const entryVnd = Math.round(latestMarketPrice * usdToVndRate);
      entryInput.value = entryVnd;
      const targetInput = document.getElementById("input-target-price-vnd");
      if (targetInput && !targetInput.dataset.modified) {
        targetInput.value = Math.round((latestMarketPrice + 0.0040) * usdToVndRate);
      }
      recalcEstimatedProfit();
    }

    updateLegendWithLastCandle();
  } catch (err) {
    console.error("Lỗi tải nến Parquet:", err);
  }
}

// 3. Lịch Sử Các Lệnh AI Đã Đánh (Bên Cạnh Chart)
async function loadOrdersSidebar() {
  try {
    const res = await fetch("/api/orders");
    allOrders = await res.json();
    renderOrdersFeed();
  } catch (err) {
    console.error("Lỗi tải danh sách lệnh AI:", err);
  }
}

function renderOrdersFeed() {
  const feed = document.getElementById("orders-feed");
  document.getElementById("sidebar-order-count").innerText = allOrders.length;

  let filtered = allOrders;
  if (currentOrderFilter === "OPEN") {
    filtered = allOrders.filter(o => o.status === "OPEN");
  } else if (currentOrderFilter === "CLOSED") {
    filtered = allOrders.filter(o => o.status === "CLOSED");
  }

  if (filtered.length === 0) {
    feed.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 30px;">Chưa có lệnh thật nào. Hãy đặt lệnh ở bảng bên dưới!</div>`;
    return;
  }

  feed.innerHTML = filtered.map(o => {
    const isBuy = o.order_type === "BUY";
    const isOpen = o.status === "OPEN";
    const pnlUsd = Number(o.profit_usd || o.profit || 0);
    const pnlVnd = Number(o.profit_vnd || (pnlUsd * usdToVndRate));
    const isWin = pnlUsd > 0;

    const openVnd = Math.round(o.open_price_vnd || (o.open_price * usdToVndRate));
    const targetVnd = o.take_profit ? Math.round(o.take_profit_vnd || (o.take_profit * usdToVndRate)) : null;
    const closeVnd = o.close_price ? Math.round(o.close_price_vnd || (o.close_price * usdToVndRate)) : null;

    let cardClass = "order-item-card";
    if (isOpen) cardClass += " is-open";
    else if (isWin) cardClass += " is-win";
    else cardClass += " is-loss";

    return `
      <div class="${cardClass}">
        <div class="order-item-header">
          <span class="order-ticket">#${o.ticket_id} • <strong>${o.symbol}</strong></span>
          <span class="order-type-badge ${isBuy ? 'badge-buy' : 'badge-sell'}">
            ${isBuy ? 'BUY' : 'SELL'} ${o.lot_size.toFixed(2)} lot
          </span>
        </div>

        <div class="order-details-grid">
          <div class="order-detail-field">Giá vào (VNĐ): <span>${openVnd.toLocaleString("vi-VN")} ₫</span></div>
          <div class="order-detail-field">Mục tiêu (VNĐ): <span>${targetVnd ? targetVnd.toLocaleString("vi-VN") + ' ₫' : '--'}</span></div>
          <div class="order-detail-field">Giá chốt (VNĐ): <span>${closeVnd ? closeVnd.toLocaleString("vi-VN") + ' ₫' : 'Đang chạy'}</span></div>
          <div class="order-detail-field">Thời gian: <span>${o.open_time.split(" ")[1] || o.open_time}</span></div>
        </div>

        <div class="order-pnl-row">
          <div>
            <div class="order-pnl-usd ${pnlUsd >= 0 ? 'text-green' : 'text-red'}">
              ${pnlVnd >= 0 ? '+' : ''}${pnlVnd.toLocaleString("vi-VN")} ₫
            </div>
            <div class="order-pnl-vnd" style="color: var(--text-muted); font-size: 11px;">
              Quy đổi: ${pnlUsd >= 0 ? '+' : ''}$${pnlUsd.toFixed(2)}
            </div>
          </div>
          <div>
            ${isOpen ? `
              <button class="btn-close-order" onclick="handleCloseOrder(${o.ticket_id})">
                Chốt lệnh ngay
              </button>
            ` : `
              <span class="badge badge-hold">${o.close_reason || 'CLOSED'}</span>
            `}
          </div>
        </div>
      </div>
    `;
  }).join("");
}

window.handleCloseOrder = async function(ticketId) {
  try {
    const res = await fetch(`/api/orders/close/${ticketId}`, { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast(`✓ Đã chốt lệnh #${ticketId} thành công (+${data.profit.toFixed(2)} USD)`);
      loadAccountData();
      loadOrdersSidebar();
    }
  } catch (err) {
    showToast(`❌ Lỗi chốt lệnh: ${err.message}`);
  }
};

// 4. Order Input & Profit Calculation Logic (VNĐ)
function initOrderForm() {
  const entryInput = document.getElementById("input-entry-price-vnd");
  const lotInput = document.getElementById("input-lot-size");
  const targetInput = document.getElementById("input-target-price-vnd");

  if (entryInput) {
    entryInput.addEventListener("input", () => {
      entryInput.dataset.modified = "true";
      recalcEstimatedProfit();
    });
  }

  if (targetInput) {
    targetInput.addEventListener("input", () => {
      targetInput.dataset.modified = "true";
      recalcEstimatedProfit();
    });
  }

  if (lotInput) {
    lotInput.addEventListener("input", recalcEstimatedProfit);
  }

  // Quick fill current price
  const fillBtn = document.getElementById("btn-fill-current-price");
  if (fillBtn) {
    fillBtn.addEventListener("click", () => {
      const entryVnd = Math.round(latestMarketPrice * usdToVndRate);
      entryInput.value = entryVnd;
      targetInput.value = Math.round((latestMarketPrice + 0.0040) * usdToVndRate);
      recalcEstimatedProfit();
      showToast(`Đã lấy giá thị trường hiện tại: ${entryVnd.toLocaleString("vi-VN")} ₫`);
    });
  }

  // Lot quick chips
  const lotChips = document.querySelectorAll(".lot-chip");
  lotChips.forEach(chip => {
    chip.addEventListener("click", () => {
      lotChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      lotInput.value = chip.dataset.lot;
      recalcEstimatedProfit();
    });
  });

  // Order submission
  const buyBtn = document.getElementById("btn-submit-buy");
  const sellBtn = document.getElementById("btn-submit-sell");
  if (buyBtn) buyBtn.addEventListener("click", () => executeOrder("BUY"));
  if (sellBtn) sellBtn.addEventListener("click", () => executeOrder("SELL"));

  // Initial calculation
  recalcEstimatedProfit();
}

function recalcEstimatedProfit() {
  const entryVndInput = document.getElementById("input-entry-price-vnd");
  const targetVndInput = document.getElementById("input-target-price-vnd");
  const lotInput = document.getElementById("input-lot-size");

  if (!entryVndInput || !targetVndInput || !lotInput) return;

  const entryVnd = parseFloat(entryVndInput.value) || 0;
  const targetVnd = parseFloat(targetVndInput.value) || 0;
  const lot = parseFloat(lotInput.value) || 0;

  const entryForex = entryVnd / usdToVndRate;
  const targetForex = targetVnd / usdToVndRate;

  const subEntry = document.getElementById("sub-entry-forex");
  const subTarget = document.getElementById("sub-target-forex");
  if (subEntry) subEntry.innerText = entryForex > 0 ? entryForex.toFixed(5) : "--";
  if (subTarget) subTarget.innerText = targetForex > 0 ? targetForex.toFixed(5) : "--";

  if (entryVnd <= 0 || targetVnd <= 0 || lot <= 0) {
    document.getElementById("calc-pips-dist").innerText = "0 pips";
    document.getElementById("calc-profit-usd").innerText = "$0.00";
    document.getElementById("calc-profit-vnd").innerText = "0 ₫";
    return;
  }

  const diffForex = Math.abs(targetForex - entryForex);
  const pips = diffForex * 10000;
  // EURUSD 1 lot = $10 per pip
  const profitUsd = pips * lot * 10;
  const profitVnd = profitUsd * usdToVndRate;

  document.getElementById("calc-pips-dist").innerText = `Mục tiêu: +${pips.toFixed(1)} pips`;
  document.getElementById("calc-profit-usd").innerText = `+$${profitUsd.toFixed(2)}`;
  document.getElementById("calc-profit-vnd").innerText = `+${Math.round(profitVnd).toLocaleString("vi-VN")} ₫`;
}

async function executeOrder(orderType) {
  const entryVnd = parseFloat(document.getElementById("input-entry-price-vnd").value);
  const lot = parseFloat(document.getElementById("input-lot-size").value);
  const targetVnd = parseFloat(document.getElementById("input-target-price-vnd").value);

  if (!entryVnd || !lot || !targetVnd) {
    showToast("Vui lòng điền đầy đủ mức giá muốn đánh (VNĐ), số lot và mức giá mong muốn (VNĐ)");
    return;
  }

  const entryForex = entryVnd / usdToVndRate;
  const targetForex = targetVnd / usdToVndRate;

  try {
    const res = await fetch("/api/orders/place", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: currentSymbol,
        order_type: orderType,
        lot_size: lot,
        entry_price: entryForex,
        entry_price_vnd: entryVnd,
        target_price: targetForex,
        target_price_vnd: targetVnd
      })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`✓ AI đã khớp lệnh ${orderType} ${lot} lot tại ${entryVnd.toLocaleString("vi-VN")} ₫ (#${data.ticket_id})`);
      loadAccountData();
      loadOrdersSidebar();
      loadSecondaryTables();
    } else {
      showToast(`❌ ${data.detail || "Không thể đặt lệnh"}`);
    }
  } catch (err) {
    showToast(`❌ Lỗi kết nối: ${err.message}`);
  }
}

// 5. Sidebar Filter and Secondary Tabs
function initControls() {
  document.getElementById("btn-refresh").addEventListener("click", () => {
    loadAllData();
    showToast("Đã làm mới dữ liệu toàn hệ thống");
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

  // Sidebar Filter buttons
  const filterBtns = document.querySelectorAll(".filter-btn");
  filterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      filterBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentOrderFilter = btn.dataset.filter;
      renderOrdersFeed();
    });
  });
}

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

async function loadSecondaryTables() {
  loadSignals();
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
          <td>${(s.confidence || 0).toFixed(1)}%</td>
          <td style="color: ${s.rsi_value < 30 ? 'var(--color-green)' : (s.rsi_value > 70 ? 'var(--color-red)' : 'inherit')}">${(s.rsi_value || 0).toFixed(1)}</td>
          <td>${(s.atr_value || 0).toFixed(4)}</td>
          <td>${(s.adx_value || 0).toFixed(1)}</td>
          <td>${s.executed ? '<span class="text-green">✓ Khớp</span>' : '<span class="text-muted">Chờ</span>'}</td>
          <td>${s.order_ticket ? `<span class="text-cyan">#${s.order_ticket}</span>` : '--'}</td>
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
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">Chưa có dữ liệu</td></tr>`;
      return;
    }

    tbody.innerHTML = equity.map(e => `
      <tr>
        <td><strong>${e.date}</strong></td>
        <td>$${Number(e.balance).toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
        <td class="text-cyan">$${Number(e.equity).toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
        <td class="text-gold"><strong>${Math.round(e.equity * usdToVndRate).toLocaleString("vi-VN")} ₫</strong></td>
        <td class="${Number(e.floating_pnl) >= 0 ? 'text-green' : 'text-red'}">${Number(e.floating_pnl) >= 0 ? '+' : ''}$${Number(e.floating_pnl).toFixed(2)}</td>
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

// Toast
function showToast(msg) {
  const toast = document.getElementById("toast-notice");
  toast.innerText = msg;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 3500);
}
