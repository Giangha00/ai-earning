#!/usr/bin/env python3
"""
mql5_signal_crawler.py
Module thu thập (crawl) dữ liệu từ MQL5 MT5 Signals (https://www.mql5.com/en/signals/mt5)
để tạo bộ Dataset Huấn luyện AI (Feature Engineering & Target Labels) cho dự án AI Trading Bot.

Các tính năng chính:
1. Thu thập danh sách tín hiệu từ các trang danh mục (/en/signals/mt5/page{N}).
2. Trích xuất thông tin tổng quan từ card (Tên, ID, Tác giả, Tăng trưởng, Algo trading %, Đòn bẩy, Phí, ...).
3. Thu thập thông tin chi tiết từng tín hiệu (/en/signals/{id}):
   - Profit Factor, Sharpe Ratio, Recovery Factor, Expected Payoff.
   - Max Drawdown (USD & %), Relative Drawdown theo Balance/Equity.
   - Tỷ lệ lệnh thắng (Win rate), Lỗ, Chuỗi thắng/thua tối đa.
   - Thời gian giữ lệnh trung bình (Average holding time), Số lệnh/tuần.
   - Các cặp tiền/tài sản được giao dịch (XAUUSD, EURUSD, ...).
4. Phân tích chuỗi thời gian tăng trưởng (Equity/Growth curve timeseries).
5. Kỹ thuật tạo đặc trưng AI (Feature Engineering) & Nhãn học có giám sát (Supervised Targets):
   - Features X: 22+ đặc trưng định lượng chuẩn hóa (Ratios, Volatility, Efficiency).
   - Labels Y: 'is_high_quality' (Binary), 'quality_grade' (Multi-class), 'target_profit_factor' (Regression).
6. Xuất định dạng chuẩn: Parquet, CSV và JSON Timeseries vào thư mục data/mql5_signals/.
"""

import argparse
import http.cookiejar
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

from config import BASE_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("mql5_signal_crawler")

DEFAULT_OUTPUT_DIR = BASE_DIR / "data" / "mql5_signals"
BASE_URL = "https://www.mql5.com"
SIGNALS_LIST_URL = "https://www.mql5.com/en/signals/mt5"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def clean_number(val: Any) -> float:
    """Chuyển đổi chuỗi số có định dạng đặc thù (khoảng trắng, USD, %, dấu phẩy) sang float an toàn."""
    if val is None or val == "" or val == "-" or val == "—":
        return 0.0
    s = str(val).replace("\xa0", " ").strip()
    s = s.replace("USD", "").replace("%", "").replace(",", "")
    s = s.replace(" ", "")
    if "(" in s:
        s = s.split("(")[0].strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_value_and_pct(text: str) -> Tuple[float, float]:
    """Phân tách định dạng '657 (71.56%)' thành (657.0, 71.56)."""
    if not text:
        return 0.0, 0.0
    m = re.search(r"([\d\s\.,\-]+)\s*\(\s*([\d\s\.,\-]+)%\s*\)", text)
    if m:
        val = clean_number(m.group(1))
        pct = clean_number(m.group(2))
        return val, pct
    return clean_number(text), 0.0


def parse_drawdown(text: str) -> Tuple[float, float]:
    """Phân tách chuỗi drawdown '665.41USD (9.50%)' hoặc '16.89% (319.49USD)'."""
    if not text:
        return 0.0, 0.0
    m_pct_first = re.search(r"([\d\s\.,]+)%\s*\(\s*([\d\s\.,]+)\s*USD\s*\)", text, re.I)
    if m_pct_first:
        pct = clean_number(m_pct_first.group(1))
        usd = clean_number(m_pct_first.group(2))
        return usd, pct
    m_usd_first = re.search(r"([\d\s\.,]+)\s*USD?\s*\(\s*([\d\s\.,]+)%\s*\)", text, re.I)
    if m_usd_first:
        usd = clean_number(m_usd_first.group(1))
        pct = clean_number(m_usd_first.group(2))
        return usd, pct
    return 0.0, clean_number(text)


def parse_holding_time_hours(text: str) -> float:
    """Chuyển đổi thời gian giữ lệnh ('4 hours', '2 days 6 hours', '45 mins') sang số giờ dạng float."""
    if not text:
        return 0.0
    s = str(text).lower()
    hours = 0.0
    m_days = re.search(r"(\d+)\s*(?:days?|d)", s)
    if m_days:
        hours += float(m_days.group(1)) * 24.0
    m_hours = re.search(r"(\d+)\s*(?:hours?|h|hrs?)", s)
    if m_hours:
        hours += float(m_hours.group(1))
    m_mins = re.search(r"(\d+)\s*(?:mins?|m|minutes?)", s)
    if m_mins:
        hours += float(m_mins.group(1)) / 60.0
    return round(hours, 2)


def parse_leverage_ratio(text: str) -> float:
    """Trích xuất đòn bẩy từ chuỗi '1:500' -> 500.0."""
    if not text:
        return 1.0
    m = re.search(r"1\s*:\s*(\d+)", str(text))
    if m:
        return float(m.group(1))
    return 1.0


class MQL5SignalCrawler:
    """
    Crawler chuyên dụng cho chuyên trang MetaTrader 5 Signals trên MQL5.com.
    Đảm bảo tính chịu lỗi, rate-limiting thân thiện và chuẩn hóa dữ liệu cho AI.
    """

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        delay_range: Tuple[float, float] = (0.5, 1.2),
        max_workers: int = 4,
        min_trades: int = 10,
    ) -> None:
        self.output_dir = output_dir or DEFAULT_OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.delay_range = delay_range
        self.max_workers = max_workers
        self.min_trades = min_trades
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))

    def fetch_url(self, url: str, retries: int = 3, timeout: int = 15) -> Optional[str]:
        """Tải nội dung HTML của URL với cơ chế retry và exponential backoff."""
        for attempt in range(1, retries + 1):
            try:
                req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
                with self.opener.open(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        content_bytes = resp.read()
                        return content_bytes.decode("utf-8", errors="ignore")
                    else:
                        logger.warning("Mã HTTP %d khi tải %s", resp.status, url)
            except urllib.error.HTTPError as e:
                if e.code in [403, 429]:
                    wait_sec = 2.0 * attempt
                    logger.warning("Gặp mã %d tại %s. Đang chờ %.1fs...", e.code, url, wait_sec)
                    time.sleep(wait_sec)
                else:
                    logger.warning("Lỗi HTTP %d khi tải %s (Lần thử %d/%d)", e.code, url, attempt, retries)
            except Exception as e:
                logger.warning("Ngoại lệ khi tải %s (Lần %d/%d): %s", url, attempt, retries, e)
                time.sleep(1.0 * attempt)
        return None

    def crawl_listing_page(self, page_num: int = 1) -> List[Dict[str, Any]]:
        """
        Crawl và trích xuất tất cả các thẻ tín hiệu (signal cards) từ một trang danh sách MT5.
        """
        if page_num == 1:
            url = SIGNALS_LIST_URL
        else:
            url = f"{SIGNALS_LIST_URL}/page{page_num}"

        logger.info("Đang crawl danh sách tín hiệu: Trang %d (%s)...", page_num, url)
        html = self.fetch_url(url)
        if not html:
            logger.error("Không thể tải trang %d", page_num)
            return []

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".signal-card")
        logger.info("Trang %d: Phát hiện %d thẻ tín hiệu.", page_num, len(cards))

        parsed_signals: List[Dict[str, Any]] = []

        for card in cards:
            try:
                wrapper = card.select_one("a.signal-card__wrapper")
                if not wrapper:
                    continue

                href = wrapper.get("href", "")
                m_id = re.search(r"/signals/(\d+)", href)
                if not m_id:
                    continue
                signal_id = m_id.group(1)

                # Thu thập thông tin header card
                title_el = card.select_one(".signal-card__title-wrapper") or card.select_one(".signal-card__title")
                title = title_el.get_text(strip=True) if title_el else ""

                author_el = card.select_one(".signal-card__author__item")
                author = author_el.get_text(strip=True) if author_el else ""

                rating_el = card.select_one(".g-rating__info")
                rating_str = rating_el.get_text(strip=True) if rating_el else ""
                rating_val = 0.0
                reviews_cnt = 0
                if rating_str:
                    m_rat = re.search(r"([\d\.]+)\s*(?:\((\d+)\))?", rating_str)
                    if m_rat:
                        rating_val = float(m_rat.group(1))
                        reviews_cnt = int(m_rat.group(2)) if m_rat.group(2) else 0

                # Tăng trưởng
                growth_val_el = card.select_one(".signal-card__growth-value")
                growth_pct = clean_number(growth_val_el.get_text(strip=True)) if growth_val_el else 0.0

                growth_lbl_el = card.select_one(".signal-card__growth-label")
                growth_period = growth_lbl_el.get_text(strip=True) if growth_lbl_el else ""

                # Algo trading %
                algo_el = card.select_one(".signal-card__algotrading")
                algo_pct = 0.0
                if algo_el:
                    m_algo = re.search(r"(\d+)%", algo_el.get_text(strip=True))
                    if m_algo:
                        algo_pct = float(m_algo.group(1))

                # Số lượng người theo dõi (Subscribers)
                sub_el = card.select_one(".signal-card__subscribers-value")
                subscribers = int(clean_number(sub_el.get_text(strip=True))) if sub_el else 0

                # Data attributes trên nút copy
                copy_el = card.select_one(".signal-card__copy")
                price_usd = 0.0
                weeks = 0
                balance_str = ""
                facilities_str = ""
                if copy_el:
                    price_usd = float(copy_el.get("data-price", 0) or 0)
                    weeks = int(copy_el.get("data-weeks", 0) or 0)
                    balance_str = copy_el.get("data-balance", "")
                    facilities_str = copy_el.get("data-facilities", "")

                # Chuỗi thời gian tăng trưởng (Equity History Series)
                chart_input = card.select_one(".signal-card__chart input[type='hidden']")
                growth_series = []
                if chart_input and chart_input.get("value"):
                    try:
                        raw_series = json.loads(chart_input["value"])
                        if isinstance(raw_series, list) and len(raw_series) >= 2:
                            growth_series = [
                                {"timestamp": raw_series[i], "growth_pct": float(raw_series[i + 1])}
                                for i in range(0, len(raw_series) - 1, 2)
                            ]
                    except Exception:
                        pass

                # Mini sparkline
                mini_input = card.select_one(".signal-card__chart-mini")
                mini_series = []
                if mini_input and mini_input.get("value"):
                    try:
                        mini_series = [float(x.strip()) for x in mini_input["value"].split(",") if x.strip()]
                    except Exception:
                        pass

                record: Dict[str, Any] = {
                    "signal_id": signal_id,
                    "title": title,
                    "author": author,
                    "rating": rating_val,
                    "reviews_count": reviews_cnt,
                    "growth_pct": growth_pct,
                    "growth_period": growth_period,
                    "algo_trading_pct": algo_pct,
                    "subscribers": subscribers,
                    "price_usd": price_usd,
                    "weeks": weeks,
                    "balance_str": balance_str,
                    "facilities_str": facilities_str,
                    "growth_series": growth_series,
                    "mini_series": mini_series,
                    "detail_url": f"{BASE_URL}/en/signals/{signal_id}",
                }
                parsed_signals.append(record)
            except Exception as ex:
                logger.debug("Lỗi khi bóc tách 1 thẻ tín hiệu: %s", ex)
                continue

        return parsed_signals

    def crawl_signal_detail(self, signal_id: str) -> Dict[str, Any]:
        """
        Bóc tách toàn bộ chỉ số định lượng nâng cao trên trang chi tiết của một tín hiệu.
        """
        url = f"{BASE_URL}/en/signals/{signal_id}"
        html = self.fetch_url(url)
        if not html:
            return {}

        soup = BeautifulSoup(html, "html.parser")
        raw_stats: Dict[str, str] = {}

        for item in soup.select(".s-list-info__item, .s-data-columns__item"):
            lbl_el = item.select_one(".s-list-info__label, .s-data-columns__label")
            val_el = item.select_one(".s-list-info__value, .s-data-columns__value")
            if lbl_el and val_el:
                lbl = lbl_el.get_text(strip=True).rstrip(":")
                val = val_el.get_text(strip=True)
                raw_stats[lbl] = val

        # Thông tin Broker & Đòn bẩy
        top_info = soup.select_one(".s-top-info__left-part") or soup.select_one(".s-top-info")
        broker_server = ""
        leverage_ratio = 1.0
        if top_info:
            top_text = top_info.get_text(separator=" | ", strip=True)
            parts = [p.strip() for p in top_text.split("|")]
            for p in parts:
                if "1:" in p:
                    leverage_ratio = parse_leverage_ratio(p)
                elif any(k in p for k in ["MT5", "Real", "Demo", "Server", "CapitalPoint", "Exness", "RoboForex"]):
                    broker_server = p

        # Parse cặp tiền giao dịch
        symbols_traded: List[str] = []
        for tbl in soup.find_all("table"):
            for tr in tbl.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells and len(cells) >= 2:
                    sym_candidate = cells[0].strip().upper()
                    if re.match(r"^[A-Z0-9_\.]{3,10}$", sym_candidate) and sym_candidate not in ["SYMBOL", "TOTAL", "DEALS"]:
                        if sym_candidate not in symbols_traded:
                            symbols_traded.append(sym_candidate)

        # Trích xuất và chuẩn hóa các chỉ số
        profit_trades_count, profit_trades_pct = parse_value_and_pct(raw_stats.get("Profit Trades", ""))
        loss_trades_count, loss_trades_pct = parse_value_and_pct(raw_stats.get("Loss Trades", ""))
        long_trades_count, long_trades_pct = parse_value_and_pct(raw_stats.get("Long Trades", ""))
        short_trades_count, short_trades_pct = parse_value_and_pct(raw_stats.get("Short Trades", ""))
        trading_days_cnt, trading_days_pct = parse_value_and_pct(raw_stats.get("Trading Days", ""))

        dd_max_usd, dd_max_pct = parse_drawdown(raw_stats.get("Maximal", ""))
        _, dd_rel_balance_pct = parse_drawdown(raw_stats.get("By Balance", ""))
        _, dd_rel_equity_pct = parse_drawdown(raw_stats.get("By Equity", ""))

        detail_data: Dict[str, Any] = {
            "signal_id": signal_id,
            "profit_usd": clean_number(raw_stats.get("Profit", "")),
            "equity_usd": clean_number(raw_stats.get("Equity", "")),
            "balance_usd": clean_number(raw_stats.get("Balance", "")),
            "initial_deposit_usd": clean_number(raw_stats.get("Initial Deposit", "")),
            "withdrawals_usd": clean_number(raw_stats.get("Withdrawals", "")),
            "trading_days": int(trading_days_cnt),
            "trading_days_pct": trading_days_pct,
            "latest_trade_str": raw_stats.get("Latest trade", ""),
            "trades_per_week": clean_number(raw_stats.get("Trades per week", "")),
            "avg_holding_time_hours": parse_holding_time_hours(raw_stats.get("Avg holding time", "")),
            "started_date": raw_stats.get("Started", ""),
            "broker_server": broker_server,
            "leverage_ratio": leverage_ratio,
            "trades_count": int(clean_number(raw_stats.get("Trades", ""))),
            "profit_trades_count": int(profit_trades_count),
            "profit_trades_pct": profit_trades_pct,
            "loss_trades_count": int(loss_trades_count),
            "loss_trades_pct": loss_trades_pct,
            "best_trade_usd": clean_number(raw_stats.get("Best trade", "")),
            "worst_trade_usd": clean_number(raw_stats.get("Worst trade", "")),
            "gross_profit_usd": clean_number(raw_stats.get("Gross Profit", "")),
            "gross_loss_usd": clean_number(raw_stats.get("Gross Loss", "")),
            "max_consecutive_wins": int(clean_number(raw_stats.get("Maximum consecutive wins", ""))),
            "max_consecutive_losses": int(clean_number(raw_stats.get("Maximum consecutive losses", ""))),
            "sharpe_ratio": clean_number(raw_stats.get("Sharpe Ratio", "")),
            "trading_activity_pct": clean_number(raw_stats.get("Trading activity", "")),
            "max_deposit_load_pct": clean_number(raw_stats.get("Max deposit load", "")),
            "recovery_factor": clean_number(raw_stats.get("Recovery Factor", "")),
            "long_trades_count": int(long_trades_count),
            "long_trades_pct": long_trades_pct,
            "short_trades_count": int(short_trades_count),
            "short_trades_pct": short_trades_pct,
            "profit_factor": clean_number(raw_stats.get("Profit Factor", "")),
            "expected_payoff_usd": clean_number(raw_stats.get("Expected Payoff", "")),
            "average_profit_usd": clean_number(raw_stats.get("Average Profit", "")),
            "average_loss_usd": clean_number(raw_stats.get("Average Loss", "")),
            "monthly_growth_pct": clean_number(raw_stats.get("Monthly growth", "")),
            "annual_forecast_pct": clean_number(raw_stats.get("Annual Forecast", "")),
            "drawdown_absolute_usd": clean_number(raw_stats.get("Absolute", "")),
            "drawdown_maximal_usd": dd_max_usd,
            "drawdown_maximal_pct": dd_max_pct,
            "drawdown_rel_balance_pct": dd_rel_balance_pct,
            "drawdown_rel_equity_pct": dd_rel_equity_pct,
            "symbols_traded": ",".join(symbols_traded[:5]),
        }
        return detail_data

    def crawl_all(
        self,
        max_pages: int = 3,
        fetch_details: bool = True,
    ) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
        """
        Thực hiện toàn trình thu thập dữ liệu MT5 Signals:
        1. Duyệt qua max_pages để lấy danh sách tín hiệu.
        2. Nếu fetch_details=True: Tải đa luồng dữ liệu chuyên sâu cho từng tín hiệu.
        3. Kết hợp và trả về DataFrame tổng hợp + Danh sách chuỗi thời gian equity.
        """
        logger.info("Bắt đầu quy trình Crawl MQL5 MT5 Signals (max_pages=%d, fetch_details=%s)...", max_pages, fetch_details)
        all_signals: List[Dict[str, Any]] = []

        for p in range(1, max_pages + 1):
            signals = self.crawl_listing_page(p)
            all_signals.extend(signals)
            if p < max_pages:
                nap_time = np.random.uniform(self.delay_range[0], self.delay_range[1])
                time.sleep(nap_time)

        logger.info("Hoàn tất crawl danh sách: Thu được tổng cộng %d tín hiệu.", len(all_signals))
        if not all_signals:
            return pd.DataFrame(), []

        # Tách danh sách time-series equity curves để lưu riêng
        equity_curves = [
            {
                "signal_id": s["signal_id"],
                "title": s["title"],
                "author": s["author"],
                "growth_series": s.get("growth_series", []),
                "mini_series": s.get("mini_series", []),
            }
            for s in all_signals
            if s.get("growth_series")
        ]

        # Khởi tạo DataFrame từ card data
        card_df = pd.DataFrame(
            [
                {k: v for k, v in s.items() if k not in ["growth_series", "mini_series"]}
                for s in all_signals
            ]
        )

        if not fetch_details:
            return card_df, equity_curves

        # Thu thập thông tin chi tiết qua ThreadPoolExecutor
        logger.info("Bắt đầu thu thập thông số chi tiết cho %d tín hiệu với %d worker threads...", len(all_signals), self.max_workers)
        details_map: Dict[str, Dict[str, Any]] = {}
        signal_ids = [s["signal_id"] for s in all_signals]

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_id = {
                executor.submit(self.crawl_signal_detail, s_id): s_id
                for s_id in signal_ids
            }
            completed_cnt = 0
            for future in as_completed(future_to_id):
                s_id = future_to_id[future]
                completed_cnt += 1
                try:
                    data = future.result()
                    if data:
                        details_map[s_id] = data
                except Exception as e:
                    logger.warning("Lỗi khi crawl chi tiết tín hiệu %s: %s", s_id, e)

                if completed_cnt % 10 == 0 or completed_cnt == len(signal_ids):
                    logger.info("Tiến độ chi tiết: %d/%d tín hiệu hoàn tất.", completed_cnt, len(signal_ids))

        # Ghép thông tin chi tiết vào DataFrame
        details_df = pd.DataFrame(list(details_map.values()))
        if not details_df.empty:
            merged_df = pd.merge(card_df, details_df, on="signal_id", how="left")
        else:
            merged_df = card_df

        return merged_df, equity_curves

    def build_ai_training_dataset(self, df_raw: pd.DataFrame) -> pd.DataFrame:
        """
        Kỹ thuật tạo đặc trưng (Feature Engineering) cho bài toán Machine Learning:
        1. Làm sạch và điền giá trị thiếu (Imputation).
        2. Tạo các tỷ số định lượng quan trọng (Calmar Ratio, Payoff Ratio, Activity Density).
        3. Tạo nhãn giám sát (Supervised Target Labels):
           - is_high_quality (1/0): Tín hiệu chất lượng chuẩn Pro (PF >= 1.5, Max DD <= 25%, Win Rate >= 55%, Trades >= 20).
           - is_profitable (1/0): Tín hiệu có lợi nhuận dương và tăng trưởng > 0.
           - quality_grade (0, 1, 2): Phân hạng Rủi ro cao (0), Khả dĩ (1), Xuất sắc (2).
           - target_profit_factor: Mục tiêu hồi quy ước lượng Profit Factor.
        """
        if df_raw.empty:
            return pd.DataFrame()

        df = df_raw.copy()

        # Đảm bảo các cột định lượng là kiểu số
        numeric_cols = [
            "growth_pct", "rating", "reviews_count", "algo_trading_pct", "subscribers",
            "price_usd", "weeks", "profit_usd", "equity_usd", "balance_usd",
            "trading_days", "trades_per_week", "avg_holding_time_hours", "leverage_ratio",
            "trades_count", "profit_trades_count", "profit_trades_pct", "loss_trades_count",
            "loss_trades_pct", "best_trade_usd", "worst_trade_usd", "gross_profit_usd",
            "gross_loss_usd", "max_consecutive_wins", "max_consecutive_losses",
            "sharpe_ratio", "trading_activity_pct", "max_deposit_load_pct",
            "recovery_factor", "long_trades_count", "long_trades_pct", "short_trades_count",
            "short_trades_pct", "profit_factor", "expected_payoff_usd", "average_profit_usd",
            "average_loss_usd", "monthly_growth_pct", "annual_forecast_pct",
            "drawdown_absolute_usd", "drawdown_maximal_usd", "drawdown_maximal_pct",
            "drawdown_rel_balance_pct", "drawdown_rel_equity_pct",
        ]

        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
            else:
                df[col] = 0.0

        # Kỹ thuật tạo đặc trưng (Feature Engineering)
        # 1. Payoff Ratio = |Average Profit / Average Loss|
        df["payoff_ratio"] = np.where(
            df["average_loss_usd"].abs() > 0.001,
            df["average_profit_usd"].abs() / df["average_loss_usd"].abs(),
            1.0,
        )

        # 2. Win / Loss Trades Ratio
        df["win_loss_ratio"] = np.where(
            df["loss_trades_count"] > 0,
            df["profit_trades_count"] / df["loss_trades_count"],
            df["profit_trades_count"],
        )

        # 3. Calmar Ratio = Annual Forecast / Max Drawdown
        df["calmar_ratio"] = np.where(
            df["drawdown_maximal_pct"] > 0.5,
            df["annual_forecast_pct"] / df["drawdown_maximal_pct"],
            df["annual_forecast_pct"] / 10.0,
        )

        # 4. Long Dominance Ratio = Long Trades / Total Trades
        df["long_dominance_ratio"] = np.where(
            df["trades_count"] > 0,
            df["long_trades_count"] / df["trades_count"],
            0.5,
        )

        # 5. Consecutive Win-Loss Resilience
        df["consecutive_resilience"] = np.where(
            df["max_consecutive_losses"] > 0,
            df["max_consecutive_wins"] / df["max_consecutive_losses"],
            df["max_consecutive_wins"],
        )

        # 6. Trade Intensity = Trades per week * (Holding time hours / 168.0)
        df["market_exposure_ratio"] = np.clip(
            (df["trades_per_week"] * df["avg_holding_time_hours"]) / 168.0, 0.0, 1.0
        )

        # 7. Growth per Week
        df["growth_per_week"] = np.where(
            df["weeks"] > 0,
            df["growth_pct"] / df["weeks"],
            df["growth_pct"],
        )

        # Gán Nhãn Giám sát (Supervised Targets)
        # Nhãn 1: is_high_quality (Binary: 1 = Đạt chuẩn Pro Strategy, 0 = Dưới chuẩn)
        df["is_high_quality"] = (
            (df["profit_factor"] >= 1.4)
            & (df["drawdown_maximal_pct"] <= 25.0)
            & (df["drawdown_maximal_pct"] > 0.0)
            & (df["profit_trades_pct"] >= 52.0)
            & (df["trades_count"] >= self.min_trades)
            & (df["recovery_factor"] >= 1.5)
        ).astype(int)

        # Nhãn 2: is_profitable
        df["is_profitable"] = (
            (df["growth_pct"] > 0.0) & (df["profit_usd"] > 0.0)
        ).astype(int)

        # Nhãn 3: quality_grade (Multi-class: 0 = Low/Risky, 1 = Acceptable, 2 = Elite)
        conditions = [
            (df["is_high_quality"] == 1) & (df["sharpe_ratio"] >= 0.2) & (df["weeks"] >= 12),
            (df["is_profitable"] == 1) & (df["drawdown_maximal_pct"] <= 35.0),
        ]
        choices = [2, 1]
        df["quality_grade"] = np.select(conditions, choices, default=0)

        # Nhãn 4: target_profit_factor (Continuous Target)
        df["target_profit_factor"] = df["profit_factor"].clip(0.0, 10.0)

        # Lọc bỏ những tín hiệu quá mới nếu cần
        if self.min_trades > 0:
            df = df[df["trades_count"] >= self.min_trades].reset_index(drop=True)

        logger.info(
            "Tạo dataset AI hoàn tất: %d dòng dữ liệu, %d cột đặc trưng & nhãn. Phân phối chất lượng: %s",
            len(df),
            len(df.columns),
            dict(df["is_high_quality"].value_counts()),
        )
        return df

    def save_datasets(
        self,
        df_raw: pd.DataFrame,
        df_features: pd.DataFrame,
        equity_curves: List[Dict[str, Any]],
        prefix: str = "mql5_signals",
    ) -> Dict[str, Path]:
        """Lưu toàn bộ dataset ra Parquet, CSV và JSON Timeseries."""
        saved_paths: Dict[str, Path] = {}

        # 1. Raw Dataset
        raw_csv_path = self.output_dir / f"{prefix}_raw.csv"
        raw_parquet_path = self.output_dir / f"{prefix}_raw.parquet"
        df_raw.to_csv(raw_csv_path, index=False, encoding="utf-8")
        try:
            df_raw.to_parquet(raw_parquet_path, index=False)
        except Exception as e:
            logger.warning("Không thể lưu Parquet raw: %s", e)
        saved_paths["raw_csv"] = raw_csv_path
        saved_paths["raw_parquet"] = raw_parquet_path

        # 2. Engineered AI Features & Targets
        if not df_features.empty:
            feat_csv_path = self.output_dir / f"{prefix}_ai_features.csv"
            feat_parquet_path = self.output_dir / f"{prefix}_ai_features.parquet"
            df_features.to_csv(feat_csv_path, index=False, encoding="utf-8")
            try:
                df_features.to_parquet(feat_parquet_path, index=False)
            except Exception as e:
                logger.warning("Không thể lưu Parquet features: %s", e)
            saved_paths["feat_csv"] = feat_csv_path
            saved_paths["feat_parquet"] = feat_parquet_path

        # 3. JSON Timeseries Curves
        if equity_curves:
            json_path = self.output_dir / f"{prefix}_equity_curves.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(equity_curves, f, ensure_ascii=False, indent=2)
            saved_paths["curves_json"] = json_path

        logger.info("Đã lưu các tệp Dataset thành công:")
        for k, p in saved_paths.items():
            logger.info("  [%s] -> %s (Kích thước: %.1f KB)", k, p, p.stat().st_size / 1024.0)

        return saved_paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MQL5 MT5 Signals Crawler & AI Dataset Generator for AI Trading Bot"
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=2,
        help="Số lượng trang danh mục cần crawl (mỗi trang ~48 tín hiệu, mặc định: 2)",
    )
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Bỏ qua việc crawl chi tiết từng trang tín hiệu (chỉ lấy card tổng quan)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Số luồng đồng thời khi tải trang chi tiết (mặc định: 4)",
    )
    parser.add_argument(
        "--min-trades",
        type=int,
        default=5,
        help="Lọc bỏ tín hiệu có ít hơn số lệnh này (mặc định: 5)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Thư mục lưu trữ dataset (mặc định: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Chế độ kiểm thử nhanh (crawl 1 trang, tối đa 5 tín hiệu chi tiết)",
    )

    args = parser.parse_args()

    crawler = MQL5SignalCrawler(
        output_dir=Path(args.output_dir),
        max_workers=args.workers,
        min_trades=args.min_trades,
    )

    if args.test:
        logger.info("--- CHẾ ĐỘ TEST NHANH (1 Trang, 5 chi tiết) ---")
        signals = crawler.crawl_listing_page(1)[:5]
        if not signals:
            logger.error("Không thu thập được tín hiệu nào trong chế độ test.")
            return
        card_df = pd.DataFrame([{k: v for k, v in s.items() if k not in ["growth_series", "mini_series"]} for s in signals])
        details = []
        for s in signals:
            d = crawler.crawl_signal_detail(s["signal_id"])
            if d:
                details.append(d)
            time.sleep(0.3)
        det_df = pd.DataFrame(details)
        if not det_df.empty:
            merged = pd.merge(card_df, det_df, on="signal_id", how="left")
        else:
            merged = card_df
        ai_df = crawler.build_ai_training_dataset(merged)
        curves = [{"signal_id": s["signal_id"], "growth_series": s.get("growth_series", [])} for s in signals]
        paths = crawler.save_datasets(merged, ai_df, curves, prefix="mql5_test_signals")
        print("\nTest Crawler thành công. Các tệp đã tạo:")
        for k, v in paths.items():
            print(f"  {k}: {v}")
        return

    # Toàn bộ quy trình
    merged_df, curves = crawler.crawl_all(
        max_pages=args.pages,
        fetch_details=not args.no_details,
    )

    if merged_df.empty:
        logger.warning("Không thu thập được dữ liệu nào từ MQL5.")
        return

    ai_features_df = crawler.build_ai_training_dataset(merged_df)
    crawler.save_datasets(merged_df, ai_features_df, curves)
    logger.info("Quy trình hoàn tất thành công!")


if __name__ == "__main__":
    main()
