"""Parametrized scenario tests for TradingAlgo.

Each scenario is an ``AlgoConfig`` object registered in the ``SCENARIOS``
list at the bottom of this module.  Adding a new test angle configuration
requires only a new ``pytest.param`` entry there — no changes to any
algorithm code.

Test classes
------------
TestScenarioSmoke
    Confirms every scenario completes without error and returns a
    well-formed DataFrame with the expected columns, valid positions and
    finite P/L.

TestSignalTiming
    Asserts that no signals fire inside the mandatory 8-minute warm-up
    window, regardless of scenario.

TestSignalDirection
    Verifies that a consistent uptrend produces at least as many BUY
    signals as SELL signals, and vice-versa for a downtrend.

TestAngleParameterIsolation
    Targeted checks that changing a single angle parameter produces an
    independently runnable result and, for the proximity check, that a
    wider window suppresses at least as many signals as a narrow one.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest
import pytz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from TradingAlgoFast import AlgoConfig, run_trading_algo_fast as run_trading_algo

# ---------------------------------------------------------------------------
# Constants shared across all tests
# ---------------------------------------------------------------------------

TARGET_DATE = "2026-01-13"
START_TIME = "09:30"
END_TIME = "10:30"

_EST = pytz.timezone("US/Eastern")

# ---------------------------------------------------------------------------
# Scenario registry
#
# To add a new scenario:
#   1. Append a pytest.param() with the desired AlgoConfig.
#   2. Give it a descriptive id= string.
#   3. Optionally comment out the previous param if you want to disable it
#      while keeping it for reference.
# ---------------------------------------------------------------------------

SCENARIOS = [
    # -- Baseline (original hardcoded values) --------------------------------
    pytest.param(
        AlgoConfig(
            orange_angle=2.5,
            yellow_angle=2.5,
            purple_angle=45.0,
            blue_angle=45.0,
            steep_angle_threshold=45.0,
            proximity_points=50.0,
        ),
        id="baseline_45-45",
    ),
    # -- Purple steeper, blue unchanged  ------------------------------------
    pytest.param(
        AlgoConfig(
            orange_angle=2.5,
            yellow_angle=2.5,
            purple_angle=65.0,
            blue_angle=45.0,
            steep_angle_threshold=65.0,
            proximity_points=50.0,
        ),
        id="purple_65-blue_45",
    ),
    # -- Blue steeper, purple unchanged  ------------------------------------
    pytest.param(
        AlgoConfig(
            orange_angle=2.5,
            yellow_angle=2.5,
            purple_angle=45.0,
            blue_angle=65.0,
            steep_angle_threshold=65.0,
            proximity_points=50.0,
        ),
        id="purple_45-blue_65",
    ),
    # -- Both rays steeper  -------------------------------------------------
    pytest.param(
        AlgoConfig(
            orange_angle=2.5,
            yellow_angle=2.5,
            purple_angle=65.0,
            blue_angle=65.0,
            steep_angle_threshold=65.0,
            proximity_points=50.0,
        ),
        id="purple_65-blue_65",
    ),
    # -- Shallower orange/yellow base rays (5 deg) --------------------------
    pytest.param(
        AlgoConfig(
            orange_angle=5.0,
            yellow_angle=5.0,
            purple_angle=45.0,
            blue_angle=45.0,
            steep_angle_threshold=45.0,
            proximity_points=50.0,
        ),
        id="shallow_orange_yellow_5deg",
    ),
    # -- Very shallow purple/blue (30 deg) ----------------------------------
    pytest.param(
        AlgoConfig(
            orange_angle=2.5,
            yellow_angle=2.5,
            purple_angle=30.0,
            blue_angle=30.0,
            steep_angle_threshold=30.0,
            proximity_points=50.0,
        ),
        id="shallow_purple_blue_30deg",
    ),
    # -- Wide proximity suppression window (100 pts) ------------------------
    pytest.param(
        AlgoConfig(
            orange_angle=2.5,
            yellow_angle=2.5,
            purple_angle=45.0,
            blue_angle=45.0,
            steep_angle_threshold=45.0,
            proximity_points=100.0,
        ),
        id="wide_proximity_100pts",
    ),
    # -- Narrow proximity suppression window (10 pts) -----------------------
    pytest.param(
        AlgoConfig(
            orange_angle=2.5,
            yellow_angle=2.5,
            purple_angle=45.0,
            blue_angle=45.0,
            steep_angle_threshold=45.0,
            proximity_points=10.0,
        ),
        id="narrow_proximity_10pts",
    ),
    # -----------------------------------------------------------------------
    # Add new scenarios below.  Comment out old ones to disable without
    # losing the parameter definition.
    # -----------------------------------------------------------------------
    ## pytest.param(
    ##     AlgoConfig(
    ##         orange_angle=2.5,
    ##         yellow_angle=2.5,
    ##         purple_angle=80.0,
    ##         blue_angle=80.0,
    ##         steep_angle_threshold=80.0,
    ##         proximity_points=50.0,
    ##     ),
    ##     id="steep_80deg",
    ## ),
]


# ---------------------------------------------------------------------------
# Data fixtures
# ---------------------------------------------------------------------------


def _make_intraday(seed: int, drift: float = 0.0) -> pd.DataFrame:
    """Return 60 bars of synthetic 1-minute OHLCV data.

    Parameters
    ----------
    seed:
        Random seed for reproducibility.
    drift:
        Price change per bar.  Positive values produce an uptrend;
        negative values a downtrend; zero produces a noisy flat session.
    """
    rng = np.random.default_rng(seed=seed)
    start = pd.Timestamp(f"{TARGET_DATE} {START_TIME}:00", tz=_EST)
    index = pd.date_range(start=start, periods=60, freq="1min", tz=_EST)

    close = 44_000.0 + np.arange(60) * drift + np.cumsum(rng.normal(0, 4, size=60))
    high = close + rng.uniform(2, 15, size=60)
    low = close - rng.uniform(2, 15, size=60)
    open_ = close + rng.normal(0, 3, size=60)

    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": rng.integers(100, 1000, size=60),
        },
        index=index,
    )


@pytest.fixture
def intraday_data() -> pd.DataFrame:
    """Flat/noisy 60-bar session."""
    return _make_intraday(seed=42, drift=0.0)


@pytest.fixture
def trending_up_data() -> pd.DataFrame:
    """Consistent uptrend (+3 pts/bar) to favour BUY signals."""
    return _make_intraday(seed=7, drift=3.0)


@pytest.fixture
def trending_down_data() -> pd.DataFrame:
    """Consistent downtrend (-3 pts/bar) to favour SELL signals."""
    return _make_intraday(seed=13, drift=-3.0)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_REQUIRED_COLUMNS = (
    "signal",
    "position",
    "pl",
    "orange_ray",
    "yellow_ray",
    "purple_ray",
    "blue_ray",
)

_CUTOFF = pd.Timestamp(f"{TARGET_DATE} {START_TIME}:00", tz=_EST) + pd.Timedelta(minutes=8)


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestScenarioSmoke:
    """Every scenario must complete without error and return a valid frame."""

    @pytest.mark.parametrize("config", SCENARIOS)
    def test_returns_dataframe(self, intraday_data, config):
        result = run_trading_algo(intraday_data, TARGET_DATE, START_TIME, END_TIME, config=config)
        assert isinstance(result, pd.DataFrame)
        assert not result.empty

    @pytest.mark.parametrize("config", SCENARIOS)
    def test_required_columns_present(self, intraday_data, config):
        result = run_trading_algo(intraday_data, TARGET_DATE, START_TIME, END_TIME, config=config)
        for col in _REQUIRED_COLUMNS:
            assert col in result.columns, f"Scenario '{config}': missing column '{col}'"

    @pytest.mark.parametrize("config", SCENARIOS)
    def test_pl_is_finite(self, intraday_data, config):
        result = run_trading_algo(intraday_data, TARGET_DATE, START_TIME, END_TIME, config=config)
        assert np.isfinite(result["pl"]).all(), "Non-finite P/L value detected"

    @pytest.mark.parametrize("config", SCENARIOS)
    def test_position_values_valid(self, intraday_data, config):
        result = run_trading_algo(intraday_data, TARGET_DATE, START_TIME, END_TIME, config=config)
        assert result["position"].isin({"flat", "long", "short"}).all()

    @pytest.mark.parametrize("config", SCENARIOS)
    def test_ray_prices_are_finite(self, intraday_data, config):
        result = run_trading_algo(intraday_data, TARGET_DATE, START_TIME, END_TIME, config=config)
        for col in ("orange_ray", "yellow_ray", "purple_ray", "blue_ray"):
            assert np.isfinite(result[col]).all(), f"Non-finite values in '{col}'"


class TestSignalTiming:
    """No signal should fire inside the mandatory 8-minute warm-up window."""

    @pytest.mark.parametrize("config", SCENARIOS)
    def test_no_signals_before_cutoff(self, intraday_data, config):
        result = run_trading_algo(intraday_data, TARGET_DATE, START_TIME, END_TIME, config=config)
        early = result.loc[result.index < _CUTOFF, "signal"]
        assert (early == "").all(), (
            f"Signal fired before the 8-minute cutoff: {early[early != ''].index.tolist()}"
        )

    @pytest.mark.parametrize("config", SCENARIOS)
    def test_no_signals_before_cutoff_uptrend(self, trending_up_data, config):
        result = run_trading_algo(trending_up_data, TARGET_DATE, START_TIME, END_TIME, config=config)
        early = result.loc[result.index < _CUTOFF, "signal"]
        assert (early == "").all()

    @pytest.mark.parametrize("config", SCENARIOS)
    def test_no_signals_before_cutoff_downtrend(self, trending_down_data, config):
        result = run_trading_algo(trending_down_data, TARGET_DATE, START_TIME, END_TIME, config=config)
        early = result.loc[result.index < _CUTOFF, "signal"]
        assert (early == "").all()


class TestSignalDirection:
    """Verify that trend-aligned data produces the expected signal bias."""

    @pytest.mark.parametrize("config", SCENARIOS)
    def test_trending_up_has_buy_bias(self, trending_up_data, config):
        result = run_trading_algo(trending_up_data, TARGET_DATE, START_TIME, END_TIME, config=config)
        buy_count = (result["signal"] == "BUY").sum()
        sell_count = (result["signal"] == "SELL").sum()
        if buy_count + sell_count > 0:
            assert buy_count >= sell_count, (
                f"Downtrend bias in uptrend data: {buy_count} buys vs {sell_count} sells"
            )

    @pytest.mark.parametrize("config", SCENARIOS)
    def test_trending_down_has_sell_bias(self, trending_down_data, config):
        result = run_trading_algo(trending_down_data, TARGET_DATE, START_TIME, END_TIME, config=config)
        buy_count = (result["signal"] == "BUY").sum()
        sell_count = (result["signal"] == "SELL").sum()
        if buy_count + sell_count > 0:
            assert sell_count >= buy_count, (
                f"Uptrend bias in downtrend data: {sell_count} sells vs {buy_count} buys"
            )


class TestAngleParameterIsolation:
    """Verify that changing a single angle parameter produces independent results."""

    def test_different_purple_angles_run_independently(self, intraday_data):
        config_a = AlgoConfig(purple_angle=45.0, steep_angle_threshold=45.0)
        config_b = AlgoConfig(purple_angle=65.0, steep_angle_threshold=65.0)
        result_a = run_trading_algo(intraday_data, TARGET_DATE, START_TIME, END_TIME, config=config_a)
        result_b = run_trading_algo(intraday_data, TARGET_DATE, START_TIME, END_TIME, config=config_b)
        assert isinstance(result_a, pd.DataFrame)
        assert isinstance(result_b, pd.DataFrame)

    def test_different_blue_angles_run_independently(self, intraday_data):
        config_a = AlgoConfig(blue_angle=45.0, steep_angle_threshold=45.0)
        config_b = AlgoConfig(blue_angle=65.0, steep_angle_threshold=65.0)
        result_a = run_trading_algo(intraday_data, TARGET_DATE, START_TIME, END_TIME, config=config_a)
        result_b = run_trading_algo(intraday_data, TARGET_DATE, START_TIME, END_TIME, config=config_b)
        assert isinstance(result_a, pd.DataFrame)
        assert isinstance(result_b, pd.DataFrame)

    def test_wider_proximity_suppresses_at_least_as_many_signals(self, intraday_data):
        """A wider proximity window should not generate *more* signals than a narrower one."""
        config_narrow = AlgoConfig(proximity_points=10.0)
        config_wide = AlgoConfig(proximity_points=200.0)
        result_narrow = run_trading_algo(intraday_data, TARGET_DATE, START_TIME, END_TIME, config=config_narrow)
        result_wide = run_trading_algo(intraday_data, TARGET_DATE, START_TIME, END_TIME, config=config_wide)
        signals_narrow = (result_narrow["signal"] != "").sum()
        signals_wide = (result_wide["signal"] != "").sum()
        assert signals_wide <= signals_narrow, (
            f"Wide proximity produced more signals ({signals_wide}) than narrow ({signals_narrow})"
        )

    def test_default_config_matches_explicit_baseline(self, intraday_data):
        """AlgoConfig() with no arguments must equal the explicit baseline scenario."""
        result_default = run_trading_algo(intraday_data, TARGET_DATE, START_TIME, END_TIME)
        result_explicit = run_trading_algo(
            intraday_data,
            TARGET_DATE,
            START_TIME,
            END_TIME,
            config=AlgoConfig(
                orange_angle=2.5,
                yellow_angle=2.5,
                purple_angle=45.0,
                blue_angle=45.0,
                steep_angle_threshold=45.0,
                proximity_points=50.0,
            ),
        )
        pd.testing.assert_frame_equal(result_default, result_explicit)
