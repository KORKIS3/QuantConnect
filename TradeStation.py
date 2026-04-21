"""TradeStation.py

TradeStation REST/WebSocket data bridge for the YM E-mini Futures strategy.
Mirrors InteractiveBrokers.py — same algo engine, same chart, same CLI.

Authentication
--------------
TradeStation uses OAuth 2.0. Set these environment variables:
    TS_CLIENT_ID      — from developer.tradestation.com
    TS_CLIENT_SECRET  — from developer.tradestation.com
    TS_REFRESH_TOKEN  — obtained via first-time OAuth flow (see --auth below)

Quick start
-----------
    # First-time auth (opens browser, saves refresh token):
    python TradeStation.py --auth

    # Dry run (signals logged, no orders):
    python TradeStation.py --dry-run

    # Live paper trading:
    python TradeStation.py --sim

    # Live real trading:
    python TradeStation.py

    # Full day session:
    python TradeStation.py --duration 450
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Optional

import matplotlib
matplotlib.use("TkAgg")

import pandas as pd
import pytz
import requests
import websocket  # pip install websocket-client

from TradingAlgoFast import AlgoConfig, run_trading_algo_fast as run_trading_algo
from plotFigure import ChartPlotter
from Emailer import send_session_summary

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_EST = pytz.timezone("US/Eastern")

# TradeStation API endpoints
_TS_AUTH_URL  = "https://signin.tradestation.com/oauth/token"
_TS_API_BASE  = "https://api.tradestation.com/v3"
_TS_SIM_BASE  = "https://sim-api.tradestation.com/v3"   # simulated trading
_TS_WS_BASE   = "wss://api.tradestation.com/v3"
_TS_SIM_WS    = "wss://sim-api.tradestation.com/v3"

# YM front-month symbol format for TradeStation
_YM_SYMBOL    = "@YM"   # continuous contract — update to e.g. "YMM26" if needed

_IB_LIVE_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live")


# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------

class TSAuth:
    """Manages TradeStation OAuth tokens."""

    def __init__(self, client_id: str, client_secret: str, refresh_token: str, sim: bool = False):
        self.client_id     = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.sim           = sim
        self.access_token: Optional[str] = None
        self._token_expiry: float = 0.0
        self._lock = threading.Lock()

    def get_token(self) -> str:
        with self._lock:
            if time.time() < self._token_expiry - 60:
                return self.access_token
            self._refresh()
            return self.access_token

    def _refresh(self) -> None:
        resp = requests.post(_TS_AUTH_URL, data={
            "grant_type":    "refresh_token",
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self.access_token  = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 1200)
        log.info("[TSAuth] token refreshed, expires in %ds", data.get("expires_in", 1200))

    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.get_token()}"}


def first_time_auth(client_id: str, client_secret: str) -> str:
    """Interactive OAuth flow — opens browser, returns refresh token."""
    import urllib.parse, webbrowser, http.server, socketserver

    redirect_uri = "http://localhost:3000/callback"
    auth_url = (
        f"https://signin.tradestation.com/authorize"
        f"?response_type=code&client_id={client_id}"
        f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
        f"&audience=https://api.tradestation.com"
        f"&scope=openid+profile+offline_access+MarketData+ReadAccount+Trade"
    )

    code_holder = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if "code" in params:
                code_holder.append(params["code"][0])
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Auth complete - you can close this tab.")
        def log_message(self, *args): pass

    print(f"\nOpening browser for TradeStation auth...\n{auth_url}\n")
    webbrowser.open(auth_url)

    with socketserver.TCPServer(("", 3000), Handler) as httpd:
        httpd.handle_request()

    if not code_holder:
        raise RuntimeError("No auth code received")

    resp = requests.post(_TS_AUTH_URL, data={
        "grant_type":    "authorization_code",
        "client_id":     client_id,
        "client_secret": client_secret,
        "code":          code_holder[0],
        "redirect_uri":  redirect_uri,
    }, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    refresh_token = data["refresh_token"]
    print(f"\nRefresh token obtained. Add to your environment:\n  TS_REFRESH_TOKEN={refresh_token}\n")
    return refresh_token


# ---------------------------------------------------------------------------
# Main bridge
# ---------------------------------------------------------------------------

class TSDataBridge:
    """TradeStation data bridge — mirrors IBDataBridge interface."""

    def __init__(
        self,
        auth: TSAuth,
        config: Optional[AlgoConfig] = None,
        dry_run: bool = False,
        sim: bool = False,
        start_time: str = "09:30",
        end_time: str = "09:35",
        show_plot: bool = True,
        enable_chart: bool = True,
        tracking_root: Optional[str] = None,
        image_root: Optional[str] = None,
        session_duration_minutes: int = 105,
    ) -> None:
        self.auth    = auth
        self.config  = config or AlgoConfig(
            warmup_minutes=12,
            steep_angle_threshold=70.0,
            proximity_points=15.0,
            min_reversal_minutes=10,
            min_entry_angle=30.0,
        )
        self.dry_run  = dry_run
        self.sim      = sim
        self.start_time = start_time
        self.end_time   = end_time
        self.show_plot  = show_plot
        self.enable_chart = enable_chart
        self._session_duration_minutes = session_duration_minutes
        self.tracking_root = tracking_root or os.path.join(_IB_LIVE_ROOT, "tracking")
        self.image_root    = image_root    or os.path.join(_IB_LIVE_ROOT, "charts")

        self._api_base = _TS_SIM_BASE if sim else _TS_API_BASE
        self._ws_base  = _TS_SIM_WS   if sim else _TS_WS_BASE

        self._session_bars: list[dict] = []
        self._last_result: Optional[pd.DataFrame] = None
        self._current_date: Optional[str] = None
        self._last_minute: Optional[str] = None
        self._live_chart = None
        self._session_ended: bool = False
        self._session_start_dt = None
        self._last_hourly_save: Optional[int] = None
        self._account_id: Optional[str] = None
        self._ws: Optional[websocket.WebSocketApp] = None
        self._running: bool = False

    # -- account --------------------------------------------------------------

    def _get_account(self) -> str:
        resp = requests.get(f"{self._api_base}/brokerage/accounts",
                            headers=self.auth.headers(), timeout=10)
        resp.raise_for_status()
        accounts = resp.json().get("Accounts", [])
        if not accounts:
            raise RuntimeError("No TradeStation accounts found")
        acct = accounts[0]["AccountID"]
        log.info("[TS] Account: %s", acct)
        return acct

    # -- backfill -------------------------------------------------------------

    def _backfill_from_930(self) -> None:
        """Fetch 1-min bars from 9:30 ET today to now."""
        now   = datetime.now(_EST)
        today = now.strftime("%Y-%m-%d")
        session_start = _EST.localize(datetime.strptime(f"{today} 09:30:00", "%Y-%m-%d %H:%M:%S"))
        if now <= session_start:
            return

        start_str = session_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        url = (f"{self._api_base}/marketdata/barcharts/{_YM_SYMBOL}"
               f"?interval=1&unit=Minute&barsback=200&firstdate={start_str}")
        try:
            resp = requests.get(url, headers=self.auth.headers(), timeout=15)
            resp.raise_for_status()
            bars = resp.json().get("Bars", [])
        except Exception as exc:
            log.error("[Backfill] error: %s", exc)
            return

        count = 0
        for bar in bars:
            bar_time = pd.Timestamp(bar["TimeStamp"]).tz_convert(_EST)
            if bar_time < session_start:
                continue
            self._session_bars.append({
                "Open":   float(bar["Open"]),
                "High":   float(bar["High"]),
                "Low":    float(bar["Low"]),
                "Close":  float(bar["Close"]),
                "Volume": float(bar.get("TotalVolume", 0)),
                "time":   bar_time,
            })
            count += 1

        if count:
            self._current_date    = today
            self._session_start_dt = session_start
            self.start_time = "09:30"
            end_dt = session_start + pd.Timedelta(minutes=self._session_duration_minutes)
            self.end_time = end_dt.strftime("%H:%M")
            log.info("[Backfill] loaded %d bars (9:30 → %s)", count, now.strftime("%H:%M"))

    # -- order execution ------------------------------------------------------

    def _place_order(self, action: str, liquidate: bool = False) -> None:
        tag = "LIQUIDATE" if liquidate else action
        if self.dry_run:
            log.info("[ORDER dry_run] %-10s  symbol=%s", tag, _YM_SYMBOL)
            return
        if not self._account_id:
            log.error("[ORDER] no account ID — cannot place order")
            return
        payload = {
            "AccountID": self._account_id,
            "Symbol":    _YM_SYMBOL,
            "Quantity":  "1",
            "OrderType": "Market",
            "TradeAction": action,
            "TimeInForce": {"Duration": "DAY"},
            "Route": "Intelligent",
        }
        try:
            resp = requests.post(f"{self._api_base}/orderexecution/orders",
                                 headers={**self.auth.headers(), "Content-Type": "application/json"},
                                 json=payload, timeout=10)
            resp.raise_for_status()
            log.info("[ORDER] %s placed — %s", tag, resp.json())
        except Exception as exc:
            log.error("[ORDER] %s failed: %s", tag, exc)

    # -- chart / algo ---------------------------------------------------------

    def _resample_to_minutes(self) -> pd.DataFrame:
        if not self._session_bars:
            return pd.DataFrame()
        df = pd.DataFrame(self._session_bars).set_index("time")
        df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize(_EST)
        else:
            df.index = df.index.tz_convert(_EST)
        if self._session_start_dt is not None:
            df = df[df.index >= self._session_start_dt]
        return df.resample("1min").agg(
            Open=("Open","first"), High=("High","max"),
            Low=("Low","min"), Close=("Close","last"),
            Volume=("Volume","sum"),
        ).dropna(subset=["Open"])

    def _update_live_chart(self) -> None:
        if not self.enable_chart or not self.show_plot or not self._session_bars:
            return
        minute_df = self._resample_to_minutes()
        if minute_df.empty:
            return
        log.info("[LiveChart] running algo on %d bars ...", len(minute_df))
        try:
            algo_df = run_trading_algo(minute_df, self._current_date,
                                       self.start_time, self.end_time, self.config)
        except Exception as exc:
            log.error("[LiveChart] algo error: %s", exc)
            return
        self._last_result = algo_df
        if self._live_chart is None:
            from InteractiveBrokers import _LiveChartWindow
            self._live_chart = _LiveChartWindow(self._current_date, self.start_time, self.end_time)
        try:
            self._live_chart.update(algo_df)
        except Exception as exc:
            log.error("[LiveChart] update error: %s", exc)

    def _run_algo(self) -> None:
        minute_df = self._resample_to_minutes()
        if minute_df.empty:
            return
        try:
            result = run_trading_algo(minute_df, self._current_date,
                                      self.start_time, self.end_time, self.config)
        except Exception as exc:
            log.error("[Algo] error: %s", exc)
            return
        self._last_result = result
        last = result.iloc[-1]
        signal  = str(last.get("signal", ""))
        is_liq  = bool(last.get("is_liquidation", False))
        pl      = float(last.get("pl", 0.0))
        price   = float(minute_df["Close"].iloc[-1])
        if signal == "BUY":
            if is_liq:
                log.info("[Algo] LIQUIDATION  price=%.2f  pl=%.1f", price, pl)
                self._place_order("SELL", liquidate=True)
            else:
                log.info("[Algo] BUY          price=%.2f  pl=%.1f", price, pl)
                self._place_order("BUY")
        elif signal == "SELL":
            if is_liq:
                log.info("[Algo] LIQUIDATION  price=%.2f  pl=%.1f", price, pl)
                self._place_order("BUY", liquidate=True)
            else:
                log.info("[Algo] SELL         price=%.2f  pl=%.1f", price, pl)
                self._place_order("SELL")

    def _save_tracking_csv(self) -> None:
        if self._last_result is None or self._current_date is None:
            return
        os.makedirs(self.tracking_root, exist_ok=True)
        path = os.path.join(self.tracking_root, f"YM_tracking_{self._current_date}.csv")
        self._last_result.to_csv(path)
        log.info("[TrackingCSV] saved %s  rows=%d", path, len(self._last_result))

    # -- session end ----------------------------------------------------------

    def _on_session_end(self) -> None:
        if not self._session_bars or not self._current_date:
            return
        log.info("[Session] %s ended — flattening and saving.", self._current_date)

        # Flatten open position
        try:
            pos = "flat"
            if self._last_result is not None and not self._last_result.empty:
                pos = str(self._last_result["position"].iloc[-1])
            if pos == "long":
                log.info("[Session] flattening LONG")
                self._place_order("SELL", liquidate=True)
            elif pos == "short":
                log.info("[Session] flattening SHORT")
                self._place_order("BUY", liquidate=True)
        except Exception as exc:
            log.error("[Session] flatten error: %s", exc)

        # Save chart image
        if self._live_chart is not None and self._live_chart._plotter is not None:
            try:
                os.makedirs(self.image_root, exist_ok=True)
                img_path = os.path.join(self.image_root,
                    f"YM_{self._current_date}_{self.start_time.replace(':','')}_ts.jpg")
                self._live_chart._plotter.fig.savefig(img_path, dpi=150, bbox_inches="tight")
                log.info("[Session] chart saved: %s", img_path)
            except Exception as exc:
                log.error("[Session] image save error: %s", exc)
            self._live_chart.close()
            self._live_chart = None

        self._save_tracking_csv()
        self._running = False

    # -- WebSocket bar stream -------------------------------------------------

    def _on_ws_message(self, ws, message: str) -> None:
        try:
            data = json.loads(message)
        except Exception:
            return

        # TradeStation streams bar updates as {"Close": ..., "TimeStamp": ...}
        if "Close" not in data or "TimeStamp" not in data:
            return

        bar_time = pd.Timestamp(data["TimeStamp"]).tz_convert(_EST)
        bar_date   = bar_time.strftime("%Y-%m-%d")
        bar_minute = bar_time.strftime("%Y-%m-%d %H:%M")

        if self._current_date is None:
            self._current_date = bar_date
            now = datetime.now(_EST)
            self._session_start_dt = _EST.localize(
                datetime.strptime(f"{bar_date} {self.start_time}:00", "%Y-%m-%d %H:%M:%S"))
            end_dt = self._session_start_dt + pd.Timedelta(minutes=self._session_duration_minutes)
            self.end_time = end_dt.strftime("%H:%M")
            log.info("[TS] session window: %s – %s", self.start_time, self.end_time)

        self._session_bars.append({
            "Open":   float(data.get("Open", data["Close"])),
            "High":   float(data.get("High", data["Close"])),
            "Low":    float(data.get("Low",  data["Close"])),
            "Close":  float(data["Close"]),
            "Volume": float(data.get("TotalVolume", 0)),
            "time":   bar_time,
        })

        # Fire on new minute boundary
        if self._last_minute is not None and bar_minute != self._last_minute:
            log.info("[OnBar] %s → %s  buffered=%d",
                     self._last_minute, bar_minute, len(self._session_bars))
            try: self._update_live_chart()
            except Exception as exc: log.error("[OnBar] chart error: %s", exc)
            try: self._run_algo()
            except Exception as exc: log.error("[OnBar] algo error: %s", exc)
            try: self._save_tracking_csv()
            except Exception as exc: log.error("[OnBar] csv error: %s", exc)

            # Hourly snapshot
            if (bar_time.minute == 0 and self._last_hourly_save != bar_time.hour and
                    self._live_chart is not None and self._live_chart._plotter is not None):
                try:
                    snap = os.path.join(self.image_root,
                        f"YM_{bar_date}_{bar_time.hour:02d}00_snapshot_ts.jpg")
                    self._live_chart._plotter.fig.savefig(snap, dpi=150, bbox_inches="tight")
                    self._last_hourly_save = bar_time.hour
                    log.info("[Snapshot] %s", snap)
                except Exception as exc:
                    log.error("[Snapshot] error: %s", exc)

            # Auto-end
            try:
                end_dt = _EST.localize(datetime.strptime(
                    f"{bar_date} {self.end_time}:00", "%Y-%m-%d %H:%M:%S"))
                if bar_time >= end_dt and not self._session_ended:
                    self._session_ended = True
                    log.info("[OnBar] end_time %s reached", self.end_time)
                    self._on_session_end()
                    if self._ws:
                        self._ws.close()
            except Exception as exc:
                log.error("[OnBar] auto-end error: %s", exc)

        self._last_minute = bar_minute

    def _on_ws_error(self, ws, error):
        log.error("[WS] error: %s", error)

    def _on_ws_close(self, ws, code, msg):
        log.info("[WS] closed: %s %s", code, msg)

    def _on_ws_open(self, ws):
        log.info("[WS] connected — subscribing to %s 1-min bars", _YM_SYMBOL)
        ws.send(json.dumps({
            "RequestID": "1",
            "Command": "Subscribe",
            "Symbol": _YM_SYMBOL,
            "Interval": "1",
            "Unit": "Minute",
        }))

    # -- main entry point -----------------------------------------------------

    def start(self) -> None:
        self._account_id = self._get_account()

        # Backfill from 9:30 if mid-session
        now = datetime.now(_EST)
        if now.hour >= 9 and now.minute >= 30:
            self._backfill_from_930()
            if self._session_bars:
                self._update_live_chart()

        ws_url = f"{self._ws_base}/marketdata/stream/barcharts/{_YM_SYMBOL}?interval=1&unit=Minute"
        headers = [f"Authorization: Bearer {self.auth.get_token()}"]

        self._ws = websocket.WebSocketApp(
            ws_url,
            header=headers,
            on_open=self._on_ws_open,
            on_message=self._on_ws_message,
            on_error=self._on_ws_error,
            on_close=self._on_ws_close,
        )

        self._running = True
        log.info("[TS] starting WebSocket stream for %s", _YM_SYMBOL)
        log.info("Press Ctrl+C to stop.")

        try:
            self._ws.run_forever(ping_interval=30, ping_timeout=10)
        except KeyboardInterrupt:
            log.info("Interrupted.")
        except Exception as exc:
            log.error("Unexpected error: %s", exc)
        finally:
            log.info("Flattening any open position before exit ...")
            self._on_session_end()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TradeStation data bridge for YM strategy.")
    p.add_argument("--auth",      action="store_true", help="Run first-time OAuth flow.")
    p.add_argument("--sim",       action="store_true", help="Use simulated trading environment.")
    p.add_argument("--dry-run",   action="store_true", dest="dry_run")
    p.add_argument("--duration",  type=int, default=105, dest="duration")
    p.add_argument("--no-plot",   action="store_false", dest="show_plot")
    p.add_argument("--tracking-root", default=os.path.join(_IB_LIVE_ROOT, "tracking"), dest="tracking_root")
    p.add_argument("--image-root",    default=os.path.join(_IB_LIVE_ROOT, "charts"),   dest="image_root")
    p.set_defaults(show_plot=True)
    return p


if __name__ == "__main__":
    args = _build_parser().parse_args()

    client_id     = os.environ.get("TS_CLIENT_ID", "")
    client_secret = os.environ.get("TS_CLIENT_SECRET", "")
    refresh_token = os.environ.get("TS_REFRESH_TOKEN", "")

    if args.auth:
        if not client_id or not client_secret:
            print("Set TS_CLIENT_ID and TS_CLIENT_SECRET environment variables first.")
        else:
            first_time_auth(client_id, client_secret)
    else:
        if not all([client_id, client_secret, refresh_token]):
            print("Set TS_CLIENT_ID, TS_CLIENT_SECRET, TS_REFRESH_TOKEN environment variables.")
            print("Run with --auth first to get your refresh token.")
        else:
            auth = TSAuth(client_id, client_secret, refresh_token, sim=args.sim)
            bridge = TSDataBridge(
                auth=auth,
                dry_run=args.dry_run,
                sim=args.sim,
                show_plot=args.show_plot,
                tracking_root=args.tracking_root,
                image_root=args.image_root,
                session_duration_minutes=args.duration,
            )
            bridge.start()
