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
from datetime import datetime
from typing import Optional

import matplotlib
matplotlib.use('TkAgg')  # must be before any pyplot import for interactive windows on Windows

import pandas as pd
import pytz
from ib_insync import IB, BarData, Contract, Future, MarketOrder, util
from openpyxl import Workbook

from TradingAlgoFast import AlgoConfig, run_trading_algo_fast as run_trading_algo
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

    def update(self, algo_df: pd.DataFrame) -> None:
        """Redraw the chart at the latest frame with the current minute data."""
        import matplotlib.pyplot as _plt

        # Fixed 75-minute rolling window so visual angles stay consistent.
        _x_end   = algo_df.index[-1] + pd.Timedelta(minutes=1)
        _x_start = _x_end - pd.Timedelta(minutes=75)

        is_first = self._plotter is None
        if is_first:
            _plt.ion()
            self._plotter = ChartPlotter(
                algo_df,
                self.target_date,
                self.start_time,
                self.end_time,
                output_dir="",
                batch_mode=False,
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
            warmup_minutes=12,
            steep_angle_threshold=70.0,
            proximity_points=15.0,
            min_reversal_minutes=0,
            min_entry_angle=30.0,
            partial_tp_pts=50.0,
            spike_profit_pts=100.0,
            spike_profit_bars=5,
            wm_shield_distance=12.0,
            steep_line_reentry=False,
            steep_line_proximity=0.0,
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
                    
                    # SAFETY CHECK: Flatten any position at session start
                    if self._ib_position != 0:
                        log.warning("=" * 80)
                        log.warning("WARNING: Account is NOT FLAT at session start!")
                        log.warning("Current position: %d contracts", self._ib_position)
                        log.warning("Flattening position now...")
                        log.warning("=" * 80)
                        
                        # Flatten the position
                        if self._ib_position > 0:
                            # Long position - sell to flatten
                            from ib_insync import MarketOrder
                            order = MarketOrder("SELL", abs(self._ib_position))
                            order.tif = "DAY"
                            trade = self._ib.placeOrder(self._contract, order)
                            log.info("[Connect] Placed SELL %d to flatten long position", abs(self._ib_position))
                            self._ib.sleep(3)  # wait for fill
                        elif self._ib_position < 0:
                            # Short position - buy to flatten
                            from ib_insync import MarketOrder
                            order = MarketOrder("BUY", abs(self._ib_position))
                            order.tif = "DAY"
                            trade = self._ib.placeOrder(self._contract, order)
                            log.info("[Connect] Placed BUY %d to flatten short position", abs(self._ib_position))
                            self._ib.sleep(3)  # wait for fill
                        
                        # Re-check position after flatten
                        positions = self._ib.positions()
                        for p in positions:
                            if p.contract.symbol in ("YM", "MYM"):
                                self._ib_position = int(p.position)
                                break
                        
                        if self._ib_position == 0:
                            log.info("[Connect] ✓ Position flattened successfully — ready to trade")
                        else:
                            log.error("[Connect] ✗ Position still not flat: %d contracts", self._ib_position)
                    else:
                        log.info("[Connect] ✓ Account is FLAT — ready to trade")
                    break
        except Exception as exc:
            log.warning("[Connect] Could not sync position from IB: %s", exc)

        # Subscribe to portfolio updates so _ib_position stays accurate from real fills
        self._ib.updatePortfolioEvent += self._on_portfolio_update

    def _on_portfolio_update(self, item) -> None:
        """Called by IB on every fill - keeps _ib_position in sync with real fills."""
        if item.contract.symbol in ("YM", "MYM"):
            new_pos = int(item.position)
            if new_pos != self._ib_position:
                log.info("[PositionSync] IB fill confirmed: _ib_position %d -> %d",
                         self._ib_position, new_pos)
                self._ib_position = new_pos
                self._pending_order = False  # fill confirmed — safe to place next order
                log.info("[PositionSync] _pending_order cleared")

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

    def _update_live_chart(self, filter_to_session: bool = True, lookback_minutes: int = 0) -> None:
        """Resample bars to 1-min, run the algo, and refresh the live chart window."""
        if not self.enable_chart or not self.show_plot or not self._session_bars:
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
        if self._live_chart is None:
            self._live_chart = _LiveChartWindow(
                target_date=self._current_date,
                start_time=self.start_time,
                end_time=self.end_time,
            )

        try:
            self._live_chart.update(algo_df)
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

        self._session_bars.append({            "Open":   bar.open_,
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
        if self._live_chart is not None:
            self._live_chart.pump()
        else:
            log.debug("[Timeout] no live chart yet")
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
        
        Uses timestamped filename to prevent overwriting on restart.
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

        try:
            os.makedirs(self.tracking_root, exist_ok=True)
            # Use timestamped filename to prevent overwriting on restart
            # Format: YM_tracking_2026-05-08_0930.csv (or YM_tracking_DUO158495_2026-05-08_0930.csv for multi-account)
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
        """Build the growing session DataFrame and hand it to TradingAlgo."""
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

        # --- Scan ALL new signals since last call, not just the last bar ---
        new_rows = result[result["signal"].isin(["BUY", "SELL"])]
        if self._last_signal_ts is not None:
            new_rows = new_rows[new_rows.index > self._last_signal_ts]

        for ts, last in new_rows.iterrows():
            signal = str(last.get("signal", ""))
            is_liq = bool(last.get("is_liquidation", False))
            pl     = float(last.get("pl", 0.0))
            price  = float(minute_df["Close"].iloc[-1])
            pos    = str(last.get("position", "flat"))

            if signal == "BUY":
                if is_liq:
                    log.info("[TradingAlgo] LIQUIDATION  price=%.2f  pl=%.1f", price, pl)
                    self._place_order("BUY", liquidate=True)
                else:
                    if self._pending_order:
                        log.info("[TradingAlgo] BUY skipped — pending order not yet filled")
                        self._last_signal_ts = ts
                        continue
                    if self._ib_position > 0:
                        log.info("[TradingAlgo] BUY skipped — already long (ib_pos=%d)", self._ib_position)
                        self._last_signal_ts = ts
                        continue
                    log.info("[TradingAlgo] BUY          price=%.2f  pl=%.1f", price, pl)
                    self._place_order("BUY")
            elif signal == "SELL":
                if is_liq:
                    log.info("[TradingAlgo] LIQUIDATION  price=%.2f  pl=%.1f", price, pl)
                    self._place_order("SELL", liquidate=True)
                else:
                    if self._pending_order:
                        log.info("[TradingAlgo] SELL skipped — pending order not yet filled")
                        self._last_signal_ts = ts
                        continue
                    if self._ib_position < 0:
                        log.info("[TradingAlgo] SELL skipped — already short (ib_pos=%d)", self._ib_position)
                        self._last_signal_ts = ts
                        continue
                    log.info("[TradingAlgo] SELL         price=%.2f  pl=%.1f", price, pl)
                    self._place_order("SELL")
            self._last_signal_ts = ts

        # --- Scan ALL new partial TPs since last call ---
        new_tp_rows = result[result["partial_tp"] == True]
        if self._last_partial_tp_ts is not None:
            new_tp_rows = new_tp_rows[new_tp_rows.index > self._last_partial_tp_ts]

        for ts, last in new_tp_rows.iterrows():
            pl  = float(last.get("pl", 0.0))
            pos = str(last.get("position", "flat"))
            price = float(minute_df["Close"].iloc[-1])
            log.info("[TradingAlgo] PARTIAL TP   price=%.2f  pl=%.1f  (1 contract)", price, pl)
            if pos == "long":
                self._place_order("SELL", partial_tp=True)
            elif pos == "short":
                self._place_order("BUY", partial_tp=True)
            self._last_partial_tp_ts = ts

    # -- order execution ------------------------------------------------------

    def _place_order(self, action: str, liquidate: bool = False, partial_tp: bool = False) -> None:
        """Submit a market order for MYM contracts.

        - Entry (flat → long/short): 2 contracts
        - Partial TP: 1 contract (close half)
        - Liquidate (exit only): 2 contracts
        - Reversal (long → short or short → long): 4 contracts (close 2 + open 2)
        """
        tag = "LIQUIDATE" if liquidate else ("PARTIAL_TP" if partial_tp else action)
        if self.dry_run:
            log.info("[ORDER dry_run] %-10s  contract=%s", tag, self._contract.localSymbol)
            return

        # Determine current position size
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

        # Calculate quantity — driven by config.num_contracts (change once to scale up)
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
            if action == "BUY":
                qty = nc + max(0, -self._ib_position)   # cover shorts + go long
            else:
                qty = nc + max(0, self._ib_position)     # cover longs + go short

        qty = max(1, qty)  # always at least 1
        order = MarketOrder(action, totalQuantity=qty)
        order.tif = "DAY"
        exec_contract = self._order_contract or self._contract
        trade = self._ib.placeOrder(exec_contract, order)
        self._pending_order = True  # cleared by _on_portfolio_update on fill confirmation
        log.info("[ORDER placed]  %-10s  qty=%d  contract=%s  orderId=%s",
                 tag, qty, exec_contract.localSymbol, trade.order.orderId)

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
