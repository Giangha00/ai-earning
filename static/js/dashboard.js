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
let liveSocket = null;

document.addEventListener("DOMContentLoaded", () => {
  initCharts();
  initOrderForm();
  initTabs();
  initControls();
  initMarketsModal();
  initBalanceSync();
  loadAllData();
  initWebSocket();

  // Auto-refresh dự phòng
  setInterval(() => {
    loadAccountData();
    loadOrdersSidebar();
  }, 10000);
});

// WebSocket Realtime Streaming
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/live`;
  const badge = document.getElementById("connection-badge");
  const text = document.getElementById("connection-text");
  const hudWsStatus = document.getElementById("hud-ws-status");

  try {
    liveSocket = new WebSocket(wsUrl);

    liveSocket.onopen = () => {
      console.log("🟢 WebSocket Connected to AI Trading Engine!");
      if (badge) badge.className = "status-badge connected";
      if (text) text.innerText = "Realtime Engine";
      if (hudWsStatus) hudWsStatus.innerText = "🟢 WEBSOCKET REALTIME";
    };

    liveSocket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "REALTIME_TICK" || msg.type === "INIT_STATE") {
          handleRealtimeTick(msg.data);
        } else if (msg.type === "ORDER_PLACED") {
          showToast(`⚡ AI Bot khớp lệnh: ${msg.data.order_type} ${msg.data.lot_size} lot ${msg.data.symbol} (R:R 1:${msg.data.rr_ratio})`);
          loadOrdersSidebar();
          loadSignals();
          loadAccountData();
        }
      } catch (err) {
        console.error("Lỗi parse WS:", err);
      }
    };

    liveSocket.onclose = () => {
      if (badge) badge.className = "status-badge simulation";
      if (text) text.innerText = "Mất kết nối WS (Đang thử lại...)";
      if (hudWsStatus) hudWsStatus.innerText = "🟡 ĐANG KẾT NỐI LẠI...";
      setTimeout(initWebSocket, 3000);
    };

    liveSocket.onerror = (err) => {
      console.warn("WebSocket error:", err);
    };
  } catch (e) {
    setTimeout(initWebSocket, 3000);
  }

  // Heartbeat ping
  setInterval(() => {
    if (liveSocket && liveSocket.readyState === WebSocket.OPEN) {
      liveSocket.send("ping");
    }
  }, 10000);
}

function handleRealtimeTick(data) {
  if (!data) return;

  // 1. Cập nhật giá trên header với chỉ báo đổi màu động
  latestMarketPrice = data.last_price || data.ask;
  const headerLiveTick = document.getElementById("header-live-tick");
  if (headerLiveTick) {
    const prevText = headerLiveTick.innerText;
    const prevPrice = parseFloat(prevText.split(":")[1]) || latestMarketPrice;
    const isUp = latestMarketPrice >= prevPrice;
    headerLiveTick.style.color = isUp ? "#10b981" : "#f43f5e";
    headerLiveTick.innerText = `${data.symbol}: ${latestMarketPrice.toFixed(5)}`;
  }

  // 2. Cập nhật nến biểu đồ thời gian thực (Real-time Candlestick & Volume & Legend)
  if (data.last_candle && candleSeries) {
    candleSeries.update(data.last_candle);

    // Cập nhật Volume cột tương ứng
    if (volumeSeries) {
      const isBull = data.last_candle.close >= data.last_candle.open;
      volumeSeries.update({
        time: data.last_candle.time,
        value: data.last_candle.volume || 1,
        color: isBull ? "rgba(34, 197, 94, 0.6)" : "rgba(239, 68, 68, 0.6)"
      });
    }

    // Đồng bộ mảng nến cục bộ để crosshair không bị lệch
    if (lastCandleData && lastCandleData.length > 0) {
      const lastIdx = lastCandleData.length - 1;
      if (lastCandleData[lastIdx].time === data.last_candle.time) {
        lastCandleData[lastIdx] = data.last_candle;
      } else if (data.last_candle.time > lastCandleData[lastIdx].time) {
        lastCandleData.push(data.last_candle);
      }
    }

    // Cập nhật toàn bộ thanh Legend OHLCV trên đỉnh biểu đồ
    const dateStr = new Date(data.last_candle.time * 1000).toLocaleString("vi-VN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
    const change = data.last_candle.close - data.last_candle.open;
    const pct = (change / (data.last_candle.open || 1)) * 100;
    const isPos = change >= 0;

    const elTime = document.getElementById("legend-time");
    if (elTime) elTime.innerText = dateStr;
    const elOpen = document.getElementById("legend-open");
    if (elOpen) elOpen.innerText = data.last_candle.open.toFixed(5);
    const elHigh = document.getElementById("legend-high");
    if (elHigh) elHigh.innerText = data.last_candle.high.toFixed(5);
    const elLow = document.getElementById("legend-low");
    if (elLow) elLow.innerText = data.last_candle.low.toFixed(5);
    const elClose = document.getElementById("legend-close");
    if (elClose) elClose.innerText = data.last_candle.close.toFixed(5);
    const elVol = document.getElementById("legend-vol");
    if (elVol) elVol.innerText = (data.last_candle.volume || 1).toLocaleString();

    const elChange = document.getElementById("legend-change");
    if (elChange) {
      elChange.innerText = `${isPos ? "+" : ""}${change.toFixed(5)} (${isPos ? "+" : ""}${pct.toFixed(2)}%)`;
      elChange.style.color = isPos ? "#10b981" : "#f43f5e";
    }
  }

  // 3. Cập nhật HUD AI 6 Kịch bản thị trường (Chương 1)
  const hudCase = document.getElementById("hud-market-case");
  const hudReason = document.getElementById("hud-case-reason");
  if (hudCase && data.market_case) {
    let badgeClass = "badge-case-a";
    let caseLabel = data.market_case;
    if (data.market_case.includes("CASE_A")) {
      badgeClass = "badge-case-a";
      caseLabel = "CASE A: TREND MƯỢT";
    } else if (data.market_case.includes("CASE_B")) {
      badgeClass = "badge-case-b";
      caseLabel = "CASE B: VÙNG NÉN";
    } else if (data.market_case.includes("CASE_C")) {
      badgeClass = "badge-case-c";
      caseLabel = "CASE C: HỖN LOẠN CÁI LOA (CẤM VÀO LỆNH)";
    } else if (data.market_case.includes("CASE_D")) {
      badgeClass = "badge-case-d";
      caseLabel = "CASE D: BẪY THANH KHOẢN (VÀO ĐẢO CHIỀU)";
    } else if (data.market_case.includes("CASE_E")) {
      badgeClass = "badge-case-e";
      caseLabel = "CASE E: SÓNG DẪN HƯỚNG (CHỜ RETEST)";
    } else if (data.market_case.includes("CASE_F")) {
      badgeClass = "badge-case-f";
      caseLabel = "CASE F: BÃO TIN & ROLLOVER (NGẮT MẠCH)";
    }
    hudCase.innerHTML = `<span class="badge ${badgeClass}">${caseLabel}</span>`;
  }
  if (hudReason && data.market_case_reason) {
    hudReason.innerText = data.market_case_reason;
  }

  // 4. Cập nhật HMM Regime (Chương 2.6)
  const hudHmm = document.getElementById("hud-hmm-regime");
  if (hudHmm && data.regime) {
    let color = data.regime === "BULLISH" ? "text-green" : (data.regime === "BEARISH" ? "text-red" : "text-amber");
    hudHmm.innerHTML = `<span class="${color}" style="font-weight: 700;">${data.regime} ${data.hmm_safe ? '✓ An toàn' : '⚠️ Ngắt lệnh'}</span>`;
  }

  // 5. Cập nhật OOD Isolation Forest (Chương 4.3)
  const hudOod = document.getElementById("hud-ood-status");
  const hudOodScore = document.getElementById("hud-ood-score");
  if (hudOod) {
    if (data.is_ood) {
      hudOod.innerHTML = `<span class="text-red" style="font-weight: 700;">⚠️ CẢNH BÁO DỮ LIỆU LẠ (BỎ QUA)</span>`;
    } else {
      hudOod.innerHTML = `<span class="text-cyan" style="font-weight: 700;">🛡️ AN TOÀN (Dữ liệu chuẩn)</span>`;
    }
  }
  if (hudOodScore) {
    hudOodScore.innerText = `Anomaly Score: ${(data.anomaly_score || 0).toFixed(3)} (Ngưỡng OOD: 0.05)`;
  }

  // 6. Cập nhật Cầu dao 24H (Chương 4.4)
  const hudCircuit = document.getElementById("hud-circuit-breaker");
  if (hudCircuit && data.circuit_breaker) {
    const isLocked = data.circuit_breaker.includes("LOCKED");
    hudCircuit.innerHTML = isLocked
      ? `<span class="text-red" style="font-weight: 800;">🚨 ${data.circuit_breaker}</span>`
      : `<span class="text-green" style="font-weight: 700;">HOẠT ĐỘNG (${data.consecutive_losses || 0}/2 Lỗ)</span>`;
  }

  // 7. Độ tin cậy & Monte Carlo VaR (Chương 2.8)
  const hudConf = document.getElementById("hud-confidence");
  if (hudConf) hudConf.innerText = `${(data.confidence || 75.0).toFixed(1)}%`;
  const hudVar = document.getElementById("hud-var95");
  if (hudVar) hudVar.innerText = `$${(data.var_95 || 0).toFixed(2)}`;
  const hudTime = document.getElementById("hud-last-update");
  if (hudTime) hudTime.innerText = `Cập nhật: ${data.updated_at || '--'}`;

  // 8. Cập nhật số dư & PnL USD realtime (Chuẩn Exness MT5)
  if (data.equity !== undefined) {
    const balUsd = Number(data.balance || data.equity || 10000);
    const eqUsd = Number(data.equity || balUsd);
    const flUsd = Number(data.floating_pnl || 0);
    const balVnd = Math.round(balUsd * usdToVndRate);

    const wBalUsd = document.getElementById("wallet-balance-usd");
    if (wBalUsd) wBalUsd.innerText = `$${balUsd.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    const wEqUsd = document.getElementById("wallet-equity-usd");
    if (wEqUsd) wEqUsd.innerText = `$${eqUsd.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    const wFloatUsd = document.getElementById("wallet-floating-usd");
    if (wFloatUsd) {
      wFloatUsd.className = flUsd >= 0 ? "text-green" : "text-red";
      wFloatUsd.innerText = `${flUsd >= 0 ? '+' : ''}$${flUsd.toFixed(2)}`;
    }

    const wBalVnd = document.getElementById("wallet-balance-vnd");
    if (wBalVnd) wBalVnd.innerText = `~${balVnd.toLocaleString("vi-VN")} ₫`;
  }
}

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
      rightOffset: 8,
      barSpacing: 9,
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
    priceLineVisible: true,
    lastValueVisible: true,
    priceLineWidth: 1,
    priceLineColor: "#06b6d4",
    priceLineStyle: LightweightCharts.LineStyle.Dashed,
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
    currentAccountUsd = Number(data.balance) || 10000.0;

    const rateEl = document.getElementById("header-rate-display");
    if (rateEl) {
      rateEl.innerText = `Tỷ giá: 1 USD ≈ ${usdToVndRate.toLocaleString("vi-VN")} ₫`;
    }

    const badge = document.getElementById("connection-badge");
    const badgeText = document.getElementById("connection-text");

    if (data.is_simulation) {
      badge.className = "status-badge simulation";
      badgeText.innerText = `Tài khoản ${data.server} (#${data.login})`;
    } else {
      badge.className = "status-badge";
      badgeText.innerText = `MT5 Exness • ${data.server} (#${data.login})`;
    }

    // Hiển thị số dư trong ví dạng USD (Dưới chart)
    const balUsd = Number(data.balance) || 10000.0;
    const eqUsd = Number(data.equity) || balUsd;
    const flUsd = Number(data.floating_pnl) || 0.0;
    const realizedUsd = Number(data.total_profit) || 0.0;
    const balVnd = Number(data.balance_vnd || (balUsd * usdToVndRate));

    const wBalUsd = document.getElementById("wallet-balance-usd");
    if (wBalUsd) wBalUsd.innerText = `$${balUsd.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    const wEqUsd = document.getElementById("wallet-equity-usd");
    if (wEqUsd) wEqUsd.innerText = `$${eqUsd.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    const wFloatUsd = document.getElementById("wallet-floating-usd");
    if (wFloatUsd) {
      wFloatUsd.className = flUsd >= 0 ? "text-green" : "text-red";
      wFloatUsd.innerText = `${flUsd >= 0 ? "+" : ""}$${flUsd.toFixed(2)}`;
    }

    const wBalVnd = document.getElementById("wallet-balance-vnd");
    if (wBalVnd) wBalVnd.innerText = `~${balVnd.toLocaleString("vi-VN")} ₫`;

    document.getElementById("wallet-leverage").innerText = `1:${data.leverage}`;
    document.getElementById("wallet-winrate").innerText = `${data.win_rate}%`;

    const realizedEl = document.getElementById("wallet-realized-usd");
    if (realizedEl) {
      realizedEl.innerText = `${realizedUsd >= 0 ? "+" : ""}$${realizedUsd.toFixed(2)}`;
      realizedEl.style.color = realizedUsd >= 0 ? "var(--color-gold)" : "var(--color-red)";
    }

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

    // Hiển thị 75 nến gần nhất với khoảng thở bên phải để thấy rõ từng nhịp nến biến động live
    const totalBars = data.candles.length;
    mainChart.timeScale().setVisibleLogicalRange({
      from: Math.max(0, totalBars - 75),
      to: totalBars + 5
    });
    rsiChart.timeScale().setVisibleLogicalRange({
      from: Math.max(0, totalBars - 75),
      to: totalBars + 5
    });

    latestMarketPrice = data.latest_price || data.candles[data.candles.length - 1].close;

    // Cập nhật giá thật thị trường vào ô nhập lệnh (USD) nếu chưa sửa
    const entryInput = document.getElementById("input-entry-price");
    if (entryInput && !entryInput.dataset.modified) {
      const digits = getSymbolDigits();
      entryInput.value = latestMarketPrice.toFixed(digits);
      const targetInput = document.getElementById("input-target-price");
      if (targetInput && !targetInput.dataset.modified) {
        // Mặc định tính theo mức lời +$50 USD nếu chưa nhập
        const defaultLot = parseFloat(document.getElementById("input-lot-size").value) || 0.1;
        const mult = getSymbolContractMultiplier();
        const diffPrice = 50.0 / (defaultLot * mult);
        targetInput.value = (latestMarketPrice + diffPrice).toFixed(digits);
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

function getSymbolDigits() {
  const isGold = currentSymbol.includes("XAU") || currentSymbol.includes("GOLD");
  const isCrypto = currentSymbol.includes("BTC") || currentSymbol.includes("ETH");
  const isJpy = currentSymbol.includes("JPY");
  if (isGold || isCrypto) return 2;
  if (isJpy) return 3;
  return 5;
}

function getSymbolPipSize() {
  const isGold = currentSymbol.includes("XAU") || currentSymbol.includes("GOLD");
  const isJpy = currentSymbol.includes("JPY");
  if (isGold) return 0.10;
  if (isJpy) return 0.01;
  return 0.0001;
}

function getSymbolContractMultiplier() {
  const isGold = currentSymbol.includes("XAU") || currentSymbol.includes("GOLD");
  const isCrypto = currentSymbol.includes("BTC") || currentSymbol.includes("ETH");
  if (isGold || isCrypto) return 100.0;
  return 100000.0;
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

    const isGold = (o.symbol || "").includes("XAU");
    const digits = isGold ? 2 : 5;

    const openPrice = o.open_price ? Number(o.open_price).toFixed(digits) : "--";
    const targetPrice = o.take_profit ? Number(o.take_profit).toFixed(digits) : "--";
    const closePrice = o.close_price ? Number(o.close_price).toFixed(digits) : (isOpen ? "Đang chạy" : "--");

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
          <div class="order-detail-field">Giá vào (Open): <span>${openPrice}</span></div>
          <div class="order-detail-field">Mục tiêu (TP): <span>${targetPrice}</span></div>
          <div class="order-detail-field">Kịch bản: <span class="text-cyan">${o.market_case || 'CASE_A_TREND'}</span></div>
          <div class="order-detail-field">Tỷ lệ R:R: <span class="text-gold">${o.rr_ratio ? `1:${o.rr_ratio.toFixed(2)}` : '1:2.0'}</span></div>
          <div class="order-detail-field">Giá chốt: <span>${closePrice}</span></div>
          <div class="order-detail-field">Thời gian: <span>${(o.open_time || '').split(" ")[1] || o.open_time}</span></div>
        </div>

        <div class="order-pnl-row">
          <div>
            <div class="order-pnl-usd ${pnlUsd >= 0 ? 'text-green' : 'text-red'}" style="font-size: 15px; font-weight: 700;">
              ${pnlUsd >= 0 ? '+' : ''}$${pnlUsd.toFixed(2)} USD
            </div>
            <div class="order-pnl-vnd" style="color: var(--text-muted); font-size: 11px;">
              Tham chiếu: ${pnlVnd >= 0 ? '+' : ''}${Math.round(pnlVnd).toLocaleString("vi-VN")} ₫
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

// 4. Order Input & Profit Calculation Logic (USD Primary View)
function initOrderForm() {
  const entryInput = document.getElementById("input-entry-price");
  const lotInput = document.getElementById("input-lot-size");
  const targetInput = document.getElementById("input-target-price");

  if (entryInput) {
    entryInput.addEventListener("input", () => {
      entryInput.dataset.modified = "true";
      recalcEstimatedProfit();
    });
  }

  if (targetInput) {
    targetInput.addEventListener("input", () => {
      targetInput.dataset.modified = "true";
      document.querySelectorAll(".profit-chip").forEach(c => c.classList.remove("active"));
      recalcEstimatedProfit();
    });
  }

  if (lotInput) {
    lotInput.addEventListener("input", () => {
      const activeProfitChip = document.querySelector(".profit-chip.active");
      if (activeProfitChip) {
        applyProfitGoal(parseFloat(activeProfitChip.dataset.profit));
      } else {
        recalcEstimatedProfit();
      }
    });
  }

  // Quick fill current price
  const fillBtn = document.getElementById("btn-fill-current-price");
  if (fillBtn) {
    fillBtn.addEventListener("click", () => {
      const digits = getSymbolDigits();
      entryInput.value = latestMarketPrice.toFixed(digits);
      const activeProfitChip = document.querySelector(".profit-chip.active");
      if (activeProfitChip) {
        applyProfitGoal(parseFloat(activeProfitChip.dataset.profit));
      } else {
        recalcEstimatedProfit();
      }
      showToast(`⚡ Đã lấy giá thị trường thực tế: ${latestMarketPrice.toFixed(digits)}`);
    });
  }

  // Quick adjust entry price (-10 pips / +10 pips)
  const minusBtn = document.getElementById("btn-adj-entry-minus");
  if (minusBtn) {
    minusBtn.addEventListener("click", () => {
      const pipSize = getSymbolPipSize();
      const digits = getSymbolDigits();
      const curPrice = parseFloat(entryInput.value) || latestMarketPrice;
      entryInput.value = (curPrice - 10 * pipSize).toFixed(digits);
      entryInput.dataset.modified = "true";
      recalcEstimatedProfit();
    });
  }

  const plusBtn = document.getElementById("btn-adj-entry-plus");
  if (plusBtn) {
    plusBtn.addEventListener("click", () => {
      const pipSize = getSymbolPipSize();
      const digits = getSymbolDigits();
      const curPrice = parseFloat(entryInput.value) || latestMarketPrice;
      entryInput.value = (curPrice + 10 * pipSize).toFixed(digits);
      entryInput.dataset.modified = "true";
      recalcEstimatedProfit();
    });
  }

  // Lot quick chips
  const lotChips = document.querySelectorAll(".lot-chip");
  lotChips.forEach(chip => {
    chip.addEventListener("click", () => {
      lotChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      lotInput.value = chip.dataset.lot;

      const activeProfitChip = document.querySelector(".profit-chip.active");
      if (activeProfitChip) {
        applyProfitGoal(parseFloat(activeProfitChip.dataset.profit));
      } else {
        recalcEstimatedProfit();
      }
    });
  });

  // Profit quick chips (Mức tiền lời USD mong muốn: +$20, +$50, +$100, +$200, +$500)
  const profitChips = document.querySelectorAll(".profit-chip");
  profitChips.forEach(chip => {
    chip.addEventListener("click", () => {
      profitChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      applyProfitGoal(parseFloat(chip.dataset.profit));
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

function applyProfitGoal(desiredProfitUsd) {
  const entryInput = document.getElementById("input-entry-price");
  const lotInput = document.getElementById("input-lot-size");
  const targetInput = document.getElementById("input-target-price");

  if (!entryInput || !lotInput || !targetInput) return;

  const entryPrice = parseFloat(entryInput.value) || latestMarketPrice;
  const lot = parseFloat(lotInput.value) || 0.1;
  const mult = getSymbolContractMultiplier();
  const digits = getSymbolDigits();

  // Công thức: Profit USD = (Diff Price) * Multiplier * Lot
  // Diff Price = Profit USD / (Multiplier * Lot)
  const diffPrice = desiredProfitUsd / (mult * lot);
  targetInput.value = (entryPrice + diffPrice).toFixed(digits);
  targetInput.dataset.modified = "true";
  recalcEstimatedProfit();
}

function recalcEstimatedProfit() {
  const entryInput = document.getElementById("input-entry-price");
  const targetInput = document.getElementById("input-target-price");
  const lotInput = document.getElementById("input-lot-size");

  if (!entryInput || !targetInput || !lotInput) return;

  const entryPrice = parseFloat(entryInput.value) || 0;
  const targetPrice = parseFloat(targetInput.value) || 0;
  const lot = parseFloat(lotInput.value) || 0;

  const subEntryVnd = document.getElementById("sub-entry-vnd");
  const subTargetInfo = document.getElementById("sub-target-info");
  const subMarginUsd = document.getElementById("sub-margin-usd");

  const pipSize = getSymbolPipSize();
  const mult = getSymbolContractMultiplier();

  if (subEntryVnd && entryPrice > 0) {
    const entryVnd = Math.round(entryPrice * usdToVndRate);
    subEntryVnd.innerText = `~${entryVnd.toLocaleString("vi-VN")} ₫`;
  }

  if (subMarginUsd && lot > 0) {
    // Ký quỹ 1:100 đòn bẩy cho 1 lot EURUSD là ~1,000 USD
    const marginUsd = lot * (mult / 100);
    subMarginUsd.innerText = `$${marginUsd.toFixed(2)} USD`;
  }

  if (entryPrice <= 0 || targetPrice <= 0 || lot <= 0) {
    const distEl = document.getElementById("calc-pips-dist");
    if (distEl) distEl.innerText = "-- pips";
    const profUsdEl = document.getElementById("calc-profit-usd");
    if (profUsdEl) profUsdEl.innerText = "$--";
    const profVndEl = document.getElementById("calc-profit-vnd");
    if (profVndEl) profVndEl.innerText = "-- ₫";
    return;
  }

  const diffPrice = Math.abs(targetPrice - entryPrice);
  const pips = diffPrice / pipSize;
  const profitUsd = diffPrice * mult * lot;
  const profitVnd = profitUsd * usdToVndRate;

  if (subTargetInfo) {
    subTargetInfo.innerText = `+${pips.toFixed(1)} pips (+$${profitUsd.toFixed(2)})`;
  }

  const distEl = document.getElementById("calc-pips-dist");
  if (distEl) distEl.innerText = `Khoảng cách TP: +${pips.toFixed(1)} pips | R:R: 1:2.0`;
  const profUsdEl = document.getElementById("calc-profit-usd");
  if (profUsdEl) profUsdEl.innerText = `+$${profitUsd.toFixed(2)} USD`;
  const profVndEl = document.getElementById("calc-profit-vnd");
  if (profVndEl) profVndEl.innerText = `~${Math.round(profitVnd).toLocaleString("vi-VN")} ₫`;
}

async function executeOrder(orderType) {
  const entryPrice = parseFloat(document.getElementById("input-entry-price").value);
  const lot = parseFloat(document.getElementById("input-lot-size").value);
  const targetPrice = parseFloat(document.getElementById("input-target-price").value);

  if (!entryPrice || !lot || !targetPrice) {
    showToast("⚠️ Vui lòng nhập mức giá vào lệnh, số lot và mức giá chốt lời (TP)!");
    return;
  }

  const mult = getSymbolContractMultiplier();
  const diffPrice = Math.abs(targetPrice - entryPrice);
  const expectedProfitUsd = diffPrice * mult * lot;

  try {
    const res = await fetch("/api/orders/place", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: currentSymbol,
        order_type: orderType,
        lot_size: lot,
        entry_price: entryPrice,
        target_price: targetPrice,
        target_profit_usd: expectedProfitUsd
      })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`✓ AI đã khớp lệnh ${orderType} ${lot} lot ${currentSymbol} tại ${entryPrice} | Mục tiêu: +$${expectedProfitUsd.toFixed(2)} USD (#${data.ticket_id})`);
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
      tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: var(--text-muted);">Chưa có tín hiệu nào</td></tr>`;
      return;
    }

    tbody.innerHTML = signals.map(s => {
      let typeBadge = "badge-hold";
      if (s.signal_type === "BUY") typeBadge = "badge-buy";
      else if (s.signal_type === "SELL") typeBadge = "badge-sell";
      else if (s.signal_type === "STRICT_NO_TRADE") typeBadge = "badge-case-c";

      let caseBadge = "badge-case-a";
      if (s.market_case && s.market_case.includes("CASE_B")) caseBadge = "badge-case-b";
      else if (s.market_case && s.market_case.includes("CASE_C")) caseBadge = "badge-case-c";
      else if (s.market_case && s.market_case.includes("CASE_D")) caseBadge = "badge-case-d";
      else if (s.market_case && s.market_case.includes("CASE_E")) caseBadge = "badge-case-e";
      else if (s.market_case && s.market_case.includes("CASE_F")) caseBadge = "badge-case-f";

      return `
        <tr>
          <td>#${s.id}</td>
          <td>${s.timestamp}</td>
          <td><strong>${s.symbol}</strong></td>
          <td><span class="badge ${typeBadge}">${s.signal_type}</span></td>
          <td><span class="badge ${caseBadge}">${s.market_case || 'CASE_A_TREND'}</span></td>
          <td><span class="text-cyan">${s.regime || 'BULLISH'}</span></td>
          <td>${(s.confidence || 0).toFixed(1)}%</td>
          <td>${s.rr_ratio ? `1:${s.rr_ratio.toFixed(2)}` : '1:2.0'}</td>
          <td>${s.executed ? '<span class="text-green">✓ Khớp</span>' : '<span class="text-muted">Chờ</span>'}</td>
          <td>${s.order_ticket ? `<span class="text-cyan">#${s.order_ticket}</span>` : '--'}</td>
          <td style="max-width: 250px; font-size: 11px; color: var(--text-muted);">${s.reason || '--'}</td>
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
  if (!toast) return;
  toast.innerText = msg;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 3500);
}

// ==========================================================================
// 1. DANH MỤC 355 THỊ TRƯỜNG EXNESS (MT5 API)
// ==========================================================================
let allMarketsList = [];
let currentMarketCategory = "all";

function initMarketsModal() {
  const btnOpen = document.getElementById("btn-open-markets");
  const modal = document.getElementById("markets-modal");
  const btnClose = document.getElementById("btn-close-markets");
  const searchInput = document.getElementById("markets-search-input");
  const catButtons = document.querySelectorAll(".cat-tab-btn");

  if (!modal) return;

  if (btnOpen) {
    btnOpen.addEventListener("click", () => {
      modal.classList.remove("hidden");
      if (allMarketsList.length === 0) {
        loadMarketsList();
      }
      setTimeout(() => searchInput && searchInput.focus(), 100);
    });
  }

  if (btnClose) {
    btnClose.addEventListener("click", () => {
      modal.classList.add("hidden");
    });
  }

  modal.addEventListener("click", (e) => {
    if (e.target === modal) {
      modal.classList.add("hidden");
    }
  });

  // Filter tabs
  catButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      catButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentMarketCategory = btn.dataset.cat || "all";
      filterAndRenderMarkets();
    });
  });

  // Search filter
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      filterAndRenderMarkets();
    });
  }
}

async function loadMarketsList() {
  try {
    const res = await fetch("/api/markets");
    const data = await res.json();
    allMarketsList = data.markets || [];
    filterAndRenderMarkets();
  } catch (err) {
    console.error("Lỗi nạp danh sách thị trường:", err);
  }
}

function filterAndRenderMarkets() {
  const container = document.getElementById("markets-list-body");
  if (!container) return;

  const searchInput = document.getElementById("markets-search-input");
  const query = (searchInput ? searchInput.value : "").toLowerCase().trim();

  const filtered = allMarketsList.filter(m => {
    // Category match
    let matchCat = true;
    if (currentMarketCategory === "forex") {
      matchCat = m.category === "Forex";
    } else if (currentMarketCategory === "metals_energy") {
      matchCat = m.category === "Kim loại & Dầu";
    } else if (currentMarketCategory === "crypto") {
      matchCat = m.category === "Crypto";
    } else if (currentMarketCategory === "indices") {
      matchCat = m.category === "Chỉ số";
    } else if (currentMarketCategory === "stocks") {
      matchCat = m.category === "Cổ phiếu";
    }

    // Search query match
    let matchSearch = true;
    if (query) {
      matchSearch = m.symbol.toLowerCase().includes(query) || (m.name && m.name.toLowerCase().includes(query));
    }

    return matchCat && matchSearch;
  });

  if (filtered.length === 0) {
    container.innerHTML = `<div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: var(--text-muted);">Không tìm thấy thị trường nào phù hợp với tìm kiếm "${query}"</div>`;
    return;
  }

  container.innerHTML = filtered.map(m => {
    let catClass = "cat-forex";
    if (m.category === "Kim loại & Dầu") catClass = "cat-metals";
    else if (m.category === "Crypto") catClass = "cat-crypto";
    else if (m.category === "Chỉ số") catClass = "cat-indices";
    else if (m.category === "Cổ phiếu") catClass = "cat-stocks";

    const isCurrent = m.symbol === currentSymbol;

    return `
      <div class="market-item-card" onclick="selectMarket('${m.symbol}')" style="${isCurrent ? 'border-color: var(--color-cyan); background: rgba(6, 182, 212, 0.12);' : ''}">
        <div class="market-item-left">
          <div class="market-item-symbol">
            <span>${m.symbol}</span>
            <span class="market-badge-cat ${catClass}">${m.category}</span>
            ${isCurrent ? '<span style="color: var(--color-cyan); font-size: 11px;">● Đang xem</span>' : ''}
          </div>
          <div class="market-item-name" title="${m.name}">${m.name}</div>
        </div>
        <div class="market-item-right">
          <div class="market-item-price">${(m.base || 1.0).toFixed(m.digits >= 3 ? 3 : m.digits)}</div>
          <div class="market-item-spread">Spread: ${m.spread} pts</div>
        </div>
      </div>
    `;
  }).join("");
}

function selectMarket(symbol) {
  if (currentSymbol === symbol) {
    const modal = document.getElementById("markets-modal");
    if (modal) modal.classList.add("hidden");
    return;
  }

  currentSymbol = symbol;
  const activeSymEl = document.getElementById("active-symbol");
  if (activeSymEl) activeSymEl.innerText = symbol;

  const orderSymbolTag = document.getElementById("order-symbol-tag");
  if (orderSymbolTag) orderSymbolTag.innerText = symbol;

  const entryInput = document.getElementById("input-entry-price");
  if (entryInput) delete entryInput.dataset.modified;
  const targetInput = document.getElementById("input-target-price");
  if (targetInput) delete targetInput.dataset.modified;

  const modal = document.getElementById("markets-modal");
  if (modal) modal.classList.add("hidden");

  showToast(`⚡ Đã chuyển sang thị trường: ${symbol}`);
  loadCandleData();
  filterAndRenderMarkets();
}

// ==========================================================================
// 2. ĐỒNG BỘ SỐ DƯ TÀI KHOẢN VÍ EXNESS
// ==========================================================================
let currentAccountUsd = 10000.0;

function initBalanceSync() {
  const btnSync = document.getElementById("btn-sync-balance");
  const modal = document.getElementById("balance-modal");
  const btnClose = document.getElementById("btn-close-balance");
  const form = document.getElementById("form-sync-balance");
  const inputUsd = document.getElementById("input-sync-balance-usd");
  const previewVnd = document.getElementById("sync-balance-vnd-preview");

  if (!modal) return;

  if (btnSync) {
    btnSync.addEventListener("click", () => {
      modal.classList.remove("hidden");
      if (inputUsd) {
        inputUsd.value = currentAccountUsd;
        updatePreview();
        setTimeout(() => inputUsd.focus(), 100);
      }
    });
  }

  if (btnClose) {
    btnClose.addEventListener("click", () => {
      modal.classList.add("hidden");
    });
  }

  modal.addEventListener("click", (e) => {
    if (e.target === modal) {
      modal.classList.add("hidden");
    }
  });

  function updatePreview() {
    if (!inputUsd || !previewVnd) return;
    const usd = parseFloat(inputUsd.value) || 0;
    const vnd = Math.round(usd * usdToVndRate);
    previewVnd.innerText = `${vnd.toLocaleString("vi-VN")} ₫`;
  }

  if (inputUsd) {
    inputUsd.addEventListener("input", updatePreview);
  }

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const newBal = parseFloat(inputUsd.value);
      if (isNaN(newBal) || newBal < 0) {
        showToast("⚠️ Vui lòng nhập số dư hợp lệ!");
        return;
      }

      try {
        const res = await fetch("/api/account/balance", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ balance: newBal })
        });
        const resData = await res.json();
        if (res.ok) {
          currentAccountUsd = newBal;
          modal.classList.add("hidden");
          showToast(`✅ ${resData.message || 'Đã đồng bộ số dư Exness thành công!'}`);
          await loadAccountData();
        } else {
          showToast(`❌ Lỗi: ${resData.detail || 'Không thể cập nhật số dư'}`);
        }
      } catch (err) {
        console.error(err);
        showToast("❌ Lỗi kết nối máy chủ");
      }
    });
  }
}
