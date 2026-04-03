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
WARMUP_MINUTES = 7    # bars before this minute are observation-only
CHART_LOOKBACK = 90   # minutes used as the session window length


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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _derive_session_window(self, bar_time: datetime) -> None:
        """Compute session_start / session_end from the first live bar."""
        self._session_start = bar_time.strftime("%H:%M")
        self._session_end   = (bar_time + timedelta(minutes=CHART_LOOKBACK)).strftime("%H:%M")
        log.info(
            "[Monitor] session window: %s – %s  (warmup=%d min)",
            self._session_start, self._session_end, self.warmup_minutes,
        )

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
        if not has_new_bar or not bars:
            return

        bar      = bars[-1]
        bar_time = bar.date.astimezone(_EST) if bar.date.tzinfo else _EST.localize(bar.date)
        bar_min  = bar_time.strftime("%Y-%m-%d %H:%M")

        self._current_date = bar_time.strftime("%Y-%m-%d")

        # First live bar -- derive dynamic session window.
        if self._session_start is None:
            self._derive_session_window(bar_time)

        # Minute boundary -- sealed minute is ready to process.
        if self._last_minute is not None and bar_min != self._last_minute:
            log.info(
                "[OnBar] %s -> %s  (%d 5-sec bars buffered)",
                self._last_minute, bar_min, len(self._session_bars),
            )
            try:
                self._run_pipeline()
            except Exception as exc:
                log.error("[OnBar] %s", exc)

        self._last_minute = bar_min
        self._session_bars.append({
            "Open": bar.open, "High": bar.high, "Low": bar.low,
            "Close": bar.close, "Volume": bar.volume, "time": bar_time,
        })

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

        log.info("Connecting to IB Gateway 127.0.0.1:4002 ...")
        self._ib.connect("127.0.0.1", 4002, clientId=97)
        log.info("Connected.  Server v%s  account=%s",
                 self._ib.client.serverVersion(), self._ib.managedAccounts())

        contract = resolve_ym_front_month(self._ib)
        log.info("Contract: %s  expiry=%s",
                 contract.localSymbol, contract.lastTradeDateOrContractMonth)

        # Request 60 S of history purely to prime _current_date / _last_minute
        # so the first live minute-boundary fires correctly.
        # Historical bars are NOT accumulated -- live data only.
        log.info("Subscribing to live bars ...")
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

        for bar in bars:
            bar_time = bar.date.astimezone(_EST) if bar.date.tzinfo else _EST.localize(bar.date)
            self._current_date = bar_time.strftime("%Y-%m-%d")
            self._last_minute  = bar_time.strftime("%Y-%m-%d %H:%M")

        # Clock fallback when HMDS returns no bars (Error 162 / weekend / maintenance).
        if self._current_date is None:
            now_est = datetime.now(_EST)
            self._current_date = now_est.strftime("%Y-%m-%d")
            self._last_minute  = now_est.strftime("%Y-%m-%d %H:%M")
            log.warning(
                "[Seed] HMDS returned no bars -- clock fallback: date=%s  last_minute=%s",
                self._current_date, self._last_minute,
            )

        log.info(
            "Ready.  Waiting for live bars.  Signals start after %d-min warm-up.",
            self.warmup_minutes,
        )

        bars.updateEvent += self._on_bar

        _pump_task = None
        if self.show_plot:
            try:
                loop = asyncio.get_event_loop()
                _pump_task = loop.create_task(self._gui_pump_loop())
                log.info("[Monitor] GUI pump task scheduled.")
            except Exception as exc:
                log.warning("[Monitor] GUI pump task failed: %s", exc)

        log.info("Running -- press Ctrl+C to stop.")
        try:
            self._ib.run()
        except KeyboardInterrupt:
            log.info("Interrupted by user.")
        finally:
            if _pump_task is not None:
                _pump_task.cancel()

        log.info("[Monitor] session ended  minutes_processed=%d", self._minute_count)

        # Keep chart open after disconnect so you can inspect bars.
        if self.show_plot and self._live_chart is not None:
            try:
                import matplotlib.pyplot as _plt
                plotter = self._live_chart._plotter
                if plotter is not None:
                    plotter.create_navigation_buttons()
                    _plt.ioff()
                    log.info("Chart window open -- close it to exit.")
                    _plt.show()
            except Exception as exc:
                log.error("[Chart] final show: %s", exc)


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
