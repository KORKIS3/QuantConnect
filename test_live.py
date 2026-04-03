"""test_live.py -- 30-minute live YM session monitor.

Keeps IB Gateway open, accumulates 5-sec bars, and on every minute boundary:
  1. Resamples to 1-minute OHLCV
  2. Runs TradingAlgo  (signals, rays, P/L)
  3. Overwrites the tracking CSV
  4. Refreshes the live interactive chart in-place

The chart window uses plt.ion() so it stays open and redraws without
blocking the IB event loop.  After the session ends the window stays
open with navigation buttons so you can step through the bars.

Usage:
    python test_live.py                 # 30-min live session + chart
    python test_live.py --no-plot       # 30-min, CSV only (headless)
    python test_live.py --duration 60   # run for 60 minutes instead
"""

import asyncio
import os
import sys
import logging
import threading
from datetime import datetime
from typing import Optional

import pytz
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ib_insync import IB, util
from InteractiveBrokers import resolve_ym_front_month, _LiveChartWindow
from TradingAlgo import run_trading_algo, AlgoConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_EST = pytz.timezone("US/Eastern")
TRACKING_ROOT    = r"C:\Users\Administrator\Desktop\IB_Live\tracking"
IMAGE_ROOT       = r"C:\Users\Administrator\Desktop\IB_Live\images"

SESSION_START    = "09:00"   # algo cutoff = SESSION_START + 8 min = 09:08
SESSION_END      = "10:30"
SESSION_DURATION = 90        # minutes: 09:00 → 10:30


# ---------------------------------------------------------------------------
# Live session monitor
# ---------------------------------------------------------------------------

class LiveSessionMonitor:
    """Accumulates live 5-sec IB bars and runs the full pipeline every minute.

    Parameters
    ----------
    duration_minutes:
        How long to keep the session open before disconnecting.
    show_plot:
        If True, display and refresh the interactive ChartPlotter window.
    config:
        AlgoConfig forwarded to run_trading_algo.
    """

    def __init__(
        self,
        duration_minutes: int = 30,
        show_plot: bool = True,
        config: Optional[AlgoConfig] = None,
    ) -> None:
        self.duration_minutes = duration_minutes
        self.show_plot = show_plot
        self.config = config or AlgoConfig()

        self._ib = IB()
        self._session_bars: list = []
        self._current_date: Optional[str] = None
        self._last_minute: Optional[str] = None
        self._session_start_time: Optional[str] = None  # HH:MM of first bar
        self._live_chart: Optional[_LiveChartWindow] = None
        self._minute_count: int = 0
        self._stop_timer: Optional[threading.Timer] = None

    # -- resampling -----------------------------------------------------------

    def _resample_to_minutes(self) -> pd.DataFrame:
        if not self._session_bars:
            return pd.DataFrame()
        df = pd.DataFrame(self._session_bars).set_index("time")
        idx = pd.to_datetime(df.index)
        df.index = idx.tz_convert(_EST) if idx.tz is not None else idx.tz_localize(_EST)
        return df.resample("1min").agg(
            Open=("Open", "first"),
            High=("High", "max"),
            Low=("Low", "min"),
            Close=("Close", "last"),
            Volume=("Volume", "sum"),
        ).dropna(subset=["Open"])

    # -- per-minute pipeline --------------------------------------------------

    def _run_pipeline(self) -> None:
        """Resample → TradingAlgo → CSV → chart refresh."""
        minute_df = self._resample_to_minutes()
        if minute_df.empty:
            return

        dt         = self._current_date
        start_time = SESSION_START
        end_time   = SESSION_END

        # 1. Run trading algorithm.
        try:
            algo_df = run_trading_algo(minute_df, dt, start_time, end_time, self.config)
        except Exception as exc:
            log.error("[Algo] error: %s", exc)
            return

        buys     = int((algo_df["signal"] == "BUY").sum())  if "signal" in algo_df.columns else 0
        sells    = int((algo_df["signal"] == "SELL").sum()) if "signal" in algo_df.columns else 0
        final_pl = round(float(algo_df["pl"].iloc[-1]), 1)  if "pl"     in algo_df.columns else 0.0

        log.info(
            "[Algo] minute=%d  bars=%d  BUY=%d  SELL=%d  pl=%+.1f pts",
            self._minute_count, len(algo_df), buys, sells, final_pl,
        )

        # 2. Overwrite tracking CSV.
        try:
            os.makedirs(TRACKING_ROOT, exist_ok=True)
            path = os.path.join(TRACKING_ROOT, f"YM_tracking_{dt}.csv")
            algo_df.to_csv(path)
            log.info("[CSV]  saved  %s  (%d rows)", path, len(algo_df))
        except Exception as exc:
            log.error("[CSV]  write error: %s", exc)

        # 3. Refresh live chart (non-blocking via plt.ion).
        if self.show_plot:
            try:
                if self._live_chart is None:
                    self._live_chart = _LiveChartWindow(dt, start_time, end_time)
                self._live_chart.update(algo_df)
            except Exception as exc:
                log.error("[Chart] update error: %s", exc)

        self._minute_count += 1
        remaining = self.duration_minutes - self._minute_count
        log.info(
            "[Monitor] %d/%d minutes complete  (~%d min remaining)",
            self._minute_count, self.duration_minutes, max(0, remaining),
        )

    # -- bar callback ---------------------------------------------------------

    def _on_bar(self, bars, has_new_bar: bool) -> None:
        if not has_new_bar or not bars:
            return

        bar      = bars[-1]
        bar_time = bar.date.astimezone(_EST) if bar.date.tzinfo else _EST.localize(bar.date)
        bar_min  = bar_time.strftime("%Y-%m-%d %H:%M")
        bar_date = bar_time.strftime("%Y-%m-%d")

        self._current_date = bar_date

        # Detect minute boundary: the previous minute's bars are now sealed.
        if self._last_minute is not None and bar_min != self._last_minute:
            log.info(
                "[OnBar] minute boundary  %s → %s  (5-sec bars buffered: %d)",
                self._last_minute, bar_min, len(self._session_bars),
            )
            try:
                self._run_pipeline()
            except Exception as exc:
                log.error("[OnBar] pipeline error: %s", exc)

        # Record the start time of the very first bar seen in this session.
        if self._last_minute is None:
            self._session_start_time = bar_time.strftime("%H:%M")

        self._last_minute = bar_min
        self._session_bars.append({
            "Open": bar.open, "High": bar.high, "Low": bar.low,
            "Close": bar.close, "Volume": bar.volume, "time": bar_time,
        })

        # On the very first live bar, refresh the chart immediately so it
        # transitions from the seed snapshot to live data without waiting for
        # a full minute boundary.
        if len(self._session_bars) == 1 and self.show_plot and self._live_chart is not None:
            try:
                self._run_pipeline()
                self._minute_count = max(0, self._minute_count - 1)
            except Exception:
                pass

    # -- session lifecycle ----------------------------------------------------

    def _schedule_stop(self) -> None:
        """Disconnect after duration_minutes using a background timer thread."""
        delay = self.duration_minutes * 60

        def _stop():
            log.info("[Monitor] %d-minute session complete — disconnecting.", self.duration_minutes)
            try:
                self._ib.disconnect()
            except Exception:
                pass

        self._stop_timer = threading.Timer(delay, _stop)
        self._stop_timer.daemon = True
        self._stop_timer.start()
        log.info("[Monitor] session will auto-stop in %d minutes.", self.duration_minutes)

    async def _gui_pump_loop(self) -> None:
        """Pump the matplotlib/Tkinter event queue every 50 ms.

        Runs as an asyncio task inside ib.run() so the chart window stays
        visible and responsive while the IB event loop owns the thread.
        """
        while True:
            if self._live_chart is not None:
                self._live_chart.pump()
            await asyncio.sleep(0.05)

    def run(self) -> None:
        """Connect, pre-load history, subscribe to live bars, run for N minutes."""
        util.logToConsole()

        log.info("Connecting to IB Gateway 127.0.0.1:4002 ...")
        self._ib.connect("127.0.0.1", 4002, clientId=97)
        log.info("Connected.  Server v%s  account=%s",
                 self._ib.client.serverVersion(), self._ib.managedAccounts())

        contract = resolve_ym_front_month(self._ib)
        log.info("Contract: %s  expiry=%s",
                 contract.localSymbol, contract.lastTradeDateOrContractMonth)

        # Request the minimum window (60 S) only to set _current_date and
        # _last_minute so the first live bar's minute-boundary detection works
        # correctly.  All historical bars are discarded immediately so the
        # chart and CSV start from a clean slate with only live data.
        log.info("Subscribing to live bars (no pre-data, trading window %s–%s) ...",
                 SESSION_START, SESSION_END)
        bars = self._ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="60 S",
            barSizeSetting="5 secs",
            whatToShow="TRADES",
            useRTH=False,
            formatDate=1,
            keepUpToDate=True,
        )

        # Walk historical bars only to set the date / last-minute reference.
        # The accumulated bars are then discarded so no pre-data appears on
        # the chart or in the CSV.
        for bar in bars:
            bar_time = bar.date.astimezone(_EST) if bar.date.tzinfo else _EST.localize(bar.date)
            self._current_date = bar_time.strftime("%Y-%m-%d")
            self._last_minute  = bar_time.strftime("%Y-%m-%d %H:%M")
            self._session_bars.append({
                "Open": bar.open, "High": bar.high, "Low": bar.low,
                "Close": bar.close, "Volume": bar.volume, "time": bar_time,
            })

        # If the seed returned no bars (HMDS error 162 — no trades in the
        # last 60 s, e.g. maintenance window or weekend), fall back to the
        # system clock so _current_date and _last_minute are always set before
        # the live subscription starts.  The live keepUpToDate subscription
        # is still active even when historical bars are absent.
        if self._current_date is None:
            now_est = datetime.now(_EST)
            self._current_date = now_est.strftime("%Y-%m-%d")
            self._last_minute  = now_est.strftime("%Y-%m-%d %H:%M")
            log.warning(
                "[Seed] No historical bars (HMDS 162).  "
                "System clock fallback: date=%s  last_minute=%s",
                self._current_date, self._last_minute,
            )

        # Show the chart immediately from seed data so the window is visible
        # before any live bar arrives.  _minute_count is reset to 0 so the
        # progress counter only reflects completed live minutes.
        if self.show_plot and self._session_bars:
            try:
                self._run_pipeline()
                self._minute_count = 0
            except Exception as exc:
                log.warning("[Chart] seed chart init failed: %s", exc)

        # Discard all historical bars — live data only from here.
        self._session_bars = []
        log.info("Ready.  Seed chart shown.  Waiting for live bars on %s ...",
                 self._current_date)

        # Wire the live callback and start the countdown timer.
        bars.updateEvent += self._on_bar
        self._schedule_stop()

        # Schedule a periodic asyncio task to pump the Tkinter event queue so
        # the chart window stays visible and responsive while ib.run() owns
        # the thread.  ensure_future() works whether or not the loop is already
        # running; it will execute alongside the IB internal coroutines once
        # ib.run() calls loop.run_forever().
        _pump_task = None
        if self.show_plot:
            try:
                loop = asyncio.get_event_loop()
                _pump_task = loop.create_task(self._gui_pump_loop())
                log.info("[Monitor] GUI pump task scheduled.")
            except Exception as exc:
                log.warning("[Monitor] GUI pump task failed to start: %s", exc)

        log.info("Live session running for %d minutes.  Press Ctrl+C to stop early.",
                 self.duration_minutes)
        try:
            self._ib.run()
        except KeyboardInterrupt:
            log.info("Interrupted by user.")
        finally:
            if self._stop_timer is not None:
                self._stop_timer.cancel()
            if _pump_task is not None:
                _pump_task.cancel()

        log.info("[Monitor] session ended  minutes_processed=%d", self._minute_count)

        # Keep the chart window open after the session so the user can
        # step through bars with the navigation buttons.
        if self.show_plot and self._live_chart is not None:
            try:
                import matplotlib.pyplot as _plt
                plotter = self._live_chart._plotter
                if plotter is not None:
                    plotter.create_navigation_buttons()
                    _plt.ioff()
                    log.info("Chart window open — close it to exit.")
                    _plt.show()
            except Exception as exc:
                log.error("[Chart] final show error: %s", exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    show_plot = "--no-plot" not in sys.argv
    duration  = SESSION_DURATION

    if "--duration" in sys.argv:
        idx = sys.argv.index("--duration")
        if idx + 1 < len(sys.argv):
            try:
                duration = int(sys.argv[idx + 1])
            except ValueError:
                pass

    log.info("Starting %d-minute live session  show_plot=%s  window=%s–%s",
             duration, show_plot, SESSION_START, SESSION_END)
    monitor = LiveSessionMonitor(duration_minutes=duration, show_plot=show_plot)
    monitor.run()


if __name__ == "__main__":
    main()
