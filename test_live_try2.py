"""test_live_try2.py -- Any-time live YM session monitor.

Connects to IB Gateway, streams 5-sec bars, and on every minute boundary:
  1. Resamples to 1-minute OHLCV
  2. Runs TradingAlgo with a 7-minute warmup from the first bar received
  3. Overwrites a tracking CSV
  4. Refreshes the live interactive chart in-place

No real orders are placed -- signals are display-only (BUY/SELL markers on
the chart and in the CSV).

Session start/end times are derived from the actual first live bar, so the
script works correctly at any time of day.

Usage:
    python test_live_try2.py             # live session until Ctrl+C
    python test_live_try2.py --no-plot   # CSV-only, no chart window
"""

import asyncio
import os
import sys
import logging
from datetime import datetime, timedelta
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
TRACKING_ROOT  = r"C:\Users\Administrator\Desktop\IB_Live\tracking"
WARMUP_MINUTES = 7       # minutes before signals are generated
SESSION_END    = "10:30"  # auto-stop time (US/Eastern)


class LiveMonitor:
    """Streams live 5-sec YM bars and runs the trading pipeline every minute.

    No orders are placed.  BUY/SELL signals are computed by TradingAlgo and
    written to the chart and CSV only.
    """

    def __init__(self, show_plot: bool = True, warmup_minutes: int = WARMUP_MINUTES):
        self.show_plot       = show_plot
        self.warmup_minutes  = warmup_minutes

        self._ib             = IB()
        self._session_bars: list = []
        self._current_date: Optional[str] = None
        self._last_minute:  Optional[str] = None
        self._session_start: Optional[str] = None   # HH:MM of first live bar
        self._session_end:   Optional[str] = None   # session_start + CHART_LOOKBACK
        self._live_chart:    Optional[_LiveChartWindow] = None
        self._minute_count:  int = 0
        self._stopped:       bool = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _derive_session_window(self, bar_time: datetime) -> None:
        """Set session_start from the first live bar; session_end is SESSION_END."""
        self._session_start = bar_time.strftime("%H:%M")
        self._session_end   = SESSION_END
        signal_time = (bar_time + timedelta(minutes=self.warmup_minutes)).strftime("%H:%M")
        print(f"[Monitor] Session window: {self._session_start} \u2013 {self._session_end}  "
              f"(signals from {signal_time})")

    def _resample_to_minutes(self) -> pd.DataFrame:
        if not self._session_bars:
            return pd.DataFrame()
        df  = pd.DataFrame(self._session_bars).set_index("time")
        idx = pd.to_datetime(df.index)
        df.index = idx.tz_convert(_EST) if idx.tz is not None else idx.tz_localize(_EST)
        return df.resample("1min").agg(
            Open=("Open",   "first"),
            High=("High",   "max"),
            Low =("Low",    "min"),
            Close=("Close", "last"),
            Volume=("Volume","sum"),
        ).dropna(subset=["Open"])

    # ------------------------------------------------------------------
    # Per-minute pipeline
    # ------------------------------------------------------------------

    def _run_pipeline(self) -> None:
        minute_df = self._resample_to_minutes()
        if minute_df.empty or self._session_start is None:
            return

        config = AlgoConfig(warmup_minutes=self.warmup_minutes)

        # --- 1. Run algo (signals only, no orders) ---
        try:
            algo_df = run_trading_algo(
                minute_df,
                self._current_date,
                self._session_start,
                self._session_end,
                config,
            )
        except Exception as exc:
            log.error("[Algo] %s", exc)
            return

        buys     = int((algo_df["signal"] == "BUY").sum())  if "signal" in algo_df.columns else 0
        sells    = int((algo_df["signal"] == "SELL").sum()) if "signal" in algo_df.columns else 0
        final_pl = round(float(algo_df["pl"].iloc[-1]), 1)  if "pl"    in algo_df.columns else 0.0
        log.info(
            "[Algo] min=%d  bars=%d  BUY=%d  SELL=%d  pl=%+.1f pts",
            self._minute_count, len(algo_df), buys, sells, final_pl,
        )

        # --- 2. Overwrite CSV ---
        try:
            os.makedirs(TRACKING_ROOT, exist_ok=True)
            path = os.path.join(TRACKING_ROOT, f"YM_live_{self._current_date}.csv")
            algo_df.to_csv(path)
            log.info("[CSV]  %s  (%d rows)", path, len(algo_df))
        except Exception as exc:
            log.error("[CSV]  %s", exc)

        # --- 3. Refresh chart ---
        if self.show_plot:
            try:
                if self._live_chart is None:
                    self._live_chart = _LiveChartWindow(
                        self._current_date, self._session_start, self._session_end
                    )
                self._live_chart.update(algo_df)
            except Exception as exc:
                log.error("[Chart] %s", exc)

        self._minute_count += 1
        log.info("[Monitor] %d minute(s) processed", self._minute_count)

    # ------------------------------------------------------------------
    # IB bar callback
    # ------------------------------------------------------------------

    def _on_bar(self, bars, has_new_bar: bool) -> None:
        if not has_new_bar or not bars or self._stopped:
            return

        bar      = bars[-1]
        bar_time = bar.date.astimezone(_EST) if bar.date.tzinfo else _EST.localize(bar.date)
        bar_min  = bar_time.strftime("%Y-%m-%d %H:%M")

        self._current_date = bar_time.strftime("%Y-%m-%d")

        # First live bar -- derive session window from actual start time.
        if self._session_start is None:
            self._derive_session_window(bar_time)

        at_boundary  = (self._last_minute is not None and bar_min != self._last_minute)
        is_first     = len(self._session_bars) == 0
        prev_minute  = self._last_minute

        self._last_minute = bar_min
        self._session_bars.append({
            "Open": bar.open, "High": bar.high, "Low": bar.low,
            "Close": bar.close, "Volume": bar.volume, "time": bar_time,
        })

        # Auto-stop: at or past SESSION_END run final pipeline then disconnect.
        if bar_time.strftime("%H:%M") >= SESSION_END:
            self._stopped = True
            print(f"[Monitor] {SESSION_END} reached -- running final pipeline.")
            try:
                self._run_pipeline()
            except Exception as exc:
                log.error("[OnBar] final pipeline: %s", exc)
            print("[Monitor] Disconnecting.")
            self._ib.disconnect()
            return

        # Update chart on minute boundary or immediately on the very first bar.
        if at_boundary or is_first:
            if at_boundary:
                log.info("[OnBar] %s -> %s  (%d bars buffered)",
                         prev_minute, bar_min, len(self._session_bars))
            try:
                self._run_pipeline()
            except Exception as exc:
                log.error("[OnBar] %s", exc)
            if is_first:
                self._minute_count = 0

    # ------------------------------------------------------------------
    # GUI pump (keeps Tkinter/matplotlib responsive inside ib.run())
    # ------------------------------------------------------------------

    async def _gui_pump_loop(self) -> None:
        while True:
            if self._live_chart is not None:
                self._live_chart.pump()
            await asyncio.sleep(0.05)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def run(self) -> None:
        util.logToConsole()

        print("[Monitor] Connecting to IB Gateway 127.0.0.1:4002 ...")
        self._ib.connect("127.0.0.1", 4002, clientId=97)
        print(f"[Monitor] Connected.  Server v{self._ib.client.serverVersion()}  "
              f"account={self._ib.managedAccounts()}")

        contract = resolve_ym_front_month(self._ib)
        print(f"[Monitor] Contract: {contract.localSymbol}  "
              f"expiry={contract.lastTradeDateOrContractMonth}")

        # Prime _last_minute from a short historical window so the first live
        # minute-boundary detection fires correctly.  No bars are added to
        # _session_bars -- the chart starts clean from the current moment.
        print("[Monitor] Subscribing to live 5-sec bars (starting fresh) ...")
        live_bars = self._ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="60 S",
            barSizeSetting="5 secs",
            whatToShow="TRADES",
            useRTH=False,
            formatDate=1,
            keepUpToDate=True,
        )

        # Only use seed bars to prime _last_minute -- do NOT add to session_bars.
        for bar in live_bars:
            bar_time = bar.date.astimezone(_EST) if bar.date.tzinfo else _EST.localize(bar.date)
            self._current_date = bar_time.strftime("%Y-%m-%d")
            self._last_minute  = bar_time.strftime("%Y-%m-%d %H:%M")

        # Clock fallback (Error 162 / weekend / maintenance window).
        if self._current_date is None:
            now_est = datetime.now(_EST)
            self._current_date = now_est.strftime("%Y-%m-%d")
            self._last_minute  = now_est.strftime("%Y-%m-%d %H:%M")
            print(f"[Monitor] WARNING -- no seed bars, clock fallback: "
                  f"date={self._current_date}  last_minute={self._last_minute}")

        print(f"[Monitor] Ready.  Session ends at {SESSION_END} ET.  "
              f"Signals start {self.warmup_minutes} min after first bar.")
        print("[Monitor] Chart will appear on the first live bar.")

        live_bars.updateEvent += self._on_bar

        _pump_task = None
        if self.show_plot:
            try:
                loop = asyncio.get_event_loop()
                _pump_task = loop.create_task(self._gui_pump_loop())
                print("[Monitor] GUI pump task scheduled.")
            except Exception as exc:
                print(f"[Monitor] WARNING -- GUI pump task failed: {exc}")

        print("[Monitor] Running -- press Ctrl+C to stop.")
        try:
            self._ib.run()
        except KeyboardInterrupt:
            print("[Monitor] Interrupted by user.")
        finally:
            if _pump_task is not None:
                _pump_task.cancel()

        print(f"[Monitor] Session ended -- minutes_processed={self._minute_count}")

        # Keep chart open after disconnect.
        if self.show_plot and self._live_chart is not None:
            try:
                import matplotlib.pyplot as _plt
                plotter = self._live_chart._plotter
                if plotter is not None:
                    plotter.create_navigation_buttons()
                    _plt.ioff()
                    print("[Monitor] Chart window open -- close it to exit.")
                    _plt.show()
            except Exception as exc:
                print(f"[Monitor] ERROR -- final show: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    show_plot = "--no-plot" not in sys.argv
    log.info(
        "Starting live monitor  show_plot=%s  warmup=%d min",
        show_plot, WARMUP_MINUTES,
    )
    LiveMonitor(show_plot=show_plot, warmup_minutes=WARMUP_MINUTES).run()


if __name__ == "__main__":
    main()
