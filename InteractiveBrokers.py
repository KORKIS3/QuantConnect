"""InteractiveBrokers.py

IB data bridge for the YM E-mini Futures trendline strategy.

Connects to TWS or IB Gateway via ib_insync, subscribes to the front-month
YM contract, and hands each bar to TradingAlgo.run_trading_algo() -- the
same engine used by ReOrgMain and RunAllDays.

Connection presets
------------------
TWS paper   : host=127.0.0.1  port=7497
TWS live    : host=127.0.0.1  port=7496
Gateway paper: host=127.0.0.1  port=4002
Gateway live : host=127.0.0.1  port=4001

Quick start
-----------
    # Run the connection test (no orders placed):
    python InteractiveBrokers.py --test

    # Live feed with signals logged but no orders:
    python InteractiveBrokers.py --dry-run

    # Live feed with order execution (paper account):
    python InteractiveBrokers.py
"""

from __future__ import annotations

# Fix for Python 3.14 asyncio event loop issue with ib_insync
import asyncio
import sys
if sys.version_info >= (3, 10):
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

import argparse
import logging
import os
import time
from datetime import datetime
from typing import Optional

import sys as _sys
import matplotlib
# Use non-interactive backend when --no-plot is passed (avoids needing a display)
if "--no-plot" in _sys.argv:
    matplotlib.use("Agg")
else:
    matplotlib.use('TkAgg')  # interactive windows on Windows

import pandas as pd
import pytz
from ib_insync import IB, BarData, Contract, Future, MarketOrder, LimitOrder, StopOrder, util
from openpyxl import Workbook

from TradingAlgoFast import AlgoConfig, run_trading_algo_fast as run_trading_algo
from belief_engine_pinball import PinballEngine, PinballConfig
from ReOrgMain import run_live_session
from plotFigure import ChartPlotter
from Emailer import send_session_summary, send_trade_alert, send_connection_failure_alert
# from Notifier import send_signal_alert

# ---------------------------------------------------------------------------
# Logging — console + file
# ---------------------------------------------------------------------------
import datetime as _dt

_LOG_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

# For single-account mode, use the original log file name
_LOG_FILE = os.path.join(_LOG_DIR, f"fred_ib_{_dt.datetime.now().strftime('%Y%m%d_%H%M')}.log")

# Configure basic logging (will be enhanced per-account in multi-account mode)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),                          # console
        logging.FileHandler(_LOG_FILE, encoding="utf-8"), # file
    ]
)
log = logging.getLogger(__name__)

# Also capture ib_insync internal logs to the same file
logging.getLogger("ib_insync").setLevel(logging.DEBUG)
logging.getLogger("ib_insync.wrapper").setLevel(logging.DEBUG)

_EST = pytz.timezone("US/Eastern")
_IB_LIVE_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live")


# ---------------------------------------------------------------------------
# Contract helper
# ---------------------------------------------------------------------------

def resolve_ym_front_month(ib: IB) -> Contract:
    """Query IB for all active MYM (Micro E-mini Dow) contracts and return the front month.

    Uses ``reqContractDetails`` so IB returns every listed expiry, then
    filters to contracts whose last trade date is today or later and sorts
    ascending -- the first entry is the front month.
    """
    from datetime import date

    base = Future(symbol="MYM", exchange="CBOT", currency="USD")
    details = ib.reqContractDetails(base)
    if not details:
        raise RuntimeError("No MYM contract details returned by IB.")

    today = date.today().strftime("%Y%m%d")
    active = [
        d.contract
        for d in details
        if d.contract.lastTradeDateOrContractMonth >= today
    ]
    if not active:
        raise RuntimeError("No active (non-expired) MYM contracts found.")

    active.sort(key=lambda c: c.lastTradeDateOrContractMonth)
    return active[0]


# ---------------------------------------------------------------------------
# Live chart window
# ---------------------------------------------------------------------------

class _LiveChartWindow:
    """Non-blocking matplotlib window that redraws on each completed minute bar.

    Uses ``plt.ion()`` so the figure stays open while ib_insync's event loop
    continues to run.  Call ``update()`` whenever a new per-minute algo
    DataFrame is ready; call ``close()`` when the session ends.
    """

    def __init__(self, target_date: str, start_time: str, end_time: str) -> None:
        self.target_date = target_date
        self.start_time = start_time
        self.end_time = end_time
        self._plotter: Optional[ChartPlotter] = None

    def update(self, algo_df: pd.DataFrame, headless: bool = False) -> None:
        """Redraw the chart at the latest frame with the current minute data."""
        import matplotlib.pyplot as _plt

        # Fixed 75-minute rolling window so visual angles stay consistent.
        _x_end   = algo_df.index[-1] + pd.Timedelta(minutes=1)
        _x_start = _x_end - pd.Timedelta(minutes=75)

        is_first = self._plotter is None
        if is_first:
            if not headless:
                _plt.ion()
            self._plotter = ChartPlotter(
                algo_df,
                self.target_date,
                self.start_time,
                self.end_time,
                output_dir="",
                batch_mode=headless,
            )
            self._plotter.create_figure()
            self._plotter.ax.set_xlim(_x_start, _x_end)
            if self._plotter.ax_top is not None:
                self._plotter.ax_top.set_xlim(_x_start, _x_end)
        else:
            self._plotter.data = algo_df
            self._plotter.ax.set_xlim(_x_start, _x_end)
            if self._plotter.ax_top is not None:
                self._plotter.ax_top.set_xlim(_x_start, _x_end)

        frame = len(algo_df) - 1
        self._plotter.update_plot(frame)

        if headless:
            return

        if is_first:
            _plt.show(block=False)
            self._plotter.fig.canvas.draw_idle()
            try:
                win = self._plotter.fig.canvas.manager.window
                win.lift()
                win.attributes("-topmost", True)
                win.after(500, lambda: win.attributes("-topmost", False))
                win.update_idletasks()
                win.update()
            except Exception:
                pass
        else:
            self._plotter.fig.canvas.draw_idle()
            try:
                win = self._plotter.fig.canvas.manager.window
                win.update_idletasks()
                win.update()
            except Exception:
                pass

    def pump(self) -> None:
        """Pump the Tkinter event queue to keep the window responsive."""
        if self._plotter is not None and self._plotter.fig is not None:
            try:
                # draw_idle() schedules a redraw; update_idletasks() forces
                # Tkinter to process it immediately on the main thread.
                self._plotter.fig.canvas.draw_idle()
                win = self._plotter.fig.canvas.manager.window
                win.update_idletasks()
                win.update()
            except Exception:
                pass

    def close(self) -> None:
        """Close the live chart window."""
        import matplotlib.pyplot as _plt
        if self._plotter is not None and self._plotter.fig is not None:
            _plt.close(self._plotter.fig)
        self._plotter = None


# ---------------------------------------------------------------------------
# IB data bridge
# ---------------------------------------------------------------------------

class IBDataBridge:
    """Subscribes to YM real-time bars and delegates all signals to TradingAlgo.

    At the end of each trading session (day rollover or manual stop) the full
    bar history is handed to ``ReOrgMain.run_live_session()`` which runs the
    same chart / CSV pipeline used by historical back-tests.

    Parameters
    ----------
    host, port, client_id:
        IB TWS / Gateway connection parameters.
    config:
        ``AlgoConfig`` passed through to ``run_trading_algo()``.
    dry_run:
        Log signals without placing any orders.
    start_time, end_time:
        Session window forwarded to ``run_live_session()`` (e.g. ``'09:30'``,
        ``'10:00'``).
    show_plot:
        Display the interactive chart at end of session.
    tracking_root:
        Directory for per-day tracking CSVs (``None`` = skip).
    image_root:
        Directory for per-day chart images (``None`` = skip).
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 1,
        config: Optional[AlgoConfig] = None,
        dry_run: bool = False,
        start_time: str = "09:30",
        end_time: str = "09:35",
        show_plot: bool = True,
        enable_chart: bool = True,
        tracking_root: Optional[str] = None,
        image_root: Optional[str] = None,
        session_duration_minutes: int = 105,
        account_id: Optional[str] = None,  # NEW: for multi-account logging
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.account_id = account_id  # NEW: store account ID for file naming
        self.config = config or AlgoConfig(
            warmup_minutes=7,
            steep_angle_threshold=90.0,
            proximity_points=4.0,
            min_reversal_minutes=0,
            min_entry_angle=0.0,
            partial_tp_pts=50.0,
            spike_profit_pts=100.0,
            spike_profit_bars=9,
            wm_shield_distance=0.0,
            swing_anchor_threshold=10.0,
            num_contracts=2,
        )
        self.dry_run = dry_run
        self.start_time = start_time
        self.end_time = end_time
        self.show_plot = show_plot
        self.enable_chart = enable_chart  # set False to run headless (no matplotlib window)
        self._session_duration_minutes = session_duration_minutes
        self.tracking_root = tracking_root or os.path.join(_IB_LIVE_ROOT, "tracking")
        self.image_root    = image_root    or os.path.join(_IB_LIVE_ROOT, "charts")

        self._ib = IB()
        self._session_bars: list[dict] = []
        self._last_result: Optional[pd.DataFrame] = None
        self._contract: Optional[Contract] = None        # YM — data feed
        self._order_contract: Optional[Contract] = None  # MYM — order execution
        self._current_date: Optional[str] = None
        self._last_minute: Optional[str] = None
        self._live_chart: Optional[_LiveChartWindow] = None
        self._raw_wb: Optional[Workbook] = None
        self._raw_ws = None
        self._raw_path: Optional[str] = None
        self._session_ended: bool = False
        self._window_set: bool = False
        self._session_start_dt = None
        self._last_hourly_save: Optional[int] = None  # tracks last hour we saved a snapshot
        self._last_signal_ts: Optional[pd.Timestamp] = None   # last signal we acted on
        self._last_partial_tp_ts: Optional[pd.Timestamp] = None  # last partial TP we acted on
        self._ib_position: int = 0  # actual IB position: +2=long, -2=short, 0=flat
        self._pending_order: bool = False  # True while an order is placed but not yet confirmed
        self._pending_order_time: Optional[float] = None  # timestamp when pending order was set
        self._pending_target: int = 0  # target position the pending order is working toward
        self._last_position_check: Optional[float] = None  # last time we validated position size
        self._pinball: PinballEngine = PinballEngine(PinballConfig())  # Pinball overlay
        self._pinball_last_action: str = "HOLD"  # last Pinball decision
        
        # TP/SL bracket order management
        self._tp_sl_enabled: bool = True
        self._tp_points: float = 60.0   # total TP in points (30 per contract × 2)
        self._sl_points: float = 50.0   # total SL in points (25 per contract × 2)
        self._cushion_points: float = 40.0  # enter 40 pts better than signal (buy dip / sell rip)
        self._bracket_tp_order = None   # active TP limit order
        self._bracket_sl_order = None   # active SL stop order
        self._entry_price: float = 0.0  # price we entered at
        
        # Live order event tracking — records actual IB outcomes for CSV/chart
        # Each entry: {time, signal, signal_price, limit_price, status, fill_price, fill_time}
        self._order_events: list[dict] = []
        
        # NEW: Create account-specific logger if account_id is provided
        if self.account_id:
            self._setup_account_logger()

    def _setup_account_logger(self) -> None:
        """Create a separate log file for this account."""
        import datetime as _dt
        log_file = os.path.join(_LOG_DIR, f"fred_ib_{self.account_id}_{_dt.datetime.now().strftime('%Y%m%d_%H%M')}.log")
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        # Add handler to root logger so all messages go to this account's log
        logging.getLogger().addHandler(handler)
        log.info("[Account %s] Logging to %s", self.account_id, log_file)

    def _seed_events_from_logs(self) -> None:
        """Parse today's IB logs to reconstruct trade history on restart.
        
        Scans all log files for today's date matching this account, extracts
        execution fills (BOT/SLD), and builds _order_events so the chart
        reflects the full day's actual IB activity.
        """
        import re
        from datetime import datetime as _dt
        
        today_str = _dt.now().strftime("%Y%m%d")
        account_pattern = f"fred_ib_{self.account_id}_{today_str}" if self.account_id else f"fred_ib_{today_str}"
        
        # Find all today's log files for this account
        log_files = sorted([
            os.path.join(_LOG_DIR, f) for f in os.listdir(_LOG_DIR)
            if f.startswith(account_pattern) and f.endswith(".log")
        ])
        
        if not log_files:
            log.info("[LogParser] No previous logs found for today")
            return
        
        # Parse executions: side='BOT'|'SLD', price=XXXXX.X, cumQty=N.0
        # We only care about the FINAL cumQty for each orderId (avoid double-counting partial fills)
        exec_pattern = re.compile(
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*execDetails Execution\("
            r".*side='(BOT|SLD)'.*price=([\d.]+).*orderId=(\d+).*cumQty=([\d.]+)"
        )
        
        # Collect unique fills: key by orderId, keep max cumQty
        fills_by_order = {}  # orderId -> {time, side, price, qty}
        
        for log_file in log_files:
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        m = exec_pattern.search(line)
                        if m:
                            time_str, side, price, order_id, cum_qty = m.groups()
                            cum_qty_f = float(cum_qty)
                            # Keep the highest cumQty per order (final fill state)
                            if order_id not in fills_by_order or cum_qty_f > fills_by_order[order_id]["qty"]:
                                fills_by_order[order_id] = {
                                    "time_str": time_str,
                                    "side": side,
                                    "price": float(price),
                                    "qty": cum_qty_f,
                                }
            except Exception as exc:
                log.warning("[LogParser] Error reading %s: %s", log_file, exc)
        
        if not fills_by_order:
            log.info("[LogParser] No executions found in today's logs")
            return
        
        # Sort by time and build order events
        sorted_fills = sorted(fills_by_order.values(), key=lambda x: x["time_str"])
        
        # Clear any existing seeded events (avoid duplicates)
        self._order_events = []
        
        est = pytz.timezone("US/Eastern")
        pos = 0  # track position through fills
        entry_price = 0.0
        
        for fill in sorted_fills:
            fill_time = pd.Timestamp(fill["time_str"], tz=est)
            signal = "BUY" if fill["side"] == "BOT" else "SELL"
            qty = int(fill["qty"])
            
            is_liquidation = False
            if signal == "BUY" and pos <= 0:
                # Going long or closing short
                if pos < 0:
                    is_liquidation = (pos + qty) == 0  # exact close
                pos = pos + qty
                if not is_liquidation:
                    entry_price = fill["price"]
            elif signal == "SELL" and pos >= 0:
                # Going short or closing long
                if pos > 0:
                    is_liquidation = (pos - qty) == 0  # exact close
                pos = pos - qty
                if not is_liquidation:
                    entry_price = fill["price"]
            else:
                # Adding to position
                pos = pos + qty if signal == "BUY" else pos - qty
                entry_price = fill["price"]
            
            self._order_events.append({
                "time": fill_time,
                "signal": signal,
                "signal_price": fill["price"],
                "limit_price": fill["price"],
                "status": "filled",
                "fill_price": fill["price"],
                "fill_time": fill_time,
                "is_liquidation": is_liquidation,
                "is_partial_tp": False,
            })
        
        if entry_price > 0:
            self._entry_price = entry_price
        
        log.info("[LogParser] Reconstructed %d fills from today's logs. Current pos=%d, entry=%.0f",
                 len(self._order_events), pos, entry_price)

    # -- connection -----------------------------------------------------------

    def _backfill_from_session_start(self) -> None:
        """Fetch 1-min bars from session start (e.g. 09:30 or 18:00) up to now.

        Works for both day and overnight sessions — uses self._session_start_dt
        which is already set by _apply_dynamic_window.
        """
        if self._session_start_dt is None:
            log.warning("[Backfill] session_start_dt not set — skipping")
            return

        now = datetime.now(_EST)
        session_start = self._session_start_dt

        if now <= session_start:
            log.info("[Backfill] session hasn't started yet — no backfill needed")
            return

        elapsed_secs = int((now - session_start).total_seconds()) + 60
        end_utc = now.astimezone(pytz.utc).strftime("%Y%m%d-%H:%M:%S")

        log.info("[Backfill] fetching %d seconds of 1-min bars from %s ...",
                 elapsed_secs, self.start_time)
        try:
            hist_bars = self._ib.reqHistoricalData(
                self._contract,
                endDateTime=end_utc,
                durationStr=f"{elapsed_secs} S",
                barSizeSetting="1 min",
                whatToShow="TRADES",
                useRTH=False,
                formatDate=1,
            )
        except Exception as exc:
            log.error("[Backfill] reqHistoricalData error: %s", exc)
            return

        if not hist_bars:
            log.warning("[Backfill] no historical bars returned")
            return

        count = 0
        for bar in hist_bars:
            bar_time = (pd.Timestamp(bar.date).tz_localize("UTC").tz_convert(_EST)
                        if pd.Timestamp(bar.date).tzinfo is None
                        else pd.Timestamp(bar.date).tz_convert(_EST))
            if bar_time < session_start:
                continue
            # Expand each 1-min bar into twelve 5-second entries so it integrates
            # cleanly with the 5-second real-time bar accumulator
            for _ in range(12):
                self._session_bars.append({
                    "Open":   bar.open,
                    "High":   bar.high,
                    "Low":    bar.low,
                    "Close":  bar.close,
                    "Volume": bar.volume / 12,
                    "time":   bar_time,
                })
            count += 1

        today = now.strftime("%Y-%m-%d")
        if count:
            self._current_date = today
            log.info("[Backfill] loaded %d bars (%s → %s)",
                     count, self.start_time, now.strftime("%H:%M"))
        else:
            log.warning("[Backfill] 0 bars loaded for window %s → %s",
                        self.start_time, now.strftime("%H:%M"))

    def connect(self) -> None:
        """Connect to TWS / IB Gateway and qualify the YM contract."""
        try:
            self._ib.connect(self.host, self.port, clientId=self.client_id)
            log.info("Connected to IB at %s:%s (clientId=%s)", self.host, self.port, self.client_id)
        except Exception as exc:
            error_msg = f"Failed to connect to IB Gateway at {self.host}:{self.port} — {exc}"
            log.error(error_msg)
            send_connection_failure_alert(error_msg)
            raise RuntimeError(error_msg) from exc

        self._contract = resolve_ym_front_month(self._ib)
        log.info("Front-month: %s  expiry=%s", self._contract.localSymbol,
                 self._contract.lastTradeDateOrContractMonth)

        # Sync _ib_position from actual IB account on connect
        try:
            positions = self._ib.positions()
            for p in positions:
                if p.contract.symbol in ("YM", "MYM"):
                    self._ib_position = int(p.position)
                    log.info("[Connect] Synced _ib_position=%d from IB account", self._ib_position)
                    
                    # Only flatten if BEFORE session start (9:30). Mid-session restarts keep position.
                    now_est = pd.Timestamp.now(tz=pytz.timezone("US/Eastern"))
                    session_start = now_est.replace(hour=9, minute=30, second=0, microsecond=0)
                    
                    if self._ib_position != 0 and now_est < session_start:
                        log.warning("=" * 80)
                        log.warning("WARNING: Account is NOT FLAT at session start!")
                        log.warning("Current position: %d contracts", self._ib_position)
                        log.warning("Flattening position now...")
                        log.warning("=" * 80)
                        
                        # Flatten the position
                        if self._ib_position > 0:
                            from ib_insync import MarketOrder
                            order = MarketOrder("SELL", abs(self._ib_position))
                            order.tif = "DAY"
                            trade = self._ib.placeOrder(self._contract, order)
                            log.info("[Connect] Placed SELL %d to flatten long position", abs(self._ib_position))
                            self._ib.sleep(3)
                        elif self._ib_position < 0:
                            from ib_insync import MarketOrder
                            order = MarketOrder("BUY", abs(self._ib_position))
                            order.tif = "DAY"
                            trade = self._ib.placeOrder(self._contract, order)
                            log.info("[Connect] Placed BUY %d to flatten short position", abs(self._ib_position))
                            self._ib.sleep(3)
                        
                        # Re-check position after flatten
                        positions = self._ib.positions()
                        for p in positions:
                            if p.contract.symbol in ("YM", "MYM"):
                                self._ib_position = int(p.position)
                                break
                        
                        if self._ib_position == 0:
                            log.info("[Connect] Position flattened successfully — ready to trade")
                        else:
                            log.error("[Connect] Position still not flat: %d contracts", self._ib_position)
                    elif self._ib_position != 0:
                        log.info("[Connect] Mid-session restart — keeping position %d (after 9:30)",
                                 self._ib_position)
                    else:
                        log.info("[Connect] Account is FLAT — ready to trade")
                    break
        except Exception as exc:
            log.warning("[Connect] Could not sync position from IB: %s", exc)

        # Subscribe to portfolio updates so _ib_position stays accurate from real fills
        self._ib.updatePortfolioEvent += self._on_portfolio_update

        # Seed _order_events from IB's current state (handles mid-session restarts)
        # If IB has a position, create a synthetic "filled" event so chart/P&L track correctly
        if self._ib_position != 0:
            try:
                portfolio = self._ib.portfolio()
                for item in portfolio:
                    if item.contract.symbol in ("YM", "MYM") and int(item.position) != 0:
                        pos_size = int(item.position)
                        # averageCost for MYM = price * multiplier(0.5)
                        entry_p = float(item.averageCost) / 0.5 if item.averageCost else 0.0
                        if entry_p > 100000 or entry_p < 10000:
                            entry_p = float(item.marketPrice) if item.marketPrice else 0.0
                        signal = "BUY" if pos_size > 0 else "SELL"
                        self._order_events.append({
                            "time": pd.Timestamp.now(tz=pytz.timezone("US/Eastern")).floor("min"),
                            "signal": signal,
                            "signal_price": entry_p,
                            "limit_price": entry_p,
                            "status": "filled",
                            "fill_price": entry_p,
                            "fill_time": pd.Timestamp.now(tz=pytz.timezone("US/Eastern")),
                            "is_liquidation": False,
                            "is_partial_tp": False,
                        })
                        self._entry_price = entry_p
                        log.info("[Connect] Seeded _order_events: %s %d @ %.0f (from IB portfolio)",
                                 signal, abs(pos_size), entry_p)
                        break
            except Exception as exc:
                log.warning("[Connect] Could not seed order events from portfolio: %s", exc)

        # Parse today's IB logs to reconstruct full trade history (handles restarts)
        self._seed_events_from_logs()

    def _on_portfolio_update(self, item) -> None:
        """Called by IB on every fill - keeps _ib_position in sync with real fills."""
        if item.contract.symbol in ("YM", "MYM"):
            new_pos = int(item.position)
            if new_pos != self._ib_position:
                old_pos = self._ib_position
                log.info("[PositionSync] IB fill confirmed: _ib_position %d -> %d",
                         self._ib_position, new_pos)
                self._ib_position = new_pos
                self._pending_order = False  # fill confirmed — safe to place next order
                self._pending_order_time = None
                log.info("[PositionSync] _pending_order cleared")
                
                # Update order event tracking — mark last pending as filled
                fill_price = float(item.averageCost) / 0.5 if item.averageCost else 0.0
                # averageCost for MYM is price * multiplier(0.5), so divide back
                # But if that gives nonsense, use marketPrice
                if fill_price > 100000 or fill_price < 10000:
                    fill_price = float(item.marketPrice) if item.marketPrice else self._entry_price
                for evt in reversed(self._order_events):
                    if evt["status"] == "pending":
                        evt["status"] = "filled"
                        evt["fill_price"] = fill_price
                        evt["fill_time"] = pd.Timestamp.now(tz=pytz.timezone("US/Eastern"))
                        break
                
                # Place bracket TP/SL orders when entering a new position
                if self._tp_sl_enabled and new_pos != 0:
                    if old_pos == 0 or (old_pos > 0 and new_pos < 0) or (old_pos < 0 and new_pos > 0):
                        # Fresh entry OR reversal — place bracket
                        bracket_fill = float(item.averageCost) / 5.0 if item.averageCost else self._entry_price
                        direction = 1 if new_pos > 0 else -1
                        self._place_bracket_orders(bracket_fill, direction)
                elif new_pos == 0 and old_pos != 0:
                    # Just exited — cancel any remaining bracket orders
                    self._cancel_bracket_orders()
                    
                    # Send TP/SL fill alert email
                    try:
                        exit_price = float(item.marketPrice) if item.marketPrice else 0.0
                        pl_pts = 0.0
                        if self._entry_price > 0:
                            if old_pos > 0:  # was long
                                pl_pts = exit_price - self._entry_price
                            else:  # was short
                                pl_pts = self._entry_price - exit_price
                        exit_type = "TP" if pl_pts > 0 else "SL"
                        action = "SELL" if old_pos > 0 else "BUY"
                        
                        # Record bracket exit as an order event for chart/CSV
                        self._order_events.append({
                            "time": pd.Timestamp.now(tz=pytz.timezone("US/Eastern")).floor("min"),
                            "signal": action,
                            "signal_price": exit_price,
                            "limit_price": exit_price,
                            "status": "filled",
                            "fill_price": exit_price,
                            "fill_time": pd.Timestamp.now(tz=pytz.timezone("US/Eastern")),
                            "is_liquidation": True,
                            "is_partial_tp": False,
                        })
                        
                        send_trade_alert(
                            action=action,
                            price=exit_price,
                            qty=abs(old_pos),
                            session_pl=pl_pts,
                            target_date=self._current_date or "",
                            position="flat",
                            order_type=f"BRACKET {exit_type} ({pl_pts:+.0f} pts)",
                        )
                    except Exception as exc:
                        log.error("[Email] bracket fill alert error: %s", exc)

                # IMMEDIATE CSV WRITE after fill confirmation
                try:
                    self._save_tracking_csv()
                    log.info("[PositionSync] Tracking CSV updated immediately after fill")
                except Exception as exc:
                    log.error("[PositionSync] Immediate CSV write failed: %s", exc)

    def disconnect(self) -> None:
        self._ib.disconnect()
        log.info("Disconnected from IB.")

    # -- real-time bar subscription -------------------------------------------

    def start(self) -> None:
        """Subscribe to real-time bars and run the event loop."""
        if self._contract is None:
            raise RuntimeError("Call connect() before start().")

        # Always set the dynamic window from wall-clock now.
        if not self._window_set:
            self._apply_dynamic_window(None)

        # Backfill historical bars from session start (09:30 for day, 18:00 for night).
        self._backfill_from_session_start()

        # Set _last_signal_ts to NOW so backfilled historical signals never trigger orders.
        # Only signals that arrive AFTER this point will place orders.
        self._last_signal_ts = pd.Timestamp.now(tz=_EST)
        self._last_partial_tp_ts = self._last_signal_ts
        log.info("[Start] Signal guard set to %s — backfill signals will not place orders.",
                 self._last_signal_ts.strftime("%H:%M:%S"))

        # If backfill loaded bars, open the chart immediately so the user can
        # see history before the first live bar arrives.
        if self._session_bars:
            log.info("[Backfill] triggering initial chart from backfilled data ...")
            try:
                self._update_live_chart()
            except Exception as exc:
                log.error("[Backfill] initial chart error: %s", exc)

        # reqRealTimeBars works on both live and paper accounts.
        # It delivers a new 5-second bar every 5 seconds.
        bars = self._ib.reqRealTimeBars(
            self._contract,
            barSize=5,
            whatToShow="TRADES",
            useRTH=False,
        )

        bars.updateEvent += self._on_realtime_bar
        log.info("Subscribed to real-time bars for %s", self._contract.localSymbol)
        log.info("Press Ctrl+C to stop.")

        self._ib.setTimeout(0.2)
        self._ib.timeoutEvent += self._on_timeout

        try:
            self._ib.run()
        except KeyboardInterrupt:
            log.info("Interrupted.")
        except Exception as exc:
            log.error("Unexpected error in event loop: %s", exc)
        finally:
            # Only flatten here if auto-end didn't already handle it.
            # _session_ended=True means auto-end already ran _on_session_end.
            if not self._session_ended:
                log.info("Flattening any open position before exit ...")
                self._on_session_end()
            self.disconnect()

    # -- dynamic session window -----------------------------------------------

    def _apply_dynamic_window(self, first_bar_time) -> None:
        """Anchor session_start_dt to the fixed start_time (e.g. 18:00 for night, 09:30 for day).
        No bars before start_time will ever enter the algo or chart.
        """
        self._window_set = True
        now = datetime.now(_EST)
        today = now.strftime("%Y-%m-%d")
        try:
            session_start = _EST.localize(
                datetime.strptime(f"{today} {self.start_time}:00", "%Y-%m-%d %H:%M:%S")
            )
        except Exception:
            session_start = now
        end_dt = session_start + pd.Timedelta(minutes=self._session_duration_minutes)
        self.end_time = end_dt.strftime("%H:%M")
        self._session_start_dt = session_start
        log.info(
            "[Window] session window: %s – %s (%d min)",
            self.start_time, self.end_time, self._session_duration_minutes,
        )

    # -- session finalisation -------------------------------------------------

    def _on_session_end(self) -> None:
        """Finalise the current session: save image, CSV, then reset state."""

        if not self._session_bars or not self._current_date:
            self._live_chart = None
            self._session_bars = []
            self._last_result = None
            self._last_minute = None
            return

        log.info("[Session] %s ended — saving data and chart.", self._current_date)

        # Flatten any open position at session end — use actual IB position as source of truth
        try:
            # Refresh from IB first to get the real position
            try:
                positions = self._ib.positions()
                for p in positions:
                    if p.contract.symbol in ("YM", "MYM"):
                        self._ib_position = int(p.position)
                        break
            except Exception as exc:
                log.warning("[Session] could not refresh IB position before flatten: %s", exc)

            if self._ib_position > 0:
                log.info("[Session] flattening LONG %d contracts at session end", self._ib_position)
                self._place_order("SELL", liquidate=True)
                self._ib.sleep(5)  # wait for fill before disconnect
            elif self._ib_position < 0:
                log.info("[Session] flattening SHORT %d contracts at session end", abs(self._ib_position))
                self._place_order("BUY", liquidate=True)
                self._ib.sleep(5)  # wait for fill before disconnect
            else:
                log.info("[Session] position already flat at session end")
        except Exception as exc:
            log.error("[Session] flatten error: %s", exc)

        # Save the chart image directly from the live figure before closing it.
        # If running headless (--no-plot), render the final chart now for saving.
        if self._live_chart is None and self.enable_chart:
            log.info("[Session] rendering final chart for image save (headless mode) ...")
            self._update_live_chart(filter_to_session=True, force=True)

        saved_image_path = None
        if self._live_chart is not None and self._live_chart._plotter is not None:
            try:
                os.makedirs(self.image_root, exist_ok=True)
                img_path = os.path.join(self.image_root, f"YM_{self._current_date}_{self.start_time.replace(':','')}.jpg")
                self._live_chart._plotter.fig.savefig(img_path, dpi=150, bbox_inches="tight")
                saved_image_path = img_path
                log.info("[Session] chart image saved: %s", img_path)
            except Exception as exc:
                log.error("[Session] image save error: %s", exc)

        if self._live_chart is not None:
            self._live_chart.close()
            self._live_chart = None

        # Save tracking CSV.
        try:
            self._save_tracking_csv()
        except Exception as exc:
            log.error("[Session] _save_tracking_csv error: %s", exc)

        # NOTE: We do NOT call run_live_session here because it re-runs the
        # algo with hard start/end time filters which produces different signals
        # than what was shown on the live chart. The correct image is already
        # saved above directly from the live figure, and the CSV is saved by
        # _save_tracking_csv.

        # Send session summary email with chart image and final P/L.
        try:
            final_pl = 0.0
            final_position = "flat"
            if self._last_result is not None and not self._last_result.empty:
                final_pl = float(self._last_result["pl"].iloc[-1])
                final_position = str(self._last_result["position"].iloc[-1])
            csv_path = os.path.join(self.tracking_root, f"YM_tracking_{self._current_date}_{self.start_time.replace(':','')}.csv")
            if not os.path.exists(csv_path):
                csv_path = os.path.join(self.tracking_root, f"YM_tracking_{self._current_date}.csv")
            send_session_summary(
                target_date=self._current_date,
                start_time=self.start_time,
                end_time=self.end_time,
                final_pl=final_pl,
                image_path=saved_image_path,
                position=final_position,
                csv_path=csv_path if os.path.exists(csv_path) else None,
            )
        except Exception as exc:
            log.error("[Session] email error: %s", exc)

        self._session_bars = []
        self._last_result = None
        self._last_minute = None
        self._raw_wb = None
        self._raw_ws = None
        self._raw_path = None
        self._session_ended = False
        self._window_set = False
        self._session_start_dt = None
        self._last_hourly_save = None
        self._last_signal_ts = None
        self._last_partial_tp_ts = None
        self._pending_order = False
        self._pending_order_time = None
        self._last_position_check = None
        self._order_events = []

    def _resample_to_minutes(self, filter_to_session: bool = True, lookback_minutes: int = 0) -> pd.DataFrame:
        """Resample accumulated 5-second bars to OHLCV bars.

        Uses 1-minute bars during 9:30-10:30 ET and 5-minute bars outside
        that window, then concatenates into a single DataFrame.
        """
        if not self._session_bars:
            return pd.DataFrame()
        df = pd.DataFrame(self._session_bars).set_index("time")
        idx = pd.to_datetime(df.index)
        df.index = idx.tz_convert(_EST) if idx.tz is not None else idx.tz_localize(_EST)

        if filter_to_session and self._session_start_dt is not None:
            df = df[df.index >= self._session_start_dt]
        elif lookback_minutes > 0:
            cutoff = datetime.now(_EST) - pd.Timedelta(minutes=lookback_minutes)
            df = df[df.index >= cutoff]

        if df.empty:
            return pd.DataFrame()

        def _agg(d, freq):
            return d.resample(freq).agg(
                Open=("Open", "first"),
                High=("High", "max"),
                Low=("Low", "min"),
                Close=("Close", "last"),
                Volume=("Volume", "sum"),
            ).dropna(subset=["Open"])

        # Always use 1-minute bars — matches the backtest data format
        return _agg(df, "1min")

    def _update_live_chart(self, filter_to_session: bool = True, lookback_minutes: int = 0, force: bool = False) -> None:
        """Resample bars to 1-min, run the algo, and refresh the live chart window.
        
        When show_plot=False (headless/--no-plot), per-minute updates are skipped
        for performance. Use force=True at session end to render the final chart
        for image saving.
        """
        if not self.enable_chart or not self._session_bars:
            log.info("[LiveChart] skipped — enable_chart=%s  show_plot=%s  bars=%d",
                     self.enable_chart, self.show_plot, len(self._session_bars))
            return

        # In headless mode, skip per-minute renders (expensive) unless forced at session end
        if not self.show_plot and not force:
            log.info("[LiveChart] skipped — enable_chart=%s  show_plot=%s  bars=%d",
                     self.enable_chart, self.show_plot, len(self._session_bars))
            return

        minute_df = self._resample_to_minutes(filter_to_session=filter_to_session, lookback_minutes=lookback_minutes)
        if minute_df.empty:
            log.info("[LiveChart] skipped — minute_df empty")
            return

        log.info("[LiveChart] running algo on %d minute bars ...", len(minute_df))
        try:
            algo_df = run_trading_algo(
                minute_df,
                self._current_date,
                self.start_time,
                self.end_time,
                self.config,
            )
        except Exception as exc:
            log.error("[LiveChart] run_trading_algo error: %s", exc)
            return

        log.info("[LiveChart] algo done — %d rows, updating chart ...", len(algo_df))
        
        # Clear signals/position/P&L before signal guard time — those are backfill artifacts
        if self._last_signal_ts is not None and not algo_df.empty:
            guard_mask = algo_df.index < self._last_signal_ts
            if guard_mask.any():
                algo_df.loc[guard_mask, "signal"] = ""
                algo_df.loc[guard_mask, "buy_price"] = pd.NA
                algo_df.loc[guard_mask, "sell_price"] = pd.NA
                algo_df.loc[guard_mask, "position"] = "flat"
                algo_df.loc[guard_mask, "pl"] = 0.0
                algo_df.loc[guard_mask, "session_pl"] = 0.0
                if "partial_tp" in algo_df.columns:
                    algo_df.loc[guard_mask, "partial_tp"] = False
                if "is_spike_exit" in algo_df.columns:
                    algo_df.loc[guard_mask, "is_spike_exit"] = False

        # Override ALL signals/P&L with IB reality
        # The algo shows theoretical instant fills, but IB may have expired them.
        # When no fills have happened, chart should show flat/zero.
        if not algo_df.empty:
            # Build set of timestamps where signals actually filled on IB
            filled_times = set()
            for evt in self._order_events:
                if evt["status"] == "filled" and evt.get("fill_time") is not None:
                    filled_times.add(evt["fill_time"].floor("min"))
                elif evt["status"] == "filled":
                    filled_times.add(evt["time"].floor("min"))

            # Clear ALL algo signals that didn't result in IB fills
            for ts in algo_df.index:
                sig = algo_df.at[ts, "signal"] if "signal" in algo_df.columns else ""
                if sig in ("BUY", "SELL"):
                    ts_min = ts.floor("min") if hasattr(ts, 'floor') else ts
                    if ts_min not in filled_times:
                        algo_df.at[ts, "signal"] = ""
                        algo_df.at[ts, "buy_price"] = pd.NA
                        algo_df.at[ts, "sell_price"] = pd.NA
                        if "partial_tp" in algo_df.columns:
                            algo_df.at[ts, "partial_tp"] = False

            # Inject signal markers for filled events (so chart shows them)
            for evt in self._order_events:
                if evt["status"] != "filled":
                    continue
                fill_t = evt.get("fill_time") or evt["time"]
                fill_t_min = fill_t.floor("min")
                fill_p = evt.get("fill_price") or evt["limit_price"]
                # Find the closest bar in algo_df
                if fill_t_min in algo_df.index:
                    target_ts = fill_t_min
                else:
                    # Find nearest bar
                    diffs = abs(algo_df.index - fill_t_min)
                    target_ts = algo_df.index[diffs.argmin()]
                algo_df.at[target_ts, "signal"] = evt["signal"]
                algo_df.at[target_ts, "order_status"] = "filled"
                algo_df.at[target_ts, "fill_price"] = fill_p
                algo_df.at[target_ts, "limit_price"] = evt.get("limit_price", fill_p)
                if evt["signal"] == "BUY":
                    algo_df.at[target_ts, "buy_price"] = fill_p
                else:
                    algo_df.at[target_ts, "sell_price"] = fill_p

            # Recompute position and P/L from only filled events
            algo_df["position"] = "flat"
            algo_df["pl"] = 0.0
            algo_df["session_pl"] = 0.0
            if "partial_tp" in algo_df.columns:
                algo_df["partial_tp"] = False
            if "is_spike_exit" in algo_df.columns:
                algo_df["is_spike_exit"] = False
            pos = "flat"
            entry_p = 0.0
            realized = 0.0
            for evt in self._order_events:
                if evt["status"] != "filled":
                    continue
                fill_t = evt.get("fill_time") or evt["time"]
                fill_t_min = fill_t.floor("min")
                fill_p = evt.get("fill_price") or evt["limit_price"]
                if evt["signal"] == "BUY":
                    if pos == "short" and entry_p > 0:
                        realized += entry_p - fill_p
                    pos = "flat" if evt.get("is_liquidation") else "long"
                    entry_p = 0.0 if evt.get("is_liquidation") else fill_p
                elif evt["signal"] == "SELL":
                    if pos == "long" and entry_p > 0:
                        realized += fill_p - entry_p
                    pos = "flat" if evt.get("is_liquidation") else "short"
                    entry_p = 0.0 if evt.get("is_liquidation") else fill_p
                # Apply position from this fill time onward
                mask = algo_df.index >= fill_t_min
                algo_df.loc[mask, "position"] = pos

            # Compute P/L for each bar based on actual fills
            for ts in algo_df.index:
                close = float(algo_df.at[ts, "Close"])
                unrealized = 0.0
                cur_pos = algo_df.at[ts, "position"]
                if cur_pos == "long" and entry_p > 0:
                    unrealized = close - entry_p
                elif cur_pos == "short" and entry_p > 0:
                    unrealized = entry_p - close
                algo_df.at[ts, "pl"] = realized + unrealized
                algo_df.at[ts, "session_pl"] = realized + unrealized

        if self._live_chart is None:
            self._live_chart = _LiveChartWindow(
                target_date=self._current_date,
                start_time=self.start_time,
                end_time=self.end_time,
            )

        try:
            self._live_chart.update(algo_df, headless=not self.show_plot)
            # Wire the Refresh Now button to re-run _update_live_chart
            if (self._live_chart._plotter is not None and
                    getattr(self._live_chart._plotter, '_refresh_callback', None) is None):
                self._live_chart._plotter._refresh_callback = self._update_live_chart
            log.info("[LiveChart] chart updated OK  bars=%d", len(algo_df))
        except Exception as exc:
            log.error("[LiveChart] update error: %s", exc)

    # -- bar handler ----------------------------------------------------------

    def _on_realtime_bar(self, bars, has_new_bar: bool) -> None:
        """Handle each new 5-second real-time bar from reqRealTimeBars."""
        if self._session_ended:
            return
        # Check for external stop signal (e.g. from _flatten_position.py)
        _stop_file = os.path.join(_IB_LIVE_ROOT, "FRED_STOP")
        if os.path.exists(_stop_file):
            log.info("[Fred] FRED_STOP file detected — stopping session.")
            try:
                os.remove(_stop_file)
            except Exception:
                pass
            self._session_ended = True
            self._on_session_end()
            self._ib.disconnect()
            return
        if not bars:
            return

        bar = bars[-1]
        # bar.time is already a datetime object in UTC
        bar_time = bar.time.astimezone(_EST)
        bar_date   = bar_time.strftime("%Y-%m-%d")
        bar_minute = bar_time.strftime("%Y-%m-%d %H:%M")

        if self._current_date is not None and bar_date != self._current_date:
            self._on_session_end()

        self._current_date = bar_date

        # Always use 1-minute bar boundaries — matches backtest data format
        bar_boundary = bar_minute

        # Fire at the correct boundary (1-min or 5-min depending on time of day).
        if self._last_minute is not None and bar_boundary != self._last_minute:
            log.info("[OnBar] bar boundary  %s → %s  buffered=%d",
                     self._last_minute, bar_boundary, len(self._session_bars))
            try:
                self._update_live_chart()
            except Exception as exc:
                log.error("[OnBar] _update_live_chart error: %s", exc)
            try:
                self._run_algo()
            except Exception as exc:
                log.error("[OnBar] _run_algo error: %s", exc)
            try:
                self._save_tracking_csv()
            except Exception as exc:
                log.error("[OnBar] _save_tracking_csv error: %s", exc)

        self._last_minute = bar_boundary

        # Save hourly chart snapshot (on the hour: 10:00, 11:00, 12:00 ...)
        current_hour = bar_time.hour
        if (bar_time.minute == 0 and
                self._last_hourly_save != current_hour and
                self._live_chart is not None and
                self._live_chart._plotter is not None):
            try:
                os.makedirs(self.image_root, exist_ok=True)
                snap_path = os.path.join(
                    self.image_root,
                    f"YM_{bar_date}_{current_hour:02d}00_snapshot.jpg"
                )
                self._live_chart._plotter.fig.savefig(snap_path, dpi=150, bbox_inches="tight")
                self._last_hourly_save = current_hour
                log.info("[Snapshot] hourly chart saved: %s", snap_path)
            except Exception as exc:
                log.error("[Snapshot] save error: %s", exc)

        # Print each bar to terminal for live visibility
        print(f"  {bar_time.strftime('%H:%M:%S')}  O={bar.open_}  H={bar.high}  L={bar.low}  C={bar.close}  V={int(bar.volume)}")

        self._session_bars.append({
            "Open":   bar.open_,
            "High":   bar.high,
            "Low":    bar.low,
            "Close":  bar.close,
            "Volume": bar.volume,
            "time":   bar_time,
        })
        self._append_bar_to_excel(bar_time, bar)

        # Show chart on the very first bar (after appending so data exists).
        if len(self._session_bars) == 1:
            log.info("[OnBar] first bar received — opening chart")
            try:
                self._update_live_chart()
            except Exception as exc:
                log.error("[OnBar] initial chart error: %s", exc)

        # Auto-end session at end_time.
        try:
            end_naive = datetime.strptime(f"{bar_date} {self.end_time}:00", "%Y-%m-%d %H:%M:%S")
            end_dt = _EST.localize(end_naive)
            # If end_time is earlier than start_time it's an overnight session —
            # use tomorrow's date for the end.
            if self._session_start_dt is not None and end_dt <= self._session_start_dt:
                from datetime import timedelta
                end_dt = end_dt + timedelta(days=1)
            if bar_time >= end_dt and not self._session_ended:
                self._session_ended = True
                log.info("[OnBar] end_time %s reached — finalising session.", self.end_time)
                self._on_session_end()
                self._ib.sleep(3)  # ensure flatten order is processed before disconnect
                self._ib.disconnect()
        except Exception as exc:
            log.error("[OnBar] auto-end check error: %s", exc)

    def _on_bar(self, bars, has_new_bar: bool) -> None:
        """Legacy handler kept for compatibility — delegates to _on_realtime_bar."""
        self._on_realtime_bar(bars, has_new_bar)

    # -- Tkinter pump ---------------------------------------------------------

    def _on_timeout(self, elapsed: float) -> None:
        """Called every 200 ms by ib_insync to keep the chart window responsive."""
        if self._live_chart is not None and self.show_plot:
            self._live_chart.pump()
        self._ib.setTimeout(0.2)

    # -- raw 5-second Excel log ----------------------------------------------

    def _append_bar_to_excel(self, bar_time: datetime, bar) -> None:
        """Append one 5-second bar row to the per-day raw Excel workbook."""
        if not self.tracking_root:
            return

        if self.account_id:
            path = os.path.join(self.tracking_root, f"YM_raw_{self.account_id}_{self._current_date}.xlsx")
        else:
            path = os.path.join(self.tracking_root, f"YM_raw_{self._current_date}.xlsx")

        if self._raw_wb is None:
            os.makedirs(self.tracking_root, exist_ok=True)
            self._raw_wb = Workbook()
            self._raw_ws = self._raw_wb.active
            self._raw_ws.append(["Time", "Open", "High", "Low", "Close", "Volume"])
            self._raw_path = path

        self._raw_ws.append([
            bar_time.strftime("%Y-%m-%d %H:%M:%S"),
            bar.open_, bar.high, bar.low, bar.close, bar.volume,
        ])
        self._raw_wb.save(self._raw_path)

    # -- per-minute tracking CSV ---------------------------------------------

    def _save_tracking_csv(self) -> None:
        """Resample current session bars and save the live tracking CSV.

        Called at every minute boundary so ``YM_tracking_{date}_{time}.csv`` reflects
        the latest algo output throughout the session, not just at session end.
        
        Overlays actual IB order events (filled/expired/pending) onto the algo's
        theoretical signals so the CSV reflects reality.
        """
        if not self.tracking_root or not self._current_date or not self._session_bars:
            return

        minute_df = self._resample_to_minutes()
        if minute_df.empty:
            return

        try:
            algo_df = run_trading_algo(
                minute_df,
                self._current_date,
                self.start_time,
                self.end_time,
                self.config,
            )
        except Exception as exc:
            log.error("[TrackingCSV] run_trading_algo error: %s", exc)
            return

        # Overlay actual IB order events onto the algo DataFrame
        algo_df["order_status"] = ""
        algo_df["limit_price"] = pd.NA
        algo_df["fill_price"] = pd.NA
        
        # Build actual position/P&L from IB fills only
        ib_position = "flat"
        ib_entry_price = 0.0
        ib_realized_pl = 0.0
        ib_positions = []
        ib_pls = []
        
        # Index order events by their signal time for fast lookup
        filled_events = {evt["time"]: evt for evt in self._order_events if evt["status"] == "filled"}
        expired_events = {evt["time"]: evt for evt in self._order_events if evt["status"] == "expired"}
        pending_events = {evt["time"]: evt for evt in self._order_events if evt["status"] == "pending"}
        
        for ts in algo_df.index:
            # Check if this bar has an IB order event
            # Round to minute for matching
            ts_min = ts.floor("min")
            
            if ts_min in filled_events:
                evt = filled_events[ts_min]
                algo_df.at[ts, "order_status"] = "filled"
                algo_df.at[ts, "limit_price"] = evt["limit_price"]
                algo_df.at[ts, "fill_price"] = evt["fill_price"]
                
                # Update IB-based position tracking
                fill_p = evt["fill_price"] or evt["limit_price"]
                if evt["signal"] == "BUY":
                    if ib_position == "short" and ib_entry_price > 0:
                        ib_realized_pl += ib_entry_price - fill_p
                    if not evt.get("is_liquidation"):
                        ib_position = "long"
                        ib_entry_price = fill_p
                    else:
                        ib_position = "flat"
                        ib_entry_price = 0.0
                elif evt["signal"] == "SELL":
                    if ib_position == "long" and ib_entry_price > 0:
                        ib_realized_pl += fill_p - ib_entry_price
                    if not evt.get("is_liquidation"):
                        ib_position = "short"
                        ib_entry_price = fill_p
                    else:
                        ib_position = "flat"
                        ib_entry_price = 0.0
                        
            elif ts_min in expired_events:
                evt = expired_events[ts_min]
                algo_df.at[ts, "order_status"] = "expired"
                algo_df.at[ts, "limit_price"] = evt["limit_price"]
                # Clear the theoretical signal — it didn't actually execute
                algo_df.at[ts, "signal"] = ""
                algo_df.at[ts, "buy_price"] = pd.NA
                algo_df.at[ts, "sell_price"] = pd.NA
                
            elif ts_min in pending_events:
                evt = pending_events[ts_min]
                algo_df.at[ts, "order_status"] = "pending"
                algo_df.at[ts, "limit_price"] = evt["limit_price"]
            
            # Compute IB-based P/L (realized + unrealized)
            close = float(algo_df.at[ts, "Close"])
            unrealized = 0.0
            if ib_position == "long" and ib_entry_price > 0:
                unrealized = close - ib_entry_price
            elif ib_position == "short" and ib_entry_price > 0:
                unrealized = ib_entry_price - close
            
            ib_positions.append(ib_position)
            ib_pls.append(ib_realized_pl + unrealized)
        
        # Override position and P/L with IB actuals if we have any order events
        if self._order_events:
            algo_df["ib_position"] = ib_positions
            algo_df["ib_pl"] = ib_pls

        try:
            os.makedirs(self.tracking_root, exist_ok=True)
            start_time_str = self.start_time.replace(':', '')
            if self.account_id:
                path = os.path.join(self.tracking_root, f"YM_tracking_{self.account_id}_{self._current_date}_{start_time_str}.csv")
            else:
                path = os.path.join(self.tracking_root, f"YM_tracking_{self._current_date}_{start_time_str}.csv")
            algo_df.to_csv(path)
            log.info("[TrackingCSV] saved  %s  rows=%d", path, len(algo_df))
        except Exception as exc:
            log.error("[TrackingCSV] write error: %s", exc)

    # -- algo delegation ------------------------------------------------------

    def _run_algo(self) -> None:
        """Build the growing session DataFrame, run TradingAlgo + Pinball overlay."""
        if not self._session_bars:
            return

        minute_df = self._resample_to_minutes()
        if minute_df.empty:
            return
        target_date = self._current_date

        try:
            result = run_trading_algo(
                minute_df,
                target_date=target_date,
                start_time=self.start_time,
                end_time=self.end_time,
                config=self.config,
            )
        except Exception as exc:
            log.error("[TradingAlgo] run error: %s", exc)
            return

        self._last_result = result

        # --- PRE-TRADE POSITION RECONCILIATION (safety check before every signal) ---
        try:
            positions = self._ib.positions()
            for p in positions:
                if p.contract.symbol in ("YM", "MYM"):
                    real_pos = int(p.position)
                    if real_pos != self._ib_position:
                        log.warning("[PositionSync] PRE-TRADE RECONCILE: _ib_position %d -> %d (CORRECTED)",
                                    self._ib_position, real_pos)
                        self._ib_position = real_pos
                    break
        except Exception as exc:
            log.error("[PositionSync] Pre-trade reconcile failed: %s", exc)

        # --- Run Ray Engine signals for trade decisions ---
        # The ray engine's signal column tells us BUY/SELL on ray crossings.
        # We use TP/SL brackets for exits, cushion limit for entries.
        import time

        # Get the latest signal from the ray engine
        last_row = result.iloc[-1]
        current_signal = str(last_row.get("signal", "")).strip()
        current_time = result.index[-1]

        # Check pending order timeout — 5 minutes (5 bars) for limit orders to fill
        if self._pending_order and self._pending_order_time is not None:
            elapsed = time.time() - self._pending_order_time
            if elapsed > 300.0:  # 5 minutes
                log.info("[RayEngine] Limit order expired after 5 minutes — cancelling")
                try:
                    open_trades = self._ib.openTrades()
                    for t in open_trades:
                        if t.contract.symbol in ("YM", "MYM") and t.orderStatus.status in ("PreSubmitted", "Submitted"):
                            self._ib.cancelOrder(t.order)
                            log.info("[RayEngine] Cancelled expired order %d", t.order.orderId)
                except Exception as exc:
                    log.warning("[RayEngine] Could not cancel expired order: %s", exc)
                # Mark order event as expired
                for evt in reversed(self._order_events):
                    if evt["status"] == "pending":
                        evt["status"] = "expired"
                        break
                self._pending_order = False
                self._pending_order_time = None

        # Emergency position validation (every 60 seconds)
        if self._last_position_check is None or (time.time() - self._last_position_check) > 60.0:
            self._last_position_check = time.time()
            max_allowed = self.config.num_contracts
            if abs(self._ib_position) > max_allowed:
                log.error("[EMERGENCY] Position %d exceeds max %d — FLATTENING", self._ib_position, max_allowed)
                try:
                    if self._ib_position > 0:
                        excess = self._ib_position - max_allowed
                        order = MarketOrder("SELL", excess)
                        order.tif = "DAY"
                        self._ib.placeOrder(self._contract, order)
                    elif self._ib_position < 0:
                        excess = abs(self._ib_position) - max_allowed
                        order = MarketOrder("BUY", excess)
                        order.tif = "DAY"
                        self._ib.placeOrder(self._contract, order)
                except Exception as exc:
                    log.error("[EMERGENCY] Failed to flatten excess position: %s", exc)

        # Skip duplicate signals — only act on NEW signals (different timestamp from last)
        if current_signal not in ("BUY", "SELL"):
            return
        if self._last_signal_ts is not None and current_time <= self._last_signal_ts:
            return

        # Determine target position from signal
        nc = self.config.num_contracts
        if current_signal == "BUY":
            target_contracts = nc   # +2
        else:
            target_contracts = -nc  # -2

        # Skip if already in the target direction
        if target_contracts == self._ib_position:
            return

        # If pending order exists, check if direction changed
        if self._pending_order:
            if target_contracts != self._pending_target:
                # Signal changed direction — cancel pending and place new
                log.info("[RayEngine] Direction changed (pending=%d, new=%d) — cancelling",
                         self._pending_target, target_contracts)
                try:
                    open_trades = self._ib.openTrades()
                    for t in open_trades:
                        if t.contract.symbol in ("YM", "MYM") and t.orderStatus.status in ("PreSubmitted", "Submitted"):
                            self._ib.cancelOrder(t.order)
                            log.info("[RayEngine] Cancelled order %d for direction change", t.order.orderId)
                except Exception as exc:
                    log.warning("[RayEngine] Could not cancel for direction change: %s", exc)
                self._pending_order = False
                self._pending_order_time = None
            else:
                # Same direction — order already working
                return

        # Place the order
        if target_contracts > self._ib_position:
            action = "BUY"
        else:
            action = "SELL"

        price = float(minute_df["Close"].iloc[-1])
        is_liquidation = False  # TP/SL brackets handle exits, not liquidation orders
        is_partial = False

        log.info("[RayEngine] SIGNAL=%s  target=%d  ib_pos=%d  price=%.2f  time=%s",
                 current_signal, target_contracts, self._ib_position, price, current_time.strftime('%H:%M'))
        self._place_order(action, liquidate=is_liquidation, partial_tp=is_partial)
        self._pending_target = target_contracts
        self._last_signal_ts = current_time

    # -- order execution ------------------------------------------------------

    def _place_order(self, action: str, liquidate: bool = False, partial_tp: bool = False, algo_target_position: str = "flat") -> None:
        """Submit a market order for MYM contracts.

        - Entry (flat → long/short): 2 contracts
        - Partial TP: 1 contract (close half)
        - Liquidate (exit only): 2 contracts
        - Reversal (long → short or short → long): 4 contracts (close 2 + open 2)
        
        algo_target_position: The algo's intended position AFTER this order executes ("long", "short", or "flat")
        """
        tag = "LIQUIDATE" if liquidate else ("PARTIAL_TP" if partial_tp else action)
        if self.dry_run:
            log.info("[ORDER dry_run] %-10s  contract=%s", tag, self._contract.localSymbol)
            return

        # Cancel bracket orders before signal exit or reversal
        if liquidate or (not partial_tp and self._ib_position != 0):
            self._cancel_bracket_orders()

        # Determine current position size from algo's last known state (not IB's stale position)
        current_pos = 0
        if self._last_result is not None and not self._last_result.empty:
            pos = str(self._last_result["position"].iloc[-1])
            if pos == "long":
                current_pos = 2
            elif pos == "short":
                current_pos = -2

        # Refresh position from IB before calculating qty to avoid stale estimates
        try:
            positions = self._ib.positions()
            for p in positions:
                if p.contract.symbol in ("YM", "MYM"):
                    real_pos = int(p.position)
                    if real_pos != self._ib_position:
                        log.info("[PositionSync] Pre-order reconcile: _ib_position %d -> %d",
                                 self._ib_position, real_pos)
                        self._ib_position = real_pos
                    break
        except Exception as exc:
            log.warning("[PositionSync] Could not refresh position before order: %s", exc)

        # Calculate quantity — USE ALGO'S TARGET POSITION, NOT IB'S STALE POSITION
        nc = self.config.num_contracts
        if partial_tp:
            # Close the larger half: (position // 2) + 1 for odd numbers
            # Examples: 2→1, 3→2, 5→3, 7→4, 9→5, 11→6
            pos_size = abs(self._ib_position)
            qty = (pos_size // 2) + (pos_size % 2)  # rounds up for odd numbers
            qty = max(1, qty)
        elif liquidate:
            qty = abs(self._ib_position) if self._ib_position != 0 else nc
        else:
            # NEW LOGIC: Calculate qty based on algo's target position, not IB's current position
            # This prevents doubling orders when IB's position() API returns stale data
            if algo_target_position == "long":
                # Algo wants to be long nc contracts
                if current_pos == 0:
                    qty = nc  # flat → long
                elif current_pos < 0:
                    qty = nc + abs(current_pos)  # short → long (cover + reverse)
                else:
                    qty = 0  # already long, skip (shouldn't happen due to duplicate check)
            elif algo_target_position == "short":
                # Algo wants to be short nc contracts
                if current_pos == 0:
                    qty = nc  # flat → short
                elif current_pos > 0:
                    qty = nc + current_pos  # long → short (cover + reverse)
                else:
                    qty = 0  # already short, skip (shouldn't happen due to duplicate check)
            else:
                # algo_target_position == "flat" (liquidation)
                qty = abs(current_pos) if current_pos != 0 else 0

        qty = max(1, qty)  # always at least 1
        log.info("[ORDER calc]    current_pos=%d  target=%s  action=%s  qty=%d", 
                 current_pos, algo_target_position, action, qty)
        
        # Use LIMIT order for entries, MARKET order for exits/liquidations
        if liquidate or partial_tp:
            order = MarketOrder(action, totalQuantity=qty)
        else:
            # Entry: use limit order with CUSHION (40 pts better than signal)
            # BUY: limit at signal_price - cushion (buy the dip)
            # SELL: limit at signal_price + cushion (sell the rip)
            limit_price = 0.0
            if self._session_bars:
                signal_price = self._session_bars[-1].get("Close", 0.0)
                if action == "BUY":
                    limit_price = signal_price - self._cushion_points
                else:
                    limit_price = signal_price + self._cushion_points
            if limit_price > 0:
                order = LimitOrder(action, totalQuantity=qty, lmtPrice=limit_price)
                self._entry_price = limit_price
                log.info("[ORDER] CUSHION LIMIT %s at %.0f (signal=%.0f, cushion=%.0f)",
                         action, limit_price, signal_price, self._cushion_points)
            else:
                order = MarketOrder(action, totalQuantity=qty)
        order.tif = "DAY"
        exec_contract = self._order_contract or self._contract
        trade = self._ib.placeOrder(exec_contract, order)
        self._pending_order = True  # cleared by _on_portfolio_update on fill confirmation
        self._pending_order_time = time.time()  # track when order was placed
        log.info("[ORDER placed]  %-10s  qty=%d  contract=%s  orderId=%s",
                 tag, qty, exec_contract.localSymbol, trade.order.orderId)

        # Record order event for live tracking CSV/chart
        signal_price = self._session_bars[-1].get("Close", 0.0) if self._session_bars else 0.0
        _lmt = getattr(order, 'lmtPrice', 0.0) or 0.0
        self._order_events.append({
            "time": pd.Timestamp.now(tz=pytz.timezone("US/Eastern")).floor("min"),
            "signal": action,
            "signal_price": signal_price,
            "limit_price": _lmt if _lmt > 0 else signal_price,
            "status": "pending",
            "fill_price": None,
            "fill_time": None,
            "is_liquidation": liquidate,
            "is_partial_tp": partial_tp,
        })

        # NOTE: _ib_position is now updated by _on_portfolio_update() on fill confirmation,
        # not here on order placement. This prevents the race condition where a partial TP
        # order is placed but not yet filled when the next signal fires.

        # Send trade alert email
        try:
            session_pl = 0.0
            position = "flat"
            if self._last_result is not None and not self._last_result.empty:
                session_pl = float(self._last_result["pl"].iloc[-1])
                position   = str(self._last_result["position"].iloc[-1])
            fill_price = 0.0
            if self._session_bars:
                fill_price = self._session_bars[-1].get("Close", 0.0)
            send_trade_alert(
                action=action,
                price=fill_price,
                qty=qty,
                session_pl=session_pl,
                target_date=self._current_date or "",
                position=position,
                order_type="LIQUIDATE" if liquidate else "ENTRY/REVERSAL",
            )
        except Exception as exc:
            log.error("[Email] trade alert error: %s", exc)

    def _place_bracket_orders(self, entry_price: float, direction: int) -> None:
        """Place TP limit and SL stop orders after entry fill.
        direction: +1 for long, -1 for short.
        TP=60 pts total, SL=50 pts total."""
        if not self._tp_sl_enabled or self.dry_run:
            return

        self._entry_price = entry_price
        nc = abs(self._ib_position) or self.config.num_contracts
        exec_contract = self._order_contract or self._contract

        # TP: limit order to close at profit
        tp_price = entry_price + (self._tp_points / 2) * direction  # per-contract price move
        # SL: stop order to close at loss
        sl_price = entry_price - (self._sl_points / 2) * direction

        if direction > 0:  # long position → sell to close
            tp_order = LimitOrder("SELL", nc, tp_price)
            sl_order = StopOrder("SELL", nc, sl_price)
        else:  # short position → buy to close
            tp_order = LimitOrder("BUY", nc, tp_price)
            sl_order = StopOrder("BUY", nc, sl_price)

        tp_order.tif = "DAY"
        sl_order.tif = "DAY"
        tp_order.ocaGroup = f"FRED_BRACKET_{int(time.time())}"
        sl_order.ocaGroup = tp_order.ocaGroup
        tp_order.ocaType = 1  # cancel other on fill
        sl_order.ocaType = 1

        try:
            self._bracket_tp_order = self._ib.placeOrder(exec_contract, tp_order)
            self._bracket_sl_order = self._ib.placeOrder(exec_contract, sl_order)
            log.info("[BRACKET] Placed TP=%.0f SL=%.0f for %s %d contracts (OCA: %s)",
                     tp_price, sl_price, "LONG" if direction > 0 else "SHORT", nc, tp_order.ocaGroup)
        except Exception as exc:
            log.error("[BRACKET] Failed to place bracket orders: %s", exc)

    def _cancel_bracket_orders(self) -> None:
        """Cancel any active TP/SL bracket orders (called before signal exit)."""
        if self.dry_run:
            return
        try:
            if self._bracket_tp_order:
                self._ib.cancelOrder(self._bracket_tp_order.order)
                log.info("[BRACKET] Cancelled TP order")
                self._bracket_tp_order = None
            if self._bracket_sl_order:
                self._ib.cancelOrder(self._bracket_sl_order.order)
                log.info("[BRACKET] Cancelled SL order")
                self._bracket_sl_order = None
        except Exception as exc:
            log.error("[BRACKET] Cancel error: %s", exc)


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def run_connection_test(host: str, port: int, client_id: int) -> None:
    """Connect, print account / contract info, then disconnect.

    No bars are subscribed and no orders are placed -- safe to run at any
    time to verify that TWS / IB Gateway is reachable.
    """
    ib = IB()
    log.info("Connecting to %s:%s (clientId=%s) ...", host, port, client_id)
    ib.connect(host, port, clientId=client_id)
    log.info("Connected.  Server version: %s", ib.client.serverVersion())

    accounts = ib.managedAccounts()
    log.info("Managed accounts : %s", accounts)

    try:
        c = resolve_ym_front_month(ib)
        log.info(
            "YM front-month   : symbol=%s  expiry=%s  exchange=%s",
            c.localSymbol, c.lastTradeDateOrContractMonth, c.exchange,
        )
    except RuntimeError as exc:
        log.warning("Could not resolve YM front-month contract: %s", exc)

    ib.disconnect()
    log.info("Disconnected.  Connection test PASSED.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="IB data bridge for YM TradingAlgo strategy.")
    p.add_argument("--host",      default="127.0.0.1",
                   help="TWS/Gateway host (default: 127.0.0.1)")
    p.add_argument("--port",      type=int, default=4002,
                   help="TWS/Gateway port (default: 4002 = IB Gateway paper)")
    p.add_argument("--client-id",     type=int, default=1, dest="client_id")
    p.add_argument("--account-id",    type=str, default=None, dest="account_id",
                   help="Account ID for file naming (e.g., DUO158495, DUQ921172)")
    p.add_argument("--test",           action="store_true",
                   help="Run connection test only, then exit.")
    p.add_argument("--dry-run",        action="store_true", dest="dry_run",
                   help="Log signals without placing orders.")
    # start_time and end_time are set dynamically from the first bar received.
    # These args are kept for manual override / backtesting use only.
    p.add_argument("--start-time",     default="09:30", dest="start_time",
                   help="Override session start time (default: auto from first bar).")
    p.add_argument("--end-time",       default="09:40", dest="end_time",
                   help="Override session end time (default: 10 min after first bar).")
    p.add_argument("--duration",       type=int, default=105, dest="duration",
                   help="Session duration in minutes (default: 105 = 9:30-11:15).")
    p.add_argument("--no-plot",        action="store_false", dest="show_plot",
                   help="Disable the live interactive chart.")
    p.set_defaults(show_plot=True)
    p.add_argument("--tracking-root",  default=os.path.join(_IB_LIVE_ROOT, "tracking"), dest="tracking_root",
                   help="Directory to save per-day tracking CSVs (default: ~/Desktop/IB_Live/tracking).")
    p.add_argument("--image-root",     default=os.path.join(_IB_LIVE_ROOT, "charts"), dest="image_root",
                   help="Directory to save per-day chart images (default: ~/Desktop/IB_Live/charts).")
    return p





if __name__ == "__main__":
    util.logToConsole(logging.WARNING)   # suppress ib_insync verbose output

    args = _build_parser().parse_args()

    if args.test:
        run_connection_test(args.host, args.port, args.client_id)
    else:
        # Single account mode
        bridge = IBDataBridge(
            host=args.host,
            port=args.port,
            client_id=args.client_id,
            account_id=args.account_id,
            dry_run=args.dry_run,
            start_time=args.start_time,
            end_time=args.end_time,
            show_plot=args.show_plot,
            tracking_root=args.tracking_root,
            image_root=args.image_root,
            session_duration_minutes=args.duration,
        )
        bridge.connect()
        bridge.start()
