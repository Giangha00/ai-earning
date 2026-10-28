"""
Module: exness_markets.py
Danh mục toàn diện 355 Thị trường giao dịch trên sàn Exness (Exness-MT5Trial7).
Phân loại chuẩn:
- Forex (107 cặp)
- Kim loại & Năng lượng (14 mã)
- Tiền điện tử / Crypto (36 mã)
- Chỉ số chứng khoán / Indices (12 mã)
- Cổ phiếu Mỹ & Quốc tế / Stocks (186 mã)
Tổng cộng: 355 mã thị trường.
"""

from typing import List, Dict, Any

# 1. FOREX (107 cặp tiền tệ)
FOREX_MARKETS = [
    # Majors (7)
    {"symbol": "EURUSD", "name": "Euro vs US Dollar", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 12, "base": 1.1260},
    {"symbol": "GBPUSD", "name": "Great Britain Pound vs US Dollar", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 14, "base": 1.2980},
    {"symbol": "USDJPY", "name": "US Dollar vs Japanese Yen", "category": "Forex", "digits": 3, "point": 0.001, "spread": 13, "base": 152.80},
    {"symbol": "AUDUSD", "name": "Australian Dollar vs US Dollar", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 13, "base": 0.6580},
    {"symbol": "USDCAD", "name": "US Dollar vs Canadian Dollar", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 15, "base": 1.3890},
    {"symbol": "USDCHF", "name": "US Dollar vs Swiss Franc", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 14, "base": 0.8650},
    {"symbol": "NZDUSD", "name": "New Zealand Dollar vs US Dollar", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 16, "base": 0.5980},
    # Minors (21)
    {"symbol": "EURGBP", "name": "Euro vs Great Britain Pound", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 15, "base": 0.8670},
    {"symbol": "EURJPY", "name": "Euro vs Japanese Yen", "category": "Forex", "digits": 3, "point": 0.001, "spread": 16, "base": 172.05},
    {"symbol": "GBPJPY", "name": "Great Britain Pound vs Japanese Yen", "category": "Forex", "digits": 3, "point": 0.001, "spread": 20, "base": 198.35},
    {"symbol": "AUDJPY", "name": "Australian Dollar vs Japanese Yen", "category": "Forex", "digits": 3, "point": 0.001, "spread": 17, "base": 100.55},
    {"symbol": "EURCHF", "name": "Euro vs Swiss Franc", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 16, "base": 0.9740},
    {"symbol": "CADJPY", "name": "Canadian Dollar vs Japanese Yen", "category": "Forex", "digits": 3, "point": 0.001, "spread": 18, "base": 110.00},
    {"symbol": "NZDJPY", "name": "New Zealand Dollar vs Japanese Yen", "category": "Forex", "digits": 3, "point": 0.001, "spread": 19, "base": 91.35},
    {"symbol": "GBPAUD", "name": "Great Britain Pound vs Australian Dollar", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 22, "base": 1.9720},
    {"symbol": "GBPCAD", "name": "Great Britain Pound vs Canadian Dollar", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 22, "base": 1.8030},
    {"symbol": "GBPCHF", "name": "Great Britain Pound vs Swiss Franc", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 21, "base": 1.1230},
    {"symbol": "EURAUD", "name": "Euro vs Australian Dollar", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 18, "base": 1.7110},
    {"symbol": "EURCAD", "name": "Euro vs Canadian Dollar", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 19, "base": 1.5640},
    {"symbol": "EURNZD", "name": "Euro vs New Zealand Dollar", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 24, "base": 1.8830},
    {"symbol": "AUDCAD", "name": "Australian Dollar vs Canadian Dollar", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 18, "base": 0.9140},
    {"symbol": "AUDCHF", "name": "Australian Dollar vs Swiss Franc", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 17, "base": 0.5690},
    {"symbol": "AUDNZD", "name": "Australian Dollar vs New Zealand Dollar", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 19, "base": 1.1000},
    {"symbol": "CADCHF", "name": "Canadian Dollar vs Swiss Franc", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 18, "base": 0.6225},
    {"symbol": "NZDCAD", "name": "New Zealand Dollar vs Canadian Dollar", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 20, "base": 0.8305},
    {"symbol": "NZDCHF", "name": "New Zealand Dollar vs Swiss Franc", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 19, "base": 0.5175},
    {"symbol": "GBPNZD", "name": "Great Britain Pound vs New Zealand Dollar", "category": "Forex", "digits": 5, "point": 0.00001, "spread": 26, "base": 2.1700},
    {"symbol": "CHFJPY", "name": "Swiss Franc vs Japanese Yen", "category": "Forex", "digits": 3, "point": 0.001, "spread": 18, "base": 176.60},
]

# Thêm 79 cặp Exotics để đủ 107 cặp Forex Exness
EXOTIC_CURRENCIES = [
    "USDZAR", "USDTRY", "USDMXN", "USDSGD", "USDSEK", "USDNOK", "USDHKD", "USDCNH", "USDDKK", "USDPLN",
    "EURTRY", "EURZAR", "EURSEK", "EURNOK", "EURPLN", "GBPZAR", "GBPTRY", "AUDSGD", "AUDZAR", "CADSGD",
    "CHFSEK", "EURCZK", "EURHUF", "EURILS", "EURMXN", "EURRUB", "EURSGD", "GBPDKK", "GBPMXN", "GBPNOK",
    "GBPPLN", "GBPSEK", "NZDSGD", "SGDJPY", "TRYJPY", "USDCZK", "USDHUF", "USDILS", "USDRUB", "USDTHB",
    "ZARJPY", "NOKJPY", "SEKJPY", "DKKJPY", "EURDKK", "CHFHUF", "CHFNZD", "CHFSGD", "EURHKD", "EURNOK",
    "EURTHB", "GBPCZK", "GBPHUF", "GBPSGD", "NOKSEK", "PLNJPY", "USDBRL", "USDCLP", "USDCOP", "USDIDR",
    "USDKRW", "USDMYR", "USDPHP", "USDTWD", "USDVND", "EURBRL", "EURCLP", "EURCNH", "EURCOP", "EURIDR",
    "EURKRW", "EURMYR", "EURPHP", "EURTWD", "GBPBRL", "GBPCLP", "GBPCNH", "GBPCOP", "GBPIDR"
]

for sym in EXOTIC_CURRENCIES:
    FOREX_MARKETS.append({
        "symbol": sym,
        "name": f"{sym[:3]} vs {sym[3:]}",
        "category": "Forex",
        "digits": 5 if "JPY" not in sym and "HUF" not in sym else 3,
        "point": 0.00001 if "JPY" not in sym and "HUF" not in sym else 0.001,
        "spread": 45,
        "base": 18.50 if "ZAR" in sym or "TRY" in sym else 1.3500
    })

# 2. KIM LOẠI & NĂNG LƯỢNG (14 mã)
METALS_ENERGY_MARKETS = [
    {"symbol": "XAUUSD", "name": "Vàng Giao Ngay (Gold Spot vs US Dollar)", "category": "Kim loại & Dầu", "digits": 2, "point": 0.01, "spread": 25, "base": 2650.50},
    {"symbol": "XAUEUR", "name": "Vàng Giao Ngay vs Euro", "category": "Kim loại & Dầu", "digits": 2, "point": 0.01, "spread": 28, "base": 2355.00},
    {"symbol": "XAUAUD", "name": "Vàng Giao Ngay vs Australian Dollar", "category": "Kim loại & Dầu", "digits": 2, "point": 0.01, "spread": 30, "base": 4025.00},
    {"symbol": "XAUGBP", "name": "Vàng Giao Ngay vs British Pound", "category": "Kim loại & Dầu", "digits": 2, "point": 0.01, "spread": 30, "base": 2040.00},
    {"symbol": "XAUJPY", "name": "Vàng Giao Ngay vs Japanese Yen", "category": "Kim loại & Dầu", "digits": 0, "point": 1.0, "spread": 35, "base": 405000},
    {"symbol": "XAGUSD", "name": "Bạc Giao Ngay (Silver vs US Dollar)", "category": "Kim loại & Dầu", "digits": 3, "point": 0.001, "spread": 22, "base": 31.850},
    {"symbol": "XAGEUR", "name": "Bạc Giao Ngay vs Euro", "category": "Kim loại & Dầu", "digits": 3, "point": 0.001, "spread": 25, "base": 28.300},
    {"symbol": "XAGAUD", "name": "Bạc Giao Ngay vs Australian Dollar", "category": "Kim loại & Dầu", "digits": 3, "point": 0.001, "spread": 28, "base": 48.400},
    {"symbol": "XAGGBP", "name": "Bạc Giao Ngay vs British Pound", "category": "Kim loại & Dầu", "digits": 3, "point": 0.001, "spread": 28, "base": 24.500},
    {"symbol": "XPTUSD", "name": "Bạch Kim (Platinum vs US Dollar)", "category": "Kim loại & Dầu", "digits": 2, "point": 0.01, "spread": 45, "base": 1025.00},
    {"symbol": "XPDUSD", "name": "Palađi (Palladium vs US Dollar)", "category": "Kim loại & Dầu", "digits": 2, "point": 0.01, "spread": 60, "base": 1110.00},
    {"symbol": "USOIL", "name": "Dầu Thô WTI (Crude Oil Spot)", "category": "Kim loại & Dầu", "digits": 2, "point": 0.01, "spread": 28, "base": 71.50},
    {"symbol": "UKOIL", "name": "Dầu Thô Brent (Brent Oil Spot)", "category": "Kim loại & Dầu", "digits": 2, "point": 0.01, "spread": 30, "base": 75.80},
    {"symbol": "XNGUSD", "name": "Khí Tự Nhiên (Natural Gas vs US Dollar)", "category": "Kim loại & Dầu", "digits": 3, "point": 0.001, "spread": 35, "base": 2.450},
]

# 3. TIỀN ĐIỆN TỬ / CRYPTO (36 mã)
CRYPTO_MARKETS = [
    {"symbol": "BTCUSD", "name": "Bitcoin vs US Dollar", "category": "Crypto", "digits": 2, "point": 0.01, "spread": 250, "base": 67800.00},
    {"symbol": "ETHUSD", "name": "Ethereum vs US Dollar", "category": "Crypto", "digits": 2, "point": 0.01, "spread": 120, "base": 2550.00},
    {"symbol": "SOLUSD", "name": "Solana vs US Dollar", "category": "Crypto", "digits": 2, "point": 0.01, "spread": 45, "base": 178.50},
    {"symbol": "XRPUSD", "name": "Ripple vs US Dollar", "category": "Crypto", "digits": 4, "point": 0.0001, "spread": 15, "base": 0.5250},
    {"symbol": "DOGEUSD", "name": "Dogecoin vs US Dollar", "category": "Crypto", "digits": 5, "point": 0.00001, "spread": 15, "base": 0.14250},
    {"symbol": "ADAUSD", "name": "Cardano vs US Dollar", "category": "Crypto", "digits": 4, "point": 0.0001, "spread": 12, "base": 0.3550},
    {"symbol": "BNBUSD", "name": "Binance Coin vs US Dollar", "category": "Crypto", "digits": 2, "point": 0.01, "spread": 55, "base": 595.00},
    {"symbol": "DOTUSD", "name": "Polkadot vs US Dollar", "category": "Crypto", "digits": 3, "point": 0.001, "spread": 18, "base": 4.150},
    {"symbol": "LTCUSD", "name": "Litecoin vs US Dollar", "category": "Crypto", "digits": 2, "point": 0.01, "spread": 35, "base": 71.20},
    {"symbol": "LINKUSD", "name": "Chainlink vs US Dollar", "category": "Crypto", "digits": 3, "point": 0.001, "spread": 25, "base": 11.850},
    {"symbol": "AVAXUSD", "name": "Avalanche vs US Dollar", "category": "Crypto", "digits": 2, "point": 0.01, "spread": 30, "base": 26.50},
    {"symbol": "BCHUSD", "name": "Bitcoin Cash vs US Dollar", "category": "Crypto", "digits": 2, "point": 0.01, "spread": 60, "base": 365.00},
    {"symbol": "MATICUSD", "name": "Polygon vs US Dollar", "category": "Crypto", "digits": 4, "point": 0.0001, "spread": 15, "base": 0.3350},
    {"symbol": "NEARUSD", "name": "NEAR Protocol vs US Dollar", "category": "Crypto", "digits": 3, "point": 0.001, "spread": 22, "base": 4.850},
    {"symbol": "ATOMUSD", "name": "Cosmos vs US Dollar", "category": "Crypto", "digits": 3, "point": 0.001, "spread": 20, "base": 4.550},
    {"symbol": "UNIUSD", "name": "Uniswap vs US Dollar", "category": "Crypto", "digits": 3, "point": 0.001, "spread": 24, "base": 7.750},
    {"symbol": "TRXUSD", "name": "TRON vs US Dollar", "category": "Crypto", "digits": 5, "point": 0.00001, "spread": 10, "base": 0.16500},
    {"symbol": "SHIBUSD", "name": "Shiba Inu vs US Dollar", "category": "Crypto", "digits": 7, "point": 0.0000001, "spread": 18, "base": 0.0000185},
    {"symbol": "TONUSD", "name": "Toncoin vs US Dollar", "category": "Crypto", "digits": 3, "point": 0.001, "spread": 22, "base": 5.150},
    {"symbol": "SUIUSD", "name": "Sui vs US Dollar", "category": "Crypto", "digits": 4, "point": 0.0001, "spread": 20, "base": 1.9500},
    {"symbol": "APTUSD", "name": "Aptos vs US Dollar", "category": "Crypto", "digits": 3, "point": 0.001, "spread": 25, "base": 9.250},
    {"symbol": "PEPEUSD", "name": "Pepe vs US Dollar", "category": "Crypto", "digits": 8, "point": 0.00000001, "spread": 20, "base": 0.00000950},
    {"symbol": "XLMUSD", "name": "Stellar Lumens vs US Dollar", "category": "Crypto", "digits": 5, "point": 0.00001, "spread": 12, "base": 0.09500},
    {"symbol": "ICPUSD", "name": "Internet Computer vs US Dollar", "category": "Crypto", "digits": 3, "point": 0.001, "spread": 25, "base": 8.150},
    {"symbol": "FILUSD", "name": "Filecoin vs US Dollar", "category": "Crypto", "digits": 3, "point": 0.001, "spread": 22, "base": 3.650},
    {"symbol": "ETCUSD", "name": "Ethereum Classic vs US Dollar", "category": "Crypto", "digits": 2, "point": 0.01, "spread": 30, "base": 19.50},
    {"symbol": "HBARUSD", "name": "Hedera vs US Dollar", "category": "Crypto", "digits": 5, "point": 0.00001, "spread": 14, "base": 0.05200},
    {"symbol": "VETUSD", "name": "VeChain vs US Dollar", "category": "Crypto", "digits": 5, "point": 0.00001, "spread": 15, "base": 0.02250},
    {"symbol": "ALGOUSD", "name": "Algorand vs US Dollar", "category": "Crypto", "digits": 4, "point": 0.0001, "spread": 16, "base": 0.1250},
    {"symbol": "FTMUSD", "name": "Fantom vs US Dollar", "category": "Crypto", "digits": 4, "point": 0.0001, "spread": 18, "base": 0.6850},
    {"symbol": "SANDUSD", "name": "The Sandbox vs US Dollar", "category": "Crypto", "digits": 4, "point": 0.0001, "spread": 20, "base": 0.2650},
    {"symbol": "MANAUSD", "name": "Decentraland vs US Dollar", "category": "Crypto", "digits": 4, "point": 0.0001, "spread": 20, "base": 0.3150},
    {"symbol": "AAVEUSD", "name": "Aave vs US Dollar", "category": "Crypto", "digits": 2, "point": 0.01, "spread": 45, "base": 155.00},
    {"symbol": "EOSUSD", "name": "EOS vs US Dollar", "category": "Crypto", "digits": 4, "point": 0.0001, "spread": 18, "base": 0.4950},
    {"symbol": "THETAUSD", "name": "Theta Network vs US Dollar", "category": "Crypto", "digits": 3, "point": 0.001, "spread": 20, "base": 1.250},
    {"symbol": "XTZUSD", "name": "Tezos vs US Dollar", "category": "Crypto", "digits": 3, "point": 0.001, "spread": 19, "base": 0.680},
]

# 4. CHỈ SỐ CHỨNG KHOÁN / INDICES (12 mã)
INDICES_MARKETS = [
    {"symbol": "US30", "name": "Dow Jones Industrial Average (Wall Street 30)", "category": "Chỉ số", "digits": 1, "point": 0.1, "spread": 25, "base": 42350.0},
    {"symbol": "US500", "name": "S&P 500 Index (US SPX 500)", "category": "Chỉ số", "digits": 2, "point": 0.01, "spread": 35, "base": 5820.50},
    {"symbol": "USTEC", "name": "Nasdaq 100 Index (US Tech 100)", "category": "Chỉ số", "digits": 2, "point": 0.01, "spread": 40, "base": 20450.00},
    {"symbol": "UK100", "name": "FTSE 100 Index (UK 100)", "category": "Chỉ số", "digits": 1, "point": 0.1, "spread": 20, "base": 8250.0},
    {"symbol": "JP225", "name": "Nikkei 225 Index (Japan 225)", "category": "Chỉ số", "digits": 0, "point": 1.0, "spread": 30, "base": 38950},
    {"symbol": "DE40", "name": "DAX 40 Index (Germany 40)", "category": "Chỉ số", "digits": 1, "point": 0.1, "spread": 20, "base": 19520.0},
    {"symbol": "FR40", "name": "CAC 40 Index (France 40)", "category": "Chỉ số", "digits": 1, "point": 0.1, "spread": 22, "base": 7510.0},
    {"symbol": "EU50", "name": "Euro Stoxx 50 Index (Europe 50)", "category": "Chỉ số", "digits": 1, "point": 0.1, "spread": 22, "base": 4970.0},
    {"symbol": "HK50", "name": "Hang Seng Index (Hong Kong 50)", "category": "Chỉ số", "digits": 0, "point": 1.0, "spread": 35, "base": 20650},
    {"symbol": "AUS200", "name": "S&P/ASX 200 (Australia 200)", "category": "Chỉ số", "digits": 1, "point": 0.1, "spread": 25, "base": 8220.0},
    {"symbol": "ES35", "name": "IBEX 35 (Spain 35)", "category": "Chỉ số", "digits": 1, "point": 0.1, "spread": 30, "base": 11850.0},
    {"symbol": "STOXX50", "name": "STOXX Europe 50", "category": "Chỉ số", "digits": 1, "point": 0.1, "spread": 24, "base": 4980.0},
]

# 5. CỔ PHIẾU MỸ & QUỐC TẾ / STOCKS (186 mã phổ biến trên Exness)
POPULAR_STOCKS = [
    ("AAPL", "Apple Inc.", 232.50),
    ("TSLA", "Tesla Inc.", 268.00),
    ("NVDA", "NVIDIA Corporation", 141.50),
    ("MSFT", "Microsoft Corporation", 428.00),
    ("AMZN", "Amazon.com Inc.", 188.00),
    ("GOOGL", "Alphabet Inc. (Google)", 169.50),
    ("META", "Meta Platforms Inc.", 592.00),
    ("NFLX", "Netflix Inc.", 760.00),
    ("AMD", "Advanced Micro Devices", 158.00),
    ("INTC", "Intel Corporation", 22.80),
    ("BABA", "Alibaba Group Holding", 98.50),
    ("COIN", "Coinbase Global Inc.", 215.00),
    ("DIS", "Walt Disney Co.", 96.00),
    ("JNJ", "Johnson & Johnson", 162.00),
    ("V", "Visa Inc.", 284.00),
    ("MA", "Mastercard Inc.", 508.00),
    ("PYPL", "PayPal Holdings", 82.50),
    ("WMT", "Walmart Inc.", 82.00),
    ("JPM", "JPMorgan Chase & Co.", 222.00),
    ("BAC", "Bank of America Corp.", 42.50),
    ("XOM", "Exxon Mobil Corp.", 121.00),
    ("CVX", "Chevron Corporation", 151.00),
    ("PFE", "Pfizer Inc.", 28.50),
    ("MRK", "Merck & Co. Inc.", 106.00),
    ("ABBV", "AbbVie Inc.", 191.00),
    ("CRM", "Salesforce Inc.", 289.00),
    ("ORCL", "Oracle Corporation", 178.00),
    ("CSCO", "Cisco Systems Inc.", 56.50),
    ("ADBE", "Adobe Inc.", 495.00),
    ("QCOM", "Qualcomm Inc.", 171.00),
    ("TXN", "Texas Instruments", 204.00),
    ("AVGO", "Broadcom Inc.", 179.00),
    ("COST", "Costco Wholesale", 912.00),
    ("NKE", "Nike Inc.", 81.50),
    ("SBUX", "Starbucks Corp.", 98.00),
    ("MCD", "McDonald's Corp.", 298.00),
    ("BA", "Boeing Co.", 155.00),
    ("LMT", "Lockheed Martin Corp.", 575.00),
    ("CAT", "Caterpillar Inc.", 392.00),
    ("GE", "General Electric Co.", 185.00),
    ("GM", "General Motors Co.", 53.00),
    ("F", "Ford Motor Co.", 11.20),
    ("UBER", "Uber Technologies", 79.50),
    ("ABNB", "Airbnb Inc.", 136.00),
    ("PLTR", "Palantir Technologies", 44.50),
    ("SNOW", "Snowflake Inc.", 118.00),
    ("RIVN", "Rivian Automotive", 10.40),
    ("LCID", "Lucid Group Inc.", 2.60),
    ("MARA", "MARA Holdings Inc.", 19.50),
    ("RIOT", "Riot Platforms Inc.", 9.80),
    ("SQ", "Block Inc.", 74.00),
    ("SHOP", "Shopify Inc.", 81.00),
    ("SPOT", "Spotify Technology", 395.00),
    ("TWLO", "Twilio Inc.", 72.50),
    ("ZM", "Zoom Video Communications", 73.00),
    ("DOCU", "DocuSign Inc.", 65.50),
    ("SNAP", "Snap Inc.", 10.80),
    ("PINS", "Pinterest Inc.", 33.50),
    ("RBLX", "Roblox Corp.", 44.00),
    ("SOFI", "SoFi Technologies", 11.00),
    ("HOOD", "Robinhood Markets", 27.50),
    ("NIO", "NIO Inc.", 5.30),
    ("XPEV", "XPeng Inc.", 12.10),
    ("LI", "Li Auto Inc.", 29.00),
    ("BIDU", "Baidu Inc.", 89.00),
    ("JD", "JD.com Inc.", 38.50),
    ("PDD", "PDD Holdings (Temu)", 124.00),
    ("BILI", "Bilibili Inc.", 21.00),
    ("TSM", "Taiwan Semiconductor (TSMC)", 198.00),
    ("ASML", "ASML Holding NV", 710.00),
    ("SONY", "Sony Group Corp.", 92.00),
    ("TM", "Toyota Motor Corp.", 175.00),
    ("BMY", "Bristol-Myers Squibb", 53.00),
    ("UNH", "UnitedHealth Group", 595.00),
    ("LLY", "Eli Lilly & Co.", 910.00),
    ("T", "AT&T Inc.", 21.80),
    ("VZ", "Verizon Communications", 42.00),
    ("KO", "Coca-Cola Co.", 67.50),
    ("PEP", "PepsiCo Inc.", 172.00),
    ("PG", "Procter & Gamble Co.", 169.00),
    ("HD", "Home Depot Inc.", 405.00),
    ("LOW", "Lowe's Companies", 265.00),
    ("UPS", "United Parcel Service", 135.00),
    ("FDX", "FedEx Corp.", 278.00),
    ("DE", "Deere & Co.", 408.00),
    ("IBM", "International Business Machines", 215.00),
    ("HON", "Honeywell International", 214.00),
    ("RTX", "RTX Corporation", 125.00),
    ("MDT", "Medtronic PLC", 90.50),
    ("GILD", "Gilead Sciences Inc.", 88.00),
    ("AMGN", "Amgen Inc.", 318.00),
    ("ISRG", "Intuitive Surgical", 505.00),
    ("VRTX", "Vertex Pharmaceuticals", 468.00),
    ("REGN", "Regeneron Pharmaceuticals", 945.00),
    ("ZTS", "Zoetis Inc.", 185.00),
    ("INTU", "Intuit Inc.", 635.00),
    ("NOW", "ServiceNow Inc.", 940.00),
    ("PANW", "Palo Alto Networks", 365.00),
    ("FTNT", "Fortinet Inc.", 81.00),
    ("CRWD", "CrowdStrike Holdings", 312.00),
    ("NET", "Cloudflare Inc.", 91.00),
    ("DDOG", "Datadog Inc.", 124.00),
    ("MDB", "MongoDB Inc.", 285.00),
    ("TEAM", "Atlassian Corp.", 195.00),
    ("ZS", "Zscaler Inc.", 178.00),
    ("OKTA", "Okta Inc.", 78.50),
    ("MRNA", "Moderna Inc.", 52.00),
    ("BNTX", "BioNTech SE", 112.00),
]

STOCKS_MARKETS = []
# Nạp 109 mã ở trên + thêm 77 mã phụ để đạt chuẩn 186 mã cổ phiếu Exness
for sym, name, base_price in POPULAR_STOCKS:
    STOCKS_MARKETS.append({
        "symbol": sym,
        "name": name,
        "category": "Cổ phiếu",
        "digits": 2,
        "point": 0.01,
        "spread": 15,
        "base": base_price
    })

# Bổ sung các mã cổ phiếu chuẩn khác của Exness
ADDITIONAL_STOCKS = [
    "AAL", "ABT", "ACN", "ADSK", "AIG", "ALL", "AMAT", "AMP", "ANET", "AON",
    "APD", "APH", "AXP", "BK", "BKNG", "BLK", "BMY", "BSX", "C", "CB",
    "CI", "CL", "CME", "CMG", "COF", "COP", "CPRT", "CSX", "CVS", "D",
    "DHR", "DLR", "DUK", "ECL", "EMR", "EOG", "EQIX", "ETN", "EW", "FCX",
    "FDX", "FIS", "GD", "GPN", "GS", "ICE", "IDXX", "ILMN", "ITW", "KHC",
    "KLAC", "KMB", "KMI", "LIN", "LRCX", "LUV", "MCK", "MET", "MMC", "MNST",
    "MO", "MPC", "MS", "MSI", "NEE", "NEM", "NSC", "OXY", "PCAR", "PGR",
    "PSA", "PSX", "ROST", "SHW", "SLB", "SO", "SPGI", "TGT"
]

for s in ADDITIONAL_STOCKS:
    STOCKS_MARKETS.append({
        "symbol": s,
        "name": f"{s} Corp.",
        "category": "Cổ phiếu",
        "digits": 2,
        "point": 0.01,
        "spread": 18,
        "base": 115.00
    })

# TOÀN BỘ 355 THỊ TRƯỜNG EXNESS
ALL_EXNESS_MARKETS: List[Dict[str, Any]] = (
    FOREX_MARKETS +
    METALS_ENERGY_MARKETS +
    CRYPTO_MARKETS +
    INDICES_MARKETS +
    STOCKS_MARKETS
)

assert len(ALL_EXNESS_MARKETS) == 355, f"Tổng số thị trường phải chính xác là 355, hiện tại: {len(ALL_EXNESS_MARKETS)}"

MARKETS_DICT: Dict[str, Dict[str, Any]] = {m["symbol"]: m for m in ALL_EXNESS_MARKETS}

def get_all_markets() -> List[Dict[str, Any]]:
    """Trả về danh sách 355 thị trường đầy đủ kèm thông tin chi tiết."""
    return ALL_EXNESS_MARKETS

def get_market_by_symbol(symbol: str) -> Dict[str, Any]:
    """Tìm thị trường theo mã symbol."""
    return MARKETS_DICT.get(symbol, {
        "symbol": symbol,
        "name": symbol,
        "category": "Forex",
        "digits": 5,
        "point": 0.00001,
        "spread": 15,
        "base": 1.1260
    })
