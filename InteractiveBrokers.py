"""InteractiveBrokers.py

IB data bridge for the YM E-mini Futures trendline strategy.

Connects to TWS or IB Gateway via ib_insync, subscribes to the front-month
YM contract, and hands each bar to TradingAlgo.run_trading_algo() -- the
same engine used by QuantConnectLocal, ReOrgMain, and RunAllDays.

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

import argparse
import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import pytz
from ib_insync import IB, BarData, Contract, Future, MarketOrder, util

from TradingAlgo import AlgoConfig, run_trading_algo
from ReOrgMain import run_live_session

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_EST = pytz.timezone("US/Eastern")


# ---------------------------------------------------------------------------
# Contract helper
# ---------------------------------------------------------------------------

def resolve_ym_front_month(ib: IB) -> Contract:
    """Query IB for all active YM contracts and return the front month.

    Uses ``reqContractDetails`` so IB returns every listed expiry, then
    filters to contracts whose last trade date is today or later and sorts
    ascending -- the first entry is the front month.
    """
    from datetime import date

    base = Future(symbol="YM", exchange="CBOT", currency="USD")
    details = ib.reqContractDetails(base)
    if not details:
        raise RuntimeError("No YM contract details returned by IB.")

    today = date.today().strftime("%Y%m%d")
    active = [
        d.contract
        for d in details
        if d.contract.lastTradeDateOrContractMonth >= today
    ]
    if not active:
        raise RuntimeError("No active (non-expired) YM contracts found.")

    active.sort(key=lambda c: c.lastTradeDateOrContractMonth)
    return active[0]


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
        port: int = 7497,
        client_id: int = 1,
        config: Optional[AlgoConfig] = None,
        dry_run: bool = False,
        start_time: str = "09:30",
        end_time: str = "10:00",
        show_plot: bool = True,
        tracking_root: Optional[str] = None,
        image_root: Optional[str] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.config = config or AlgoConfig()
        self.dry_run = dry_run
        self.start_time = start_time
        self.end_time = end_time
        self.show_plot = show_plot
        self.tracking_root = tracking_root
        self.image_root = image_root

        self._ib = IB()
        self._session_bars: list[dict] = []
        self._last_result: Optional[pd.DataFrame] = None
        self._contract: Optional[Contract] = None
        self._current_date: Optional[str] = None

    # -- connection -----------------------------------------------------------

    def connect(self) -> None:
        """Connect to TWS / IB Gateway and qualify the YM contract."""
        self._ib.connect(self.host, self.port, clientId=self.client_id)
        log.info("Connected to IB at %s:%s (clientId=%s)", self.host, self.port, self.client_id)

        self._contract = resolve_ym_front_month(self._ib)
        log.info("Front-month: %s  expiry=%s", self._contract.localSymbol,
                 self._contract.lastTradeDateOrContractMonth)

    def disconnect(self) -> None:
        self._ib.disconnect()
        log.info("Disconnected from IB.")

    # -- real-time bar subscription -------------------------------------------

    def start(self) -> None:
        """Subscribe to 5-second real-time bars and run the event loop."""
        if self._contract is None:
            raise RuntimeError("Call connect() before start().")

        bars = self._ib.reqRealTimeBars(
            self._contract,
            barSize=5,
            whatToShow="TRADES",
            useRTH=False,
        )
        bars.updateEvent += self._on_bar
        log.info("Subscribed to real-time bars for %s", self._contract.localSymbol)
        log.info("Press Ctrl+C to stop.")

        try:
            self._ib.run()
        except KeyboardInterrupt:
            log.info("Interrupted.")
        finally:
            self._on_session_end()
            self.disconnect()

    # -- session finalisation -------------------------------------------------

    def _on_session_end(self) -> None:
        """Finalise the current session: call run_live_session(), then reset state.

        Triggered automatically on day rollover (first bar of a new date) or
        when ``start()`` returns after a KeyboardInterrupt.
        """
        if not self._session_bars or not self._current_date:
            self._session_bars = []
            self._last_result = None
            return

        log.info(
            "[Session] %s ended -- running ReOrgMain.run_live_session()",
            self._current_date,
        )
        df = pd.DataFrame(self._session_bars).set_index("time")
        idx = pd.to_datetime(df.index)
        df.index = (
            idx.tz_convert(_EST) if idx.tz is not None else idx.tz_localize(_EST)
        )

        try:
            run_live_session(
                df,
                target_date=self._current_date,
                start_time=self.start_time,
                end_time=self.end_time,
                show_plot=self.show_plot,
                tracking_root=self.tracking_root,
                image_root=self.image_root,
            )
        except Exception as exc:
            log.error("[Session] run_live_session error: %s", exc)

        self._session_bars = []
        self._last_result = None

    # -- bar handler ----------------------------------------------------------

    def _on_bar(self, bars: list[BarData], has_new_bar: bool) -> None:
        """Accumulate each sealed 5-second bar and run the algo.

        Detects a day rollover (bar date differs from ``_current_date``) and
        calls ``_on_session_end()`` to finalise the previous session before
        starting a fresh one.
        """
        if not has_new_bar or not bars:
            return

        bar = bars[-1]
        bar_time = datetime.fromtimestamp(bar.time, tz=timezone.utc).astimezone(_EST)
        bar_date = bar_time.strftime("%Y-%m-%d")

        if self._current_date is not None and bar_date != self._current_date:
            self._on_session_end()

        self._current_date = bar_date

        self._session_bars.append({
            "Open":   bar.open,
            "High":   bar.high,
            "Low":    bar.low,
            "Close":  bar.close,
            "Volume": bar.volume,
            "time":   bar_time,
        })

        self._run_algo()

    # -- algo delegation ------------------------------------------------------

    def _run_algo(self) -> None:
        """Build the growing session DataFrame and hand it to TradingAlgo."""
        if not self._session_bars:
            return

        df = pd.DataFrame(self._session_bars).set_index("time")
        target_date = df.index[0].strftime("%Y-%m-%d")

        try:
            result = run_trading_algo(df, target_date=target_date, config=self.config)
        except Exception as exc:
            log.error("[TradingAlgo] run error: %s", exc)
            return

        self._last_result = result
        last = result.iloc[-1]
        signal = str(last.get("signal", ""))
        is_liq = bool(last.get("is_liquidation", False))
        pl = float(last.get("pl", 0.0))
        price = float(df["Close"].iloc[-1])

        if signal == "BUY":
            if is_liq:
                log.info("[TradingAlgo] LIQUIDATION  price=%.2f  pl=%.1f", price, pl)
                self._place_order("SELL", liquidate=True)
            else:
                log.info("[TradingAlgo] BUY          price=%.2f  pl=%.1f", price, pl)
                self._place_order("BUY")
        elif signal == "SELL":
            if is_liq:
                log.info("[TradingAlgo] LIQUIDATION  price=%.2f  pl=%.1f", price, pl)
                self._place_order("BUY", liquidate=True)
            else:
                log.info("[TradingAlgo] SELL         price=%.2f  pl=%.1f", price, pl)
                self._place_order("SELL")

    # -- order execution ------------------------------------------------------

    def _place_order(self, action: str, liquidate: bool = False) -> None:
        """Submit a market order for 1 YM contract (or log it in dry-run mode)."""
        tag = "LIQUIDATE" if liquidate else action
        if self.dry_run:
            log.info("[ORDER dry_run] %-10s  contract=%s", tag, self._contract.localSymbol)
            return
        order = MarketOrder(action, totalQuantity=1)
        trade = self._ib.placeOrder(self._contract, order)
        log.info("[ORDER placed]  %-10s  orderId=%s", tag, trade.order.orderId)


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
    p.add_argument("--port",      type=int, default=7497,
                   help="TWS/Gateway port (default: 7497 = TWS paper)")
    p.add_argument("--client-id",     type=int, default=1, dest="client_id")
    p.add_argument("--test",           action="store_true",
                   help="Run connection test only, then exit.")
    p.add_argument("--dry-run",        action="store_true", dest="dry_run",
                   help="Log signals without placing orders.")
    p.add_argument("--start-time",     default="09:30", dest="start_time",
                   help="Session start time forwarded to ReOrgMain (default: 09:30).")
    p.add_argument("--end-time",       default="10:00", dest="end_time",
                   help="Session end time forwarded to ReOrgMain (default: 10:00).")
    p.add_argument("--show-plot",      action="store_true", dest="show_plot",
                   help="Show interactive chart at end of session.")
    p.add_argument("--tracking-root",  default=None, dest="tracking_root",
                   help="Directory to save per-day tracking CSVs.")
    p.add_argument("--image-root",     default=None, dest="image_root",
                   help="Directory to save per-day chart images.")
    return p


if __name__ == "__main__":
    util.logToConsole(logging.WARNING)   # suppress ib_insync verbose output

    args = _build_parser().parse_args()

    if args.test:
        run_connection_test(args.host, args.port, args.client_id)
    else:
        bridge = IBDataBridge(
            host=args.host,
            port=args.port,
            client_id=args.client_id,
            dry_run=args.dry_run,
            start_time=args.start_time,
            end_time=args.end_time,
            show_plot=args.show_plot,
            tracking_root=args.tracking_root,
            image_root=args.image_root,
        )
        bridge.connect()
        bridge.start()
