"""
Tests for QuantConnectLocal.py — YM Futures Trendline Strategy.

QuantConnect's AlgorithmImports is a compiled Lean library only available
inside the QC cloud/Lean runtime. This module patches sys.modules with
lightweight Python stubs so that the algorithm logic can be exercised
locally without a Lean installation.
"""

import os
import sys
import types
from datetime import date as dt, timedelta
from unittest.mock import MagicMock

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Make the repo root importable when tests are run from the tests/ directory
# ─────────────────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────────────────────────────────────
# Stubs that mimic the QuantConnect / Lean API surface used by the algorithm
# ─────────────────────────────────────────────────────────────────────────────

class MockRollingWindow:
    """
    Mimics QuantConnect's generic RollingWindow[T].
    Index 0 == most-recent value (same as the real implementation).
    """

    def __class_getitem__(cls, _):
        """Support RollingWindow[float] syntax."""
        return cls

    def __init__(self, size: int):
        self._size = size
        self._data: list = []

    def add(self, value):
        self._data.insert(0, value)
        if len(self._data) > self._size:
            self._data.pop()

    def __getitem__(self, index: int):
        return self._data[index]

    @property
    def count(self) -> int:
        return len(self._data)

    @property
    def is_ready(self) -> bool:
        return len(self._data) >= self._size


class MockQCAlgorithm:
    """Minimal stub of QCAlgorithm with all lifecycle hooks as no-ops."""

    def __init__(self):
        self.schedule = MagicMock()
        self.date_rules = MagicMock()
        self.time_rules = MagicMock()
        self.future_chain_provider = MagicMock()
        self.securities: dict = {}
        self.portfolio = MagicMock()
        self.portfolio.invested = False
        self.is_warming_up = False
        self.time = MagicMock()
        self._logs: list = []

    def set_start_date(self, *a): pass
    def set_end_date(self, *a): pass
    def set_cash(self, *a): pass
    def set_benchmark(self, *a): pass
    def set_warm_up(self, *a): pass
    def set_holdings(self, *a, **kw): pass
    def liquidate(self, *a): pass
    def add_future(self, *a, **kw): return MagicMock()
    def add_future_contract(self, *a): pass

    def log(self, message: str):
        self._logs.append(message)


# ─────────────────────────────────────────────────────────────────────────────
# Build and inject the mock module into sys.modules BEFORE importing the algo
# ─────────────────────────────────────────────────────────────────────────────

_mock_ai = types.ModuleType("AlgorithmImports")
_mock_ai.QCAlgorithm = MockQCAlgorithm
_mock_ai.RollingWindow = MockRollingWindow

_resolution = MagicMock()
_resolution.MINUTE = 1
_mock_ai.Resolution = _resolution

_futures = MagicMock()
_futures.Indices.DOW_30_E_MINI = "YM"
_mock_ai.Futures = _futures

_mock_ai.timedelta = timedelta

# Only the names we explicitly provide will be star-imported
_mock_ai.__all__ = ["QCAlgorithm", "RollingWindow", "Resolution", "Futures", "timedelta"]

sys.modules["AlgorithmImports"] = _mock_ai

# Now that the mock is in place, import the algorithm under test
from QuantConnectLocal import PensiveLightBrownWolf  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Helpers shared across tests
# ─────────────────────────────────────────────────────────────────────────────

def make_algo() -> PensiveLightBrownWolf:
    """Return a fresh algorithm instance with strategy state pre-seeded."""
    algo = PensiveLightBrownWolf()
    algo.ym = MagicMock()
    algo.contract = None
    algo.price_window = MockRollingWindow(100)
    algo.swing_highs = []
    algo.swing_lows = []
    algo.uptrend_slope = None
    algo.uptrend_intercept = None
    algo.downtrend_slope = None
    algo.downtrend_intercept = None
    algo.entry_price = 0
    algo.stop_loss_percent = 0.02
    algo.set_holdings = MagicMock()
    algo.liquidate = MagicMock()
    return algo


def fill_window(algo: PensiveLightBrownWolf, prices: list) -> None:
    """
    Load prices into the rolling window so that prices[0] ends up at index 0
    (i.e. the most-recent slot). We add oldest values first.
    """
    for p in reversed(prices):
        algo.price_window.add(p)


def make_contract(date_value):
    """Create a mock futures contract symbol with an id.date attribute."""
    c = MagicMock()
    c.id.date = date_value
    return c


# ─────────────────────────────────────────────────────────────────────────────
# Price fixture for trendline tests
#
# Layout (index 0 = newest bar in the rolling window):
#
#   i =  5  → price 115  ← swing high #2  (recent)
#   i = 10  → price  90  ← swing low  #2  (recent)
#   i = 15  → price 120  ← swing high #1  (older)
#   i = 20  → price  80  ← swing low  #1  (older)
#
# Expected trendlines after update_trendlines():
#   Downtrend (highs): x1=5,y1=115  x2=15,y2=120  slope=0.5   intercept=112.5
#   Uptrend   (lows):  x1=10,y1=90  x2=20,y2=80   slope=-1.0  intercept=100.0
# ─────────────────────────────────────────────────────────────────────────────
PRICES_WITH_SWINGS = [
    100, 101, 102, 103, 104,   # i=  0- 4  descending approach to recent peak
    115,                        # i=  5    SWING HIGH #2
    108, 105, 102, 100,        # i=  6- 9
    90,                         # i= 10    SWING LOW  #2
    95,  100, 105, 110,        # i= 11-14
    120,                        # i= 15    SWING HIGH #1
    115, 110, 105, 100,        # i= 16-19
    80,                         # i= 20    SWING LOW  #1
    85,   90,  95, 100,        # i= 21-24
    105, 100,  95,  90,  85,   # i= 25-29  (oldest)
]


# ─────────────────────────────────────────────────────────────────────────────
# Tests: initialize()
# ─────────────────────────────────────────────────────────────────────────────

class TestInitialize:

    def _make_fresh(self) -> PensiveLightBrownWolf:
        algo = PensiveLightBrownWolf()
        mock_sub = MagicMock()
        mock_sub.symbol = MagicMock()
        algo.add_future = MagicMock(return_value=mock_sub)
        return algo

    def test_strategy_variables_initialized(self):
        algo = self._make_fresh()
        algo.initialize()

        assert algo.contract is None
        assert isinstance(algo.price_window, MockRollingWindow)
        assert algo.swing_highs == []
        assert algo.swing_lows == []
        assert algo.uptrend_slope is None
        assert algo.uptrend_intercept is None
        assert algo.downtrend_slope is None
        assert algo.downtrend_intercept is None
        assert algo.entry_price == 0
        assert algo.stop_loss_percent == pytest.approx(0.02)

    def test_schedule_registered(self):
        algo = self._make_fresh()
        algo.initialize()
        algo.schedule.on.assert_called_once()

    def test_add_future_called_with_ym_symbol(self):
        algo = self._make_fresh()
        algo.initialize()

        first_arg = algo.add_future.call_args[0][0]
        assert first_arg == "YM"

    def test_filter_applied_to_subscription(self):
        algo = self._make_fresh()
        mock_sub = algo.add_future.return_value
        algo.initialize()
        mock_sub.set_filter.assert_called_once()

    def test_price_window_capacity_is_100(self):
        algo = self._make_fresh()
        algo.initialize()
        assert algo.price_window._size == 100


# ─────────────────────────────────────────────────────────────────────────────
# Tests: update_trendlines()
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateTrendlines:

    def test_skips_when_fewer_than_20_prices(self):
        algo = make_algo()
        fill_window(algo, [100.0] * 15)
        algo.update_trendlines()

        assert algo.downtrend_slope is None
        assert algo.uptrend_slope is None

    def test_detects_two_swing_highs(self):
        algo = make_algo()
        fill_window(algo, PRICES_WITH_SWINGS)
        algo.update_trendlines()

        assert len(algo.swing_highs) == 2
        indices = {h[0] for h in algo.swing_highs}
        assert 5 in indices
        assert 15 in indices

    def test_detects_two_swing_lows(self):
        algo = make_algo()
        fill_window(algo, PRICES_WITH_SWINGS)
        algo.update_trendlines()

        assert len(algo.swing_lows) == 2
        indices = {lo[0] for lo in algo.swing_lows}
        assert 10 in indices
        assert 20 in indices

    def test_swing_high_values_are_correct(self):
        algo = make_algo()
        fill_window(algo, PRICES_WITH_SWINGS)
        algo.update_trendlines()

        values = {h[1] for h in algo.swing_highs}
        assert 115 in values
        assert 120 in values

    def test_swing_low_values_are_correct(self):
        algo = make_algo()
        fill_window(algo, PRICES_WITH_SWINGS)
        algo.update_trendlines()

        values = {lo[1] for lo in algo.swing_lows}
        assert 90 in values
        assert 80 in values

    def test_downtrend_slope(self):
        algo = make_algo()
        fill_window(algo, PRICES_WITH_SWINGS)
        algo.update_trendlines()
        # (120-115) / (15-5) = 0.5
        assert algo.downtrend_slope == pytest.approx(0.5)

    def test_downtrend_intercept(self):
        algo = make_algo()
        fill_window(algo, PRICES_WITH_SWINGS)
        algo.update_trendlines()
        # y2 - slope*x2 = 120 - 0.5*15 = 112.5
        assert algo.downtrend_intercept == pytest.approx(112.5)

    def test_uptrend_slope(self):
        algo = make_algo()
        fill_window(algo, PRICES_WITH_SWINGS)
        algo.update_trendlines()
        # (80-90) / (20-10) = -1.0
        assert algo.uptrend_slope == pytest.approx(-1.0)

    def test_uptrend_intercept(self):
        algo = make_algo()
        fill_window(algo, PRICES_WITH_SWINGS)
        algo.update_trendlines()
        # y2 - slope*x2 = 80 - (-1.0)*20 = 100.0
        assert algo.uptrend_intercept == pytest.approx(100.0)

    def test_no_downtrend_line_with_flat_prices(self):
        algo = make_algo()
        fill_window(algo, [100.0] * 25)
        algo.update_trendlines()

        assert algo.downtrend_slope is None
        assert algo.downtrend_intercept is None

    def test_no_uptrend_line_with_flat_prices(self):
        algo = make_algo()
        fill_window(algo, [100.0] * 25)
        algo.update_trendlines()

        assert algo.uptrend_slope is None
        assert algo.uptrend_intercept is None

    def test_swing_lists_cleared_on_recalculation(self):
        algo = make_algo()
        fill_window(algo, PRICES_WITH_SWINGS)
        algo.update_trendlines()
        first_highs = list(algo.swing_highs)

        algo.update_trendlines()

        assert algo.swing_highs == first_highs  # same input → same result

    def test_trendline_log_messages_emitted(self):
        algo = make_algo()
        fill_window(algo, PRICES_WITH_SWINGS)
        algo.update_trendlines()

        assert any("Downtrend resistance" in m for m in algo._logs)
        assert any("Uptrend support" in m for m in algo._logs)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: on_data()
# ─────────────────────────────────────────────────────────────────────────────

class TestOnData:

    # ── internal helpers ─────────────────────────────────────────────────────

    def _wire_chain(self, algo, contract, price=38000.0):
        """Configure the chain provider and securities for a live contract."""
        algo.future_chain_provider.get_future_contract_list.return_value = [contract]
        mock_sec = MagicMock()
        mock_sec.price = price
        algo.securities[contract] = mock_sec
        algo.contract = contract

    def _make_position(self, is_long=False, is_short=False):
        pos = MagicMock()
        pos.is_long = is_long
        pos.is_short = is_short
        return pos

    # ── warm-up guard ─────────────────────────────────────────────────────────

    def test_skips_entirely_during_warmup(self):
        algo = make_algo()
        algo.is_warming_up = True
        algo.on_data(MagicMock())

        algo.set_holdings.assert_not_called()
        algo.liquidate.assert_not_called()

    # ── chain / contract management ──────────────────────────────────────────

    def test_returns_early_when_chain_empty(self):
        algo = make_algo()
        algo.future_chain_provider.get_future_contract_list.return_value = []
        algo.on_data(MagicMock())

        algo.set_holdings.assert_not_called()

    def test_selects_nearest_expiry_as_front_month(self):
        algo = make_algo()
        near = make_contract(dt(2024, 3, 15))
        far = make_contract(dt(2024, 6, 21))
        self._wire_chain(algo, near, price=38000.0)
        algo.future_chain_provider.get_future_contract_list.return_value = [far, near]

        algo.on_data(MagicMock())

        assert algo.contract is near

    def test_contract_rollover_subscribes_new_contract(self):
        algo = make_algo()
        old_c = make_contract(dt(2024, 3, 15))
        new_c = make_contract(dt(2024, 6, 21))
        algo.contract = old_c
        algo.future_chain_provider.get_future_contract_list.return_value = [new_c]
        algo.add_future_contract = MagicMock()

        algo.on_data(MagicMock())

        assert algo.contract is new_c
        algo.add_future_contract.assert_called_once_with(new_c)

    def test_skips_when_price_is_zero(self):
        algo = make_algo()
        contract = make_contract(dt(2024, 3, 15))
        self._wire_chain(algo, contract, price=0.0)
        algo.on_data(MagicMock())

        algo.set_holdings.assert_not_called()

    # ── price window accumulation ─────────────────────────────────────────────

    def test_price_added_to_rolling_window(self):
        algo = make_algo()
        contract = make_contract(dt(2024, 3, 15))
        self._wire_chain(algo, contract, price=38500.0)

        before = algo.price_window.count
        algo.on_data(MagicMock())

        assert algo.price_window.count == before + 1
        assert algo.price_window[0] == pytest.approx(38500.0)

    # ── bullish breakout entry ────────────────────────────────────────────────

    def test_buy_signal_when_price_above_resistance(self):
        algo = make_algo()
        contract = make_contract(dt(2024, 3, 15))
        algo.downtrend_slope = 0.0
        algo.downtrend_intercept = 38000.0
        self._wire_chain(algo, contract, price=38100.0)

        algo.on_data(MagicMock())

        algo.set_holdings.assert_called_once_with(contract, 0.5)
        assert algo.entry_price == pytest.approx(38100.0)

    def test_no_buy_when_price_equals_resistance(self):
        algo = make_algo()
        contract = make_contract(dt(2024, 3, 15))
        algo.downtrend_slope = 0.0
        algo.downtrend_intercept = 38000.0
        self._wire_chain(algo, contract, price=38000.0)

        algo.on_data(MagicMock())

        algo.set_holdings.assert_not_called()

    def test_no_buy_when_price_below_resistance(self):
        algo = make_algo()
        contract = make_contract(dt(2024, 3, 15))
        algo.downtrend_slope = 0.0
        algo.downtrend_intercept = 38000.0
        self._wire_chain(algo, contract, price=37900.0)

        algo.on_data(MagicMock())

        algo.set_holdings.assert_not_called()

    def test_buy_signal_logs_bullish_breakout(self):
        algo = make_algo()
        contract = make_contract(dt(2024, 3, 15))
        algo.downtrend_slope = 0.0
        algo.downtrend_intercept = 38000.0
        self._wire_chain(algo, contract, price=38100.0)

        algo.on_data(MagicMock())

        assert any("BULLISH BREAKOUT" in m for m in algo._logs)

    # ── bearish breakdown entry ───────────────────────────────────────────────

    def test_short_signal_when_price_below_support(self):
        algo = make_algo()
        contract = make_contract(dt(2024, 3, 15))
        algo.downtrend_slope = None       # no downtrend line → elif branch runs
        algo.uptrend_slope = 0.0
        algo.uptrend_intercept = 38000.0
        self._wire_chain(algo, contract, price=37900.0)

        algo.on_data(MagicMock())

        algo.set_holdings.assert_called_once_with(contract, -0.5)
        assert algo.entry_price == pytest.approx(37900.0)

    def test_no_short_when_price_equals_support(self):
        algo = make_algo()
        contract = make_contract(dt(2024, 3, 15))
        algo.downtrend_slope = None
        algo.uptrend_slope = 0.0
        algo.uptrend_intercept = 38000.0
        self._wire_chain(algo, contract, price=38000.0)

        algo.on_data(MagicMock())

        algo.set_holdings.assert_not_called()

    def test_short_signal_logs_bearish_breakdown(self):
        algo = make_algo()
        contract = make_contract(dt(2024, 3, 15))
        algo.downtrend_slope = None
        algo.uptrend_slope = 0.0
        algo.uptrend_intercept = 38000.0
        self._wire_chain(algo, contract, price=37900.0)

        algo.on_data(MagicMock())

        assert any("BEARISH BREAKDOWN" in m for m in algo._logs)

    # ── no entry when already invested ───────────────────────────────────────

    def test_no_entry_signal_when_already_invested(self):
        algo = make_algo()
        contract = make_contract(dt(2024, 3, 15))
        algo.downtrend_slope = 0.0
        algo.downtrend_intercept = 38000.0
        algo.portfolio.invested = True
        position = self._make_position(is_long=True)
        algo.portfolio.__getitem__ = MagicMock(return_value=position)
        # Price would trigger a buy if not invested
        self._wire_chain(algo, contract, price=38100.0)
        algo.entry_price = 38100.0  # avoid spurious stop-loss trigger

        algo.on_data(MagicMock())

        algo.set_holdings.assert_not_called()

    # ── long stop-loss ────────────────────────────────────────────────────────

    def test_long_stop_loss_triggers_liquidation(self):
        algo = make_algo()
        contract = make_contract(dt(2024, 3, 15))
        algo.entry_price = 38000.0
        algo.portfolio.invested = True
        position = self._make_position(is_long=True)
        algo.portfolio.__getitem__ = MagicMock(return_value=position)
        # 3% drop — exceeds 2% stop
        trigger_price = algo.entry_price * (1 - algo.stop_loss_percent) - 1
        self._wire_chain(algo, contract, price=trigger_price)

        algo.on_data(MagicMock())

        algo.liquidate.assert_called_once_with(contract)

    def test_long_no_liquidation_within_stop_tolerance(self):
        algo = make_algo()
        contract = make_contract(dt(2024, 3, 15))
        algo.entry_price = 38000.0
        algo.portfolio.invested = True
        position = self._make_position(is_long=True)
        algo.portfolio.__getitem__ = MagicMock(return_value=position)
        # Only 1% drop — within 2% stop
        self._wire_chain(algo, contract, price=algo.entry_price * 0.99)

        algo.on_data(MagicMock())

        algo.liquidate.assert_not_called()

    def test_long_stop_loss_logs_message(self):
        algo = make_algo()
        contract = make_contract(dt(2024, 3, 15))
        algo.entry_price = 38000.0
        algo.portfolio.invested = True
        position = self._make_position(is_long=True)
        algo.portfolio.__getitem__ = MagicMock(return_value=position)
        trigger_price = algo.entry_price * (1 - algo.stop_loss_percent) - 1
        self._wire_chain(algo, contract, price=trigger_price)

        algo.on_data(MagicMock())

        assert any("STOP LOSS HIT" in m for m in algo._logs)

    # ── short stop-loss ───────────────────────────────────────────────────────

    def test_short_stop_loss_triggers_liquidation(self):
        algo = make_algo()
        contract = make_contract(dt(2024, 3, 15))
        algo.entry_price = 38000.0
        algo.portfolio.invested = True
        position = self._make_position(is_short=True)
        algo.portfolio.__getitem__ = MagicMock(return_value=position)
        # 3% rise — exceeds 2% stop
        trigger_price = algo.entry_price * (1 + algo.stop_loss_percent) + 1
        self._wire_chain(algo, contract, price=trigger_price)

        algo.on_data(MagicMock())

        algo.liquidate.assert_called_once_with(contract)

    def test_short_no_liquidation_within_stop_tolerance(self):
        algo = make_algo()
        contract = make_contract(dt(2024, 3, 15))
        algo.entry_price = 38000.0
        algo.portfolio.invested = True
        position = self._make_position(is_short=True)
        algo.portfolio.__getitem__ = MagicMock(return_value=position)
        # Only 1% rise — within 2% stop
        self._wire_chain(algo, contract, price=algo.entry_price * 1.01)

        algo.on_data(MagicMock())

        algo.liquidate.assert_not_called()
