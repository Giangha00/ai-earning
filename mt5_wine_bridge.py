"""
Cầu nối Live MetaTrader 5 trên macOS thông qua Wine Python (MetaTrader 5.app).
Cho phép dự án Python trên macOS kết nối trực tiếp 2 chiều (Real-time) với
terminal64.exe của Exness đang chạy trong /Applications/MetaTrader 5.app:
- Đồng bộ số dư (Balance), Tài sản ròng (Equity), Margin, Leverage trực tiếp từ Exness.
- Tự động ánh xạ mã giao dịch Exness (ví dụ: EURUSD <-> EURUSDm, XAUUSD <-> XAUUSDm).
- Tự động bật Algo Trading (WM_COMMAND 32851) trên MT5 nếu đang tắt.
- Đặt lệnh thật, đóng lệnh thật và đồng bộ lịch sử Deal thật trên tài khoản Exness.
"""

import json
import logging
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

WINE_BIN = "/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine"
WINE_PREFIX = os.path.expanduser("~/Library/Application Support/net.metaquotes.wine.metatrader5")
WINE_PYTHON_EXE = os.path.join(WINE_PREFIX, "drive_c", "Python311", "python.exe")
TERMINAL_EXE_WIN = r"C:\Program Files\MetaTrader 5\terminal64.exe"
BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 18855

# Script chạy ngầm bên trong Wine Python 3.11 kết nối trực tiếp vào terminal64.exe
WINE_WORKER_CODE = r'''
import ctypes
import json
import socket
import sys
import threading
import time
import MetaTrader5 as mt5

TERMINAL_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
HOST = "127.0.0.1"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18855

_SYMBOL_MAP_CACHE = {}
_LOCK = threading.Lock()


def ensure_algo_trading_enabled():
    try:
        ti = mt5.terminal_info()
        if ti and not ti.trade_allowed:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW("MetaQuotes::MetaTrader::5.00", None)
            if hwnd:
                user32.PostMessageW(hwnd, 0x0111, 32851, 0)
                time.sleep(0.25)
    except Exception:
        pass


def resolve_broker_symbol(sym: str) -> str:
    if not sym:
        return sym
    if sym in _SYMBOL_MAP_CACHE:
        return _SYMBOL_MAP_CACHE[sym]
    # 1. Thử chính xác tên symbol
    info = mt5.symbol_info(sym)
    if info is not None and getattr(info, "trade_mode", 0) != 0:
        mt5.symbol_select(sym, True)
        _SYMBOL_MAP_CACHE[sym] = sym
        return sym
    # 2. Thử hậu tố 'm' của Exness Standard/Trial (VD: EURUSDm, XAUUSDm, BTCUSDm)
    for suffix in ("m", "c", ".a", "pro", ""):
        cand = f"{sym}{suffix}" if suffix else sym
        info_c = mt5.symbol_info(cand)
        if info_c is not None:
            mt5.symbol_select(cand, True)
            _SYMBOL_MAP_CACHE[sym] = cand
            return cand
    return sym


def clean_ui_symbol(broker_sym: str) -> str:
    if not broker_sym:
        return broker_sym
    if broker_sym.endswith("m") and len(broker_sym) > 3:
        return broker_sym[:-1]
    return broker_sym


def handle_cmd(req: dict) -> dict:
    cmd = req.get("cmd")
    with _LOCK:
        if cmd == "ping":
            return {"ok": True}

        if cmd == "initialize":
            login = req.get("login")
            password = req.get("password")
            server = req.get("server")
            ok = mt5.initialize(TERMINAL_PATH)
            if not ok and login and password and server:
                ok = mt5.initialize(TERMINAL_PATH, login=int(login), password=str(password), server=str(server))
            if ok:
                acc = mt5.account_info()
                if login and acc and int(acc.login) != int(login) and password and server:
                    mt5.login(login=int(login), password=str(password), server=str(server))
                ensure_algo_trading_enabled()
            err = mt5.last_error()
            return {"ok": bool(ok), "error": list(err) if err else [0, ""]}

        if cmd == "login":
            login = int(req.get("login"))
            password = str(req.get("password"))
            server = str(req.get("server"))
            ok = mt5.login(login=login, password=password, server=server)
            ensure_algo_trading_enabled()
            err = mt5.last_error()
            return {"ok": bool(ok), "error": list(err) if err else [0, ""]}

        if cmd == "shutdown":
            mt5.shutdown()
            return {"ok": True}

        if cmd == "last_error":
            err = mt5.last_error()
            return {"ok": True, "error": list(err) if err else [0, ""]}

        if cmd == "account_info":
            acc = mt5.account_info()
            if acc is None:
                mt5.initialize(TERMINAL_PATH)
                acc = mt5.account_info()
            if acc is None:
                return {"ok": False, "data": None}
            return {
                "ok": True,
                "data": {
                    "login": acc.login,
                    "name": acc.name,
                    "server": acc.server,
                    "currency": acc.currency,
                    "balance": float(acc.balance),
                    "equity": float(acc.equity),
                    "profit": float(acc.profit),
                    "margin": float(acc.margin),
                    "margin_free": float(acc.margin_free),
                    "margin_level": float(acc.margin_level),
                    "leverage": int(acc.leverage),
                },
            }

        if cmd == "symbol_select":
            sym = resolve_broker_symbol(req.get("symbol", "EURUSD"))
            ok = mt5.symbol_select(sym, bool(req.get("enable", True)))
            return {"ok": bool(ok)}

        if cmd == "symbol_info":
            ui_sym = req.get("symbol", "EURUSD")
            sym = resolve_broker_symbol(ui_sym)
            info = mt5.symbol_info(sym)
            if info is None:
                return {"ok": False, "data": None}
            return {
                "ok": True,
                "data": {
                    "name": ui_sym,
                    "broker_name": info.name,
                    "description": getattr(info, "description", ui_sym),
                    "visible": bool(info.visible),
                    "digits": int(info.digits),
                    "point": float(info.point),
                    "spread": int(info.spread),
                    "trade_tick_size": float(info.trade_tick_size),
                    "trade_tick_value": float(info.trade_tick_value),
                    "trade_contract_size": float(info.trade_contract_size),
                    "volume_min": float(info.volume_min),
                    "volume_max": float(info.volume_max),
                    "volume_step": float(info.volume_step),
                    "bid": float(info.bid),
                    "ask": float(info.ask),
                    "last": float(info.last or info.ask),
                    "filling_mode": int(getattr(info, "filling_mode", 1)),
                },
            }

        if cmd == "symbol_info_tick":
            ui_sym = req.get("symbol", "EURUSD")
            sym = resolve_broker_symbol(ui_sym)
            tick = mt5.symbol_info_tick(sym)
            if tick is None or (tick.bid == 0.0 and tick.ask == 0.0):
                mt5.symbol_select(sym, True)
                time.sleep(0.05)
                tick = mt5.symbol_info_tick(sym)
            if tick is None or (tick.bid == 0.0 and tick.ask == 0.0):
                return {"ok": False, "data": None}
            return {
                "ok": True,
                "data": {
                    "bid": float(tick.bid),
                    "ask": float(tick.ask),
                    "last": float(tick.last if tick.last > 0 else tick.ask),
                    "volume": float(tick.volume),
                    "time": int(tick.time),
                },
            }

        if cmd == "copy_rates_from_pos":
            ui_sym = req.get("symbol", "EURUSD")
            sym = resolve_broker_symbol(ui_sym)
            tf = int(req.get("timeframe", 5))
            start_pos = int(req.get("start_pos", 0))
            count = int(req.get("count", 500))
            mt5.symbol_select(sym, True)
            rates = mt5.copy_rates_from_pos(sym, tf, start_pos, count)
            if rates is None or len(rates) == 0:
                time.sleep(0.15)
                rates = mt5.copy_rates_from_pos(sym, tf, start_pos, count)
            if rates is None or len(rates) == 0:
                return {"ok": False, "data": []}
            rows = []
            for r in rates:
                rows.append({
                    "time": int(r["time"]),
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "tick_volume": int(r["tick_volume"]),
                    "spread": int(r["spread"]),
                    "real_volume": int(r["real_volume"]),
                })
            return {"ok": True, "data": rows}

        if cmd == "positions_get":
            ticket = req.get("ticket")
            ui_sym = req.get("symbol")
            if ticket is not None:
                pos_list = mt5.positions_get(ticket=int(ticket))
            elif ui_sym is not None:
                sym = resolve_broker_symbol(ui_sym)
                pos_list = mt5.positions_get(symbol=sym)
            else:
                pos_list = mt5.positions_get()
            if pos_list is None:
                return {"ok": True, "data": []}
            res = []
            for p in pos_list:
                res.append({
                    "ticket": int(p.ticket),
                    "symbol": clean_ui_symbol(p.symbol),
                    "type": int(p.type),
                    "volume": float(p.volume),
                    "price_open": float(p.price_open),
                    "price_current": float(p.price_current),
                    "sl": float(p.sl),
                    "tp": float(p.tp),
                    "swap": float(p.swap),
                    "commission": float(getattr(p, "commission", 0.0)),
                    "profit": float(p.profit),
                    "time": int(p.time),
                    "magic": int(p.magic),
                    "comment": str(p.comment),
                })
            return {"ok": True, "data": res}

        if cmd == "history_deals_get":
            position_id = req.get("position")
            from_ts = int(req.get("from_ts", 0))
            to_ts = int(req.get("to_ts", int(time.time()) + 86400))
            if position_id is not None:
                deals = mt5.history_deals_get(position=int(position_id))
            else:
                deals = mt5.history_deals_get(from_ts, to_ts)
            if deals is None:
                return {"ok": True, "data": []}
            res = []
            for d in deals:
                res.append({
                    "ticket": int(d.ticket),
                    "position_id": int(d.position_id),
                    "symbol": clean_ui_symbol(d.symbol),
                    "entry": int(d.entry),
                    "type": int(d.type),
                    "volume": float(d.volume),
                    "price": float(d.price),
                    "profit": float(d.profit),
                    "commission": float(d.commission),
                    "swap": float(d.swap),
                    "fee": float(getattr(d, "fee", 0.0)),
                    "time": int(d.time),
                    "comment": str(d.comment),
                })
            return {"ok": True, "data": res}

        if cmd == "order_send":
            ensure_algo_trading_enabled()
            order_req = dict(req.get("request", {}))
            ui_sym = order_req.get("symbol", "EURUSD")
            broker_sym = resolve_broker_symbol(ui_sym)
            order_req["symbol"] = broker_sym

            if order_req.get("action") == mt5.TRADE_ACTION_DEAL:
                info = mt5.symbol_info(broker_sym)
                if info is not None:
                    fm = getattr(info, "filling_mode", 1)
                    if fm & 1:
                        order_req["type_filling"] = mt5.ORDER_FILLING_FOK
                    elif fm & 2:
                        order_req["type_filling"] = mt5.ORDER_FILLING_IOC
                    else:
                        order_req["type_filling"] = mt5.ORDER_FILLING_RETURN

            res = mt5.order_send(order_req)
            if res is None:
                err = mt5.last_error()
                return {"ok": False, "data": None, "error": list(err) if err else [-1, "order_send returned None"]}
            return {
                "ok": True,
                "data": {
                    "retcode": int(res.retcode),
                    "order": int(res.order or res.deal or 0),
                    "deal": int(res.deal or 0),
                    "price": float(res.price),
                    "volume": float(res.volume),
                    "comment": str(res.comment),
                },
            }

        return {"ok": False, "error": [-1, f"Unknown cmd: {cmd}"]}


def serve():
    mt5.initialize(TERMINAL_PATH)
    ensure_algo_trading_enabled()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(16)
    while True:
        conn, _ = srv.accept()
        try:
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
            if data:
                req = json.loads(data.decode("utf-8"))
                resp = handle_cmd(req)
                conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
        except Exception as e:
            try:
                conn.sendall((json.dumps({"ok": False, "error": [-1, str(e)]}) + "\n").encode("utf-8"))
            except Exception:
                pass
        finally:
            conn.close()


if __name__ == "__main__":
    serve()
'''


class DictObj:
    def __init__(self, d: Dict[str, Any]):
        for k, v in d.items():
            setattr(self, k, v)


class WineMT5Bridge:
    """
    Giao diện tương thích 100% với thư viện MetaTrader5 chuẩn,
    nhưng giao tiếp trực tiếp với terminal64.exe trên macOS qua Wine Python Bridge
    kèm cơ chế fallback an toàn cho dữ liệu nến/tick khi thị trường đóng cửa.
    """
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388
    TIMEFRAME_D1 = 16408

    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_REQUOTE = 10004
    TRADE_RETCODE_REJECT = 10006
    TRADE_RETCODE_PRICE_OFF = 10008
    TRADE_RETCODE_INVALID_PRICE = 10015
    TRADE_RETCODE_INVALID_STOPS = 10016
    TRADE_RETCODE_INVALID_VOLUME = 10014
    TRADE_RETCODE_MARKET_CLOSED = 10018
    TRADE_RETCODE_NO_MONEY = 10019
    TRADE_RETCODE_TRADE_DISABLED = 10017

    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_SLTP = 6
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2

    _proc: Optional[subprocess.Popen] = None
    _lock = threading.Lock()
    _last_err = (1, "Success")

    def __init__(self, fallback_mock: Any):
        self._fallback = fallback_mock
        self._ensure_worker_running()

    def __getattr__(self, name: str) -> Any:
        if name == "set_balance":
            raise AttributeError("set_balance is only for MockMT5 simulation")
        return getattr(self._fallback, name)

    @classmethod
    def is_available(cls) -> bool:
        if os.environ.get("MT5_FORCE_MOCK") == "1":
            return False
        return os.path.exists(WINE_BIN) and os.path.exists(WINE_PYTHON_EXE)

    @classmethod
    def _is_port_open(cls) -> bool:
        try:
            with socket.create_connection((BRIDGE_HOST, BRIDGE_PORT), timeout=0.3) as s:
                s.sendall(b'{"cmd": "ping"}\n')
                data = s.recv(1024)
                return b'"ok": true' in data
        except Exception:
            return False

    @classmethod
    def _ensure_worker_running(cls) -> bool:
        if cls._is_port_open():
            return True
        with cls._lock:
            if cls._is_port_open():
                return True
            try:
                # Đảm bảo MetaTrader 5.app đã được bật trên macOS
                res = subprocess.run(["pgrep", "-f", "terminal64.exe"], capture_output=True)
                if res.returncode != 0:
                    subprocess.Popen(["open", "-g", "-a", "MetaTrader 5"])
                    time.sleep(3.0)

                worker_win_path = os.path.join(WINE_PREFIX, "drive_c", "Python311", "mt5_wine_worker.py")
                with open(worker_win_path, "w", encoding="utf-8") as f:
                    f.write(WINE_WORKER_CODE)

                env = os.environ.copy()
                env["WINEPREFIX"] = WINE_PREFIX
                env["WINEDEBUG"] = "-all"

                cls._proc = subprocess.Popen(
                    [WINE_BIN, r"C:\Python311\python.exe", r"C:\Python311\mt5_wine_worker.py", str(BRIDGE_PORT)],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                for _ in range(30):
                    if cls._is_port_open():
                        logging.info("🔗 Đã khởi chạy cầu nối Live Exness MT5 (Wine Python Bridge) trên cổng %d.", BRIDGE_PORT)
                        return True
                    time.sleep(0.2)
            except Exception as e:
                logging.warning(f"Không thể khởi chạy WineMT5Bridge: {e}")
        return False

    def _rpc(self, payload: Dict[str, Any], timeout: float = 5.0) -> Dict[str, Any]:
        if not self._ensure_worker_running():
            return {"ok": False, "error": [-1, "Bridge worker not running"]}
        try:
            with socket.create_connection((BRIDGE_HOST, BRIDGE_PORT), timeout=timeout) as s:
                s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
                buf = b""
                while not buf.endswith(b"\n"):
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
                if not buf:
                    return {"ok": False, "error": [-1, "Empty response"]}
                return json.loads(buf.decode("utf-8"))
        except Exception as e:
            return {"ok": False, "error": [-1, str(e)]}

    def initialize(self, path: str = None, login: int = None, password: str = None, server: str = None) -> bool:
        from config import config
        resp = self._rpc({
            "cmd": "initialize",
            "login": login or config.MT5_LOGIN,
            "password": password or config.MT5_PASSWORD,
            "server": server or config.MT5_SERVER,
        })
        if resp.get("ok"):
            self._last_err = (1, "Success")
            self.account_info()
            return True
        err = resp.get("error", [-1, "Init failed"])
        self._last_err = (err[0], err[1])
        return self._fallback.initialize(path=path, login=login, password=password, server=server)

    def login(self, login: int, password: str = None, server: str = None) -> bool:
        resp = self._rpc({"cmd": "login", "login": login, "password": password, "server": server})
        return bool(resp.get("ok", True))

    def shutdown(self) -> None:
        pass

    def last_error(self):
        return self._last_err

    def account_info(self):
        resp = self._rpc({"cmd": "account_info"})
        if resp.get("ok") and resp.get("data"):
            d = resp["data"]
            # Tự động đồng bộ số dư thực tế từ Exness vào SQLite & config để 2 bên luôn khớp 100%
            try:
                from config import config
                from db import get_setting, set_setting
                real_bal = round(float(d["balance"]), 2)
                config.MT5_BALANCE = real_bal
                saved = get_setting("account_balance", "")
                if saved != str(real_bal):
                    set_setting("account_balance", str(real_bal))
            except Exception:
                pass
            return DictObj(d)
        return self._fallback.account_info()

    def symbol_select(self, symbol: str, enable: bool = True) -> bool:
        resp = self._rpc({"cmd": "symbol_select", "symbol": symbol, "enable": enable})
        if resp.get("ok"):
            return True
        return self._fallback.symbol_select(symbol, enable)

    def symbol_info(self, symbol: str):
        resp = self._rpc({"cmd": "symbol_info", "symbol": symbol})
        if resp.get("ok") and resp.get("data"):
            return DictObj(resp["data"])
        return self._fallback.symbol_info(symbol)

    def set_symbol_price(self, symbol: str, price: float):
        if hasattr(self._fallback, "set_symbol_price"):
            self._fallback.set_symbol_price(symbol, price)

    def symbol_info_tick(self, symbol: str):
        resp = self._rpc({"cmd": "symbol_info_tick", "symbol": symbol})
        if resp.get("ok") and resp.get("data"):
            d = resp["data"]
            if d.get("bid", 0) > 0 and d.get("ask", 0) > 0:
                return DictObj(d)
        return self._fallback.symbol_info_tick(symbol)

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, count: int):
        import numpy as np
        resp = self._rpc({
            "cmd": "copy_rates_from_pos",
            "symbol": symbol,
            "timeframe": timeframe,
            "start_pos": start_pos,
            "count": count,
        }, timeout=8.0)
        if resp.get("ok") and resp.get("data") and len(resp["data"]) >= 10:
            rows = resp["data"]
            dtype = [
                ("time", "i8"),
                ("open", "f8"),
                ("high", "f8"),
                ("low", "f8"),
                ("close", "f8"),
                ("tick_volume", "i8"),
                ("spread", "i4"),
                ("real_volume", "i8"),
            ]
            data = [
                (
                    r["time"],
                    r["open"],
                    r["high"],
                    r["low"],
                    r["close"],
                    r["tick_volume"],
                    r["spread"],
                    r["real_volume"],
                )
                for r in rows
            ]
            return np.array(data, dtype=dtype)
        return self._fallback.copy_rates_from_pos(symbol, timeframe, start_pos, count)

    def positions_get(self, symbol: str = None, ticket: int = None):
        payload: Dict[str, Any] = {"cmd": "positions_get"}
        if ticket is not None:
            payload["ticket"] = ticket
        elif symbol is not None:
            payload["symbol"] = symbol
        resp = self._rpc(payload)
        if resp.get("ok") and resp.get("data") is not None:
            return tuple(DictObj(p) for p in resp["data"])
        return self._fallback.positions_get(symbol=symbol, ticket=ticket)

    def history_deals_get(self, date_from: Any = 0, date_to: Any = None, position: int = None):
        payload: Dict[str, Any] = {"cmd": "history_deals_get"}
        if position is not None:
            payload["position"] = int(position)
        else:
            payload["from_ts"] = int(date_from) if isinstance(date_from, (int, float)) else 0
            payload["to_ts"] = int(date_to) if isinstance(date_to, (int, float)) else int(time.time()) + 86400
        resp = self._rpc(payload)
        if resp.get("ok") and resp.get("data") is not None:
            return tuple(DictObj(d) for d in resp["data"])
        return ()

    def order_send(self, request: dict):
        resp = self._rpc({"cmd": "order_send", "request": request}, timeout=8.0)
        if resp.get("ok") and resp.get("data"):
            # Sau khi gửi lệnh hoặc đóng lệnh, cập nhật ngay số dư từ Exness
            self.account_info()
            return DictObj(resp["data"])
        return self._fallback.order_send(request)
