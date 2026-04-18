"""TradingAlgo

Headless trading algorithm core for YM intraday data.

This module can run independently of the plotting layer; it does not
require `ChartPlotter`. The ray and signal logic is copied from the
interactive implementation in `plotFigure.py` so the behaviour remains
consistent without moving any code out of that file.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import pytz

from TrendLineAutomation import fit_trendlines_high_low


@dataclass
class AlgoConfig:
    """Parameters that define a trading algorithm scenario.

    All angles are expressed as positive degree magnitudes.  Orange and
    purple rays descend (negative slope); yellow and blue rays ascend
    (positive).  ``steep_angle_threshold`` is the maximum display angle
    below which a purple or blue ray crossing can trigger a signal — rays
    steeper than this value are suppressed as noise.  ``proximity_points``
    is the price-distance window used to suppress a steep-ray crossing when
    the close is already near the shallow orange/yellow ray.
    """

    orange_angle: float = 2.5
    yellow_angle: float = 2.5
    purple_angle: float = 45.0
    blue_angle: float = 45.0
    steep_angle_threshold: float = 45.0
    proximity_points: float = 50.0
    warmup_minutes: Optional[int] = None
    min_reversal_minutes: int = 10  # minimum minutes before allowing a position reversal
    max_loss_per_trade: float = 0.0  # hard stop-loss per trade in points (0 = disabled)
    confirmation_bars: int = 0  # 0=enter on first cross, 1=require next bar also beyond ray
    spike_profit_pts: float = 100.0  # exit if unrealized profit >= this within spike_profit_bars of entry
    spike_profit_bars: int = 5       # number of bars after entry to check for spike profit (0 = disabled)
    wm_shield_distance: float = 12.0  # suppress exit if water mark cluster within this many pts (0 = disabled)
    wm_tolerance: float = 12.0        # pts tolerance for clustering bar lows/highs
    wm_min_touches: int = 4           # minimum bars touching a level to form a cluster
    wm_min_span: float = 15.0         # minimum minutes the touches must span
    wm_lookback: int = 30             # bars to look back for clusters


class Ray:
    """Represents a ray line with an angle starting from a specific point."""

    def __init__(self, angle_degrees: float, start_price: float, start_time, color: str, label: str):
        self.angle_degrees = angle_degrees
        self.start_price = start_price
        self.start_time = start_time
        self.color = color
        self.label = label
        self.adjusted_slope: Optional[float] = None

    def calculate_slope(self, x_per_unit: float, y_per_unit: float) -> float:
        """Calculate slope in data units based on angle and aspect ratio."""
        if x_per_unit == 0:
            return 0.0
        angle_rad = np.deg2rad(self.angle_degrees)
        tan_angle = np.tan(angle_rad)
        return float(tan_angle * (y_per_unit / x_per_unit))

    def get_price_at_time(self, target_time, slope: float) -> float:
        """Calculate ray price at a specific time."""
        start_time_num = mdates.date2num(self.start_time)
        target_time_num = mdates.date2num(target_time)
        time_diff = target_time_num - start_time_num
        if time_diff <= 0:
            return float(self.start_price)
        return float(self.start_price + slope * time_diff)

    def update_for_crossover(self, new_price: float, new_time, slope: float) -> float:
        """Adjust ray to pass through a new point if crossed."""
        start_time_num = mdates.date2num(self.start_time)
        new_time_num = mdates.date2num(new_time)
        time_diff = new_time_num - start_time_num
        if time_diff > 0:
            return float((new_price - self.start_price) / time_diff)
        return float(slope)


class RayManager:
    """Manages all ray calculations and updates (headless version)."""

    def __init__(self, data: pd.DataFrame, config: Optional[AlgoConfig] = None):
        self.data = data
        self.config = config or AlgoConfig()
        self.orange_ray: Optional[Ray] = None
        self.yellow_ray: Optional[Ray] = None
        self.purple_ray: Optional[Ray] = None
        self.blue_ray: Optional[Ray] = None
        self.dark_purple_ray: Optional[Ray] = None
        self.magenta_ray: Optional[Ray] = None   # local swing high ray
        self.lime_ray: Optional[Ray] = None      # local swing low ray
        self.purple_intersections = 0
        self.purple_anchor_time = None
        self.blue_anchor_time = None
        self.purple_anchor_price: Optional[float] = None
        self.blue_anchor_price: Optional[float] = None
        self.magenta_anchor_time = None
        self.magenta_anchor_price: Optional[float] = None
        self.lime_anchor_time = None
        self.lime_anchor_price: Optional[float] = None
        self._magenta_slope_frozen: bool = False
        self._lime_slope_frozen: bool = False

    def initialize_rays(self, current_data: pd.DataFrame, x_per_unit: float, y_per_unit: float) -> None:
        """Initialize all rays from current data (first bar)."""
        if current_data.empty:
            return
        first_idx = current_data.index[0]
        # Use shallower base angles to match the latest interactive behaviour.
        _oa = self.config.orange_angle
        _ya = self.config.yellow_angle
        _pa = self.config.purple_angle
        _ba = self.config.blue_angle
        self.orange_ray = Ray(-_oa, float(current_data["High"].iloc[0]), first_idx, "orange", f"Max Ray (-{_oa})")
        self.yellow_ray = Ray(_ya, float(current_data["Low"].iloc[0]), first_idx, "yellow", f"Min Ray (+{_ya})")
        self.purple_ray = Ray(-_pa, float(current_data["High"].iloc[0]), first_idx, "darkviolet", f"Max Ray (-{_pa})")
        self.blue_ray = Ray(_ba, float(current_data["Low"].iloc[0]), first_idx, "blue", f"Min Ray (+{_ba})")
        self.dark_purple_ray = None
        self.purple_intersections = 0

    def update_all_rays(self, current_data: pd.DataFrame, x_per_unit: float, y_per_unit: float) -> None:
        """Update all rays (orange, yellow, purple, blue) for crossovers."""
        if (
            self.orange_ray is None
            or self.yellow_ray is None
            or self.purple_ray is None
            or self.blue_ray is None
        ):
            return

        if len(current_data) > 0 and current_data.index[0] == self.data.index[0]:
            if len(current_data) == 1 or self.orange_ray.start_time != current_data.index[0]:
                self.orange_ray.start_price = float(current_data["High"].iloc[0])
                self.orange_ray.start_time = current_data.index[0]
                self.orange_ray.adjusted_slope = None
            if len(current_data) == 1 or self.yellow_ray.start_time != current_data.index[0]:
                self.yellow_ray.start_price = float(current_data["Low"].iloc[0])
                self.yellow_ray.start_time = current_data.index[0]
                self.yellow_ray.adjusted_slope = None

        orange_slope = self.orange_ray.calculate_slope(x_per_unit, y_per_unit)
        yellow_slope = self.yellow_ray.calculate_slope(x_per_unit, y_per_unit)
        purple_slope = self.purple_ray.calculate_slope(x_per_unit, y_per_unit)
        blue_slope = self.blue_ray.calculate_slope(x_per_unit, y_per_unit)

        # Orange ray: anchors at the highest high seen, descends at fixed angle.
        # Only re-anchors when a new high exceeds the current anchor — never adjusts slope mid-ray.
        for i in range(1, len(current_data)):
            current_high = float(current_data["High"].iloc[i])
            current_idx = current_data.index[i]
            if current_high > self.orange_ray.start_price:
                self.orange_ray.start_price = current_high
                self.orange_ray.start_time = current_idx
                orange_slope = self.orange_ray.calculate_slope(x_per_unit, y_per_unit)
        self.orange_ray.adjusted_slope = orange_slope

        # Yellow ray: anchors at the lowest low seen, ascends at fixed angle.
        # Only re-anchors when a new low is below the current anchor.
        for i in range(1, len(current_data)):
            current_low = float(current_data["Low"].iloc[i])
            current_idx = current_data.index[i]
            if current_low < self.yellow_ray.start_price:
                self.yellow_ray.start_price = current_low
                self.yellow_ray.start_time = current_idx
                yellow_slope = self.yellow_ray.calculate_slope(x_per_unit, y_per_unit)
        self.yellow_ray.adjusted_slope = yellow_slope

        # Purple/blue trendlines using TrendLineAutomation
        if len(current_data) >= 2:
            max_high = float(current_data["High"].max())
            last_max_time = current_data[current_data["High"] == max_high].index[-1]
            min_low = float(current_data["Low"].min())
            last_min_time = current_data[current_data["Low"] == min_low].index[-1]

            if self.purple_anchor_time is None:
                self.purple_anchor_time = last_max_time
                self.purple_anchor_price = max_high
            elif max_high > float(self.purple_anchor_price):
                self.purple_anchor_time = last_max_time
                self.purple_anchor_price = max_high

            if self.blue_anchor_time is None:
                self.blue_anchor_time = last_min_time
                self.blue_anchor_price = min_low
            elif min_low < float(self.blue_anchor_price):
                self.blue_anchor_time = last_min_time
                self.blue_anchor_price = min_low

            window_data_purple = current_data.loc[self.purple_anchor_time :]
            window_data_blue = current_data.loc[self.blue_anchor_time :]
            if len(window_data_purple) < 2 or len(window_data_blue) < 2:
                return

            if self.purple_ray is None:
                self.purple_ray = Ray(-45.0, float(self.purple_anchor_price), self.purple_anchor_time, "darkviolet", "Max Ray (-45)")
            self.purple_ray.start_price = float(self.purple_anchor_price)
            self.purple_ray.start_time = self.purple_anchor_time

            if self.blue_ray is None:
                self.blue_ray = Ray(45.0, float(self.blue_anchor_price), self.blue_anchor_time, "blue", "Min Ray (+45)")
            self.blue_ray.start_price = float(self.blue_anchor_price)
            self.blue_ray.start_time = self.blue_anchor_time

            support_coefs, _ = fit_trendlines_high_low(
                window_data_blue["High"].to_numpy(),
                window_data_blue["Low"].to_numpy(),
                window_data_blue["Close"].to_numpy(),
            )
            _, resist_coefs = fit_trendlines_high_low(
                window_data_purple["High"].to_numpy(),
                window_data_purple["Low"].to_numpy(),
                window_data_purple["Close"].to_numpy(),
            )

            support_slope_idx, support_intercept = support_coefs
            resist_slope_idx, resist_intercept = resist_coefs

            time_step_days_blue = mdates.date2num(window_data_blue.index[1]) - mdates.date2num(window_data_blue.index[0])
            time_step_days_purple = mdates.date2num(window_data_purple.index[1]) - mdates.date2num(window_data_purple.index[0])
            if time_step_days_blue == 0:
                time_step_days_blue = 1.0
            if time_step_days_purple == 0:
                time_step_days_purple = 1.0

            support_slope_time = support_slope_idx / time_step_days_blue
            resist_slope_time = resist_slope_idx / time_step_days_purple

            if self.purple_ray is None:
                self.purple_ray = Ray(-45.0, float(resist_intercept), window_data_purple.index[0], "darkviolet", "Max Ray (-45)")
            self.purple_ray.start_price = float(resist_intercept)
            self.purple_ray.start_time = window_data_purple.index[0]
            self.purple_ray.adjusted_slope = float(resist_slope_time)

            if self.blue_ray is None:
                self.blue_ray = Ray(45.0, float(support_intercept), window_data_blue.index[0], "blue", "Min Ray (+45)")
            self.blue_ray.start_price = float(support_intercept)
            self.blue_ray.start_time = window_data_blue.index[0]
            self.blue_ray.adjusted_slope = float(support_slope_time)

        # --- Magenta ray: local swing high (50+ pt above neighbours) ---
        # --- Lime ray:    local swing low  (50+ pt below neighbours)  ---
        SWING_THRESHOLD = 50.0
        if len(current_data) >= 3:
            # Scan for swing highs/lows — need at least 1 bar on each side.
            for j in range(1, len(current_data) - 1):
                h     = float(current_data["High"].iloc[j])
                h_prev = float(current_data["High"].iloc[j - 1])
                h_next = float(current_data["High"].iloc[j + 1])
                if h - h_prev >= SWING_THRESHOLD and h - h_next >= SWING_THRESHOLD:
                    # Valid swing high — update magenta anchor if higher.
                    if self.magenta_anchor_price is None or h > float(self.magenta_anchor_price):
                        self.magenta_anchor_time  = current_data.index[j]
                        self.magenta_anchor_price = h
                        self._magenta_slope_frozen = False

                l      = float(current_data["Low"].iloc[j])
                l_prev = float(current_data["Low"].iloc[j - 1])
                l_next = float(current_data["Low"].iloc[j + 1])
                if l_prev - l >= SWING_THRESHOLD and l_next - l >= SWING_THRESHOLD:
                    # Valid swing low — update lime anchor if lower.
                    if self.lime_anchor_price is None or l < float(self.lime_anchor_price):
                        self.lime_anchor_time  = current_data.index[j]
                        self.lime_anchor_price = l
                        self._lime_slope_frozen = False

            # Build magenta ray from swing anchor through most recent lower high.
            if self.magenta_anchor_time is not None and not self._magenta_slope_frozen:
                after = current_data.loc[self.magenta_anchor_time:]
                candidates = after[(after["High"] < float(self.magenta_anchor_price)) &
                                   (after.index != self.magenta_anchor_time)]
                if not candidates.empty:
                    best_idx = candidates["High"].idxmax()
                    t0 = mdates.date2num(self.magenta_anchor_time)
                    t1 = mdates.date2num(best_idx)
                    if t1 != t0:
                        slope = (float(candidates.loc[best_idx, "High"]) - float(self.magenta_anchor_price)) / (t1 - t0)
                        if self.magenta_ray is None:
                            self.magenta_ray = Ray(-45.0, float(self.magenta_anchor_price), self.magenta_anchor_time, "magenta", "Swing High Ray")
                        self.magenta_ray.start_price = float(self.magenta_anchor_price)
                        self.magenta_ray.start_time  = self.magenta_anchor_time
                        self.magenta_ray.adjusted_slope = float(slope)
                        self._magenta_slope_frozen = True

            # Build lime ray from swing anchor through most recent higher low.
            if self.lime_anchor_time is not None and not self._lime_slope_frozen:
                after = current_data.loc[self.lime_anchor_time:]
                candidates = after[(after["Low"] > float(self.lime_anchor_price)) &
                                   (after.index != self.lime_anchor_time)]
                if not candidates.empty:
                    best_idx = candidates["Low"].idxmin()
                    t0 = mdates.date2num(self.lime_anchor_time)
                    t1 = mdates.date2num(best_idx)
                    if t1 != t0:
                        slope = (float(candidates.loc[best_idx, "Low"]) - float(self.lime_anchor_price)) / (t1 - t0)
                        if self.lime_ray is None:
                            self.lime_ray = Ray(45.0, float(self.lime_anchor_price), self.lime_anchor_time, "lime", "Swing Low Ray")
                        self.lime_ray.start_price = float(self.lime_anchor_price)
                        self.lime_ray.start_time  = self.lime_anchor_time
                        self.lime_ray.adjusted_slope = float(slope)
                        self._lime_slope_frozen = True


def _display_angle_from_slope(slope: float, x_per_unit: float = 1.0, y_per_unit: float = 1.0) -> float:
    """Return the visual angle in degrees of a ray given its slope.

    In this headless context we treat x/y scales as 1:1, so this reduces
    to the arctangent of the slope magnitude.
    """

    return float(abs(np.rad2deg(np.arctan(abs(slope) * x_per_unit / y_per_unit))))


def _build_signals_frame(
    data: pd.DataFrame,
    buy_signals: Dict[pd.Timestamp, float],
    sell_signals: Dict[pd.Timestamp, float],
    trading_halted: bool,
    halt_time,
    liquidation_timestamps: Optional[set] = None,
) -> pd.DataFrame:
    """Construct a per-minute DataFrame with signals and cumulative P/L."""

    df = data.copy()
    liq_ts = liquidation_timestamps or set()

    df["signal"] = ""
    df["buy_price"] = pd.NA
    df["sell_price"] = pd.NA
    df["is_liquidation"] = False

    for ts, price in buy_signals.items():
        if ts in df.index:
            df.at[ts, "signal"] = "BUY"
            df.at[ts, "buy_price"] = float(price)
            if ts in liq_ts:
                df.at[ts, "is_liquidation"] = True

    for ts, price in sell_signals.items():
        if ts in df.index:
            df.at[ts, "signal"] = "SELL"
            df.at[ts, "sell_price"] = float(price)
            if ts in liq_ts:
                df.at[ts, "is_liquidation"] = True

    position = "flat"
    entry_price: Optional[float] = None
    cumulative_realized_pl: float = 0.0

    positions = []
    pls = []

    for ts in df.index:
        if trading_halted and halt_time is not None and ts > halt_time:
            # After halt, keep position flat and P/L constant.
            positions.append("flat")
            pls.append(cumulative_realized_pl)
            continue

        is_buy = ts in buy_signals
        is_sell = ts in sell_signals
        is_liq = ts in liq_ts

        if is_buy:
            buy_price = float(buy_signals[ts])
            if position == "short" and entry_price is not None:
                cumulative_realized_pl += entry_price - buy_price
            if is_liq:
                # Liquidation: close short, go flat (do not open long).
                position = "flat"
                entry_price = None
            else:
                position = "long"
                entry_price = buy_price

        if is_sell:
            sell_price = float(sell_signals[ts])
            if position == "long" and entry_price is not None:
                cumulative_realized_pl += sell_price - entry_price
            if is_liq:
                # Liquidation: close long, go flat (do not open short).
                position = "flat"
                entry_price = None
            else:
                position = "short"
                entry_price = sell_price

        current_close = float(df.loc[ts, "Close"])
        unrealized = 0.0
        if position == "long" and entry_price is not None:
            unrealized = current_close - entry_price
        elif position == "short" and entry_price is not None:
            unrealized = entry_price - current_close

        total_pl = cumulative_realized_pl + unrealized
        positions.append(position)
        pls.append(total_pl)

    df["position"] = positions
    df["pl"] = pls

    return df


def _find_wm_clusters(values, times, tolerance, min_touches, min_span_minutes):
    """Find price clusters where multiple bar lows/highs land within tolerance pts.
    Returns list of (level, touch_count) for clusters spanning min_span_minutes."""
    if len(values) < min_touches:
        return []
    indexed = sorted(zip(values, times), key=lambda x: x[0])
    clusters = []
    used = set()
    for i in range(len(indexed)):
        if i in used:
            continue
        base = indexed[i][0]
        group = [(indexed[i][0], indexed[i][1])]
        used.add(i)
        for j in range(i + 1, len(indexed)):
            if j in used:
                continue
            if abs(indexed[j][0] - base) <= tolerance:
                group.append((indexed[j][0], indexed[j][1]))
                used.add(j)
            elif indexed[j][0] - base > tolerance:
                break
        if len(group) >= min_touches:
            touch_times = sorted([g[1] for g in group])
            span = (touch_times[-1] - touch_times[0]).total_seconds() / 60
            if span >= min_span_minutes:
                clusters.append((float(np.mean([g[0] for g in group])), len(group)))
    return clusters


def run_trading_algo(
    data: pd.DataFrame,
    target_date: str,
    start_time: str = "09:30",
    end_time: str = "10:00",
    config: Optional[AlgoConfig] = None,
) -> pd.DataFrame:
    """Run the trading algorithm headlessly for a single day's data.

    This function mirrors the ray/signal logic used by the interactive
    plotter but operates purely on the DataFrame, returning an enriched
    per-minute DataFrame with signals and cumulative P/L.
    """

    if data is None or data.empty:
        raise ValueError("run_trading_algo expected non-empty intraday data")

    full_data = data.copy()

    # Ensure timezone-awareness (US/Eastern) to match the interactive code.
    est = pytz.timezone("US/Eastern")
    try:
        if full_data.index.tz is None:
            full_data.index = pd.to_datetime(full_data.index, errors="coerce")
            full_data.index = full_data.index.tz_localize(est)
        else:
            full_data.index = pd.to_datetime(full_data.index).tz_convert(est)
    except Exception:
        pass

    # Resolve config early so warmup_minutes is available for the cutoff.
    cfg = config or AlgoConfig()

    # Cutoff: when warmup_minutes is set, trading begins that many minutes
    # after the first bar in the dataset (any-time-of-day).  Otherwise fall
    # back to the fixed 8-minute offset from session start (legacy behaviour).
    if cfg.warmup_minutes is not None:
        cutoff_time = full_data.index[0] + pd.Timedelta(minutes=cfg.warmup_minutes)
    else:
        cutoff_time = (
            pd.Timestamp(f"{target_date} {start_time}:00", tz=est)
            + pd.Timedelta(minutes=8)
        )

    # Compute an aspect ratio that matches the interactive ChartPlotter so
    # that angle-based filters (e.g. the 65° cutoff on purple/blue rays)
    # produce the same results as the live chart.
    #
    # ChartPlotter uses figsize=(16, 9) with:
    #   subplots_adjust(right=0.85)
    #   subplot2grid((10, 1), (0, 0), rowspan=9)
    # giving approximate axes fractions:
    #   width  = 0.85 - 0.125 = 0.725  (right - left default)
    #   height = 0.88 - 0.11  = 0.770  (top - bottom defaults)
    # Compute aspect ratio using a fixed 75-minute rolling window so that
    # visual angles in the algo match what you see on the live chart.
    # This means 45° in the algo = 45° on screen regardless of session length.
    _fig_w = 16.0
    _fig_h = 9.0
    _ax_w_in = _fig_w * (0.85 - 0.125)   # ≈ 11.6 inches
    _ax_h_in = _fig_h * (0.88 - 0.11)    # ≈ 6.93 inches

    _WINDOW_MINUTES = 75
    _x_range = _WINDOW_MINUTES / (24 * 60)  # 75 mins as fraction of a day

    _y_range = (
        float(full_data["High"].max()) + 20.0
        - (float(full_data["Low"].min()) - 20.0)
    )

    x_per_unit = _x_range / _ax_w_in
    y_per_unit = _y_range / _ax_h_in

    # Initialize ray manager and per-minute steep rays.
    rm = RayManager(full_data, config=cfg)

    if rm.orange_ray is None:
        rm.initialize_rays(full_data, x_per_unit, y_per_unit)

    if full_data.empty:
        return full_data

    minute_purple_ray = Ray(-cfg.purple_angle, float(full_data["High"].iloc[0]), full_data.index[0], "darkviolet", f"Max Ray (-{cfg.purple_angle})")
    minute_blue_ray = Ray(cfg.blue_angle, float(full_data["Low"].iloc[0]), full_data.index[0], "blue", f"Min Ray (+{cfg.blue_angle})")

    # These slopes are used only for the fixed-angle orange/yellow rays.
    orange_slope = rm.orange_ray.calculate_slope(x_per_unit, y_per_unit)
    yellow_slope = rm.yellow_ray.calculate_slope(x_per_unit, y_per_unit)

    temp_position = "flat"
    temp_entry_price: Optional[float] = None
    temp_entry_time = None
    temp_entry_bar: int = 0
    trading_halted = False
    halt_time = None

    # Trailing stop state: tracks a ~60° line from the most recent swing point.
    trailing_stop_price: Optional[float] = None  # current trailing stop level
    trailing_stop_anchor_time = None
    trailing_stop_anchor_price: Optional[float] = None
    _TRAILING_ANGLE_DEG = 60.0  # angle of the trailing stop line

    buy_signals: Dict[pd.Timestamp, float] = {}
    sell_signals: Dict[pd.Timestamp, float] = {}
    liquidation_timestamps: set = set()
    session_realized_pl: float = 0.0  # running closed-trade P/L for daily loss cap

    # Per-minute geometry that will be attached to the result so the
    # interactive plotter only has to *render* what the algo computed.
    orange_prices = []
    yellow_prices = []
    purple_prices = []
    blue_prices = []

    orange_slopes = []
    yellow_slopes = []
    purple_slopes = []
    blue_slopes = []

    purple_anchor_prices = []
    purple_anchor_times = []
    blue_anchor_prices = []
    blue_anchor_times = []

    # Ray drawing data: start anchor points, visual angles, and end-of-session prices.
    # These allow plotFigure.py to render rays without any recalculation.
    orange_ray_start_prices = []
    orange_ray_start_times = []
    yellow_ray_start_prices = []
    yellow_ray_start_times = []
    purple_ray_start_prices = []
    purple_ray_start_times = []
    blue_ray_start_prices = []
    blue_ray_start_times = []

    magenta_prices = []
    lime_prices = []

    orange_angles = []
    yellow_angles = []
    purple_angles = []
    blue_angles = []

    orange_ray_end_prices = []
    yellow_ray_end_prices = []
    purple_ray_end_prices = []
    blue_ray_end_prices = []

    for i, (time, row) in enumerate(full_data.iterrows()):
        current_close = float(row["Close"])

        if time >= cutoff_time and i >= 3 and not trading_halted:
            # Compute "previous-minute" values using the ray state that has
            # already been updated through the prior bar. This mirrors the
            # incremental logic in the interactive plotter, so crossings use
            # the same prev_* values as the chart.

            prev_time = full_data.index[i - 1]
            prev_close = float(full_data["Close"].iloc[i - 1])

            # Slopes and prices as of the previous minute.
            prev_orange_slope = rm.orange_ray.adjusted_slope or rm.orange_ray.calculate_slope(x_per_unit, y_per_unit)
            prev_yellow_slope = rm.yellow_ray.adjusted_slope or rm.yellow_ray.calculate_slope(x_per_unit, y_per_unit)
            prev_purple_slope = rm.purple_ray.adjusted_slope or rm.purple_ray.calculate_slope(x_per_unit, y_per_unit)
            prev_blue_slope = rm.blue_ray.adjusted_slope or rm.blue_ray.calculate_slope(x_per_unit, y_per_unit)

            prev_orange = rm.orange_ray.get_price_at_time(prev_time, prev_orange_slope)
            prev_yellow = rm.yellow_ray.get_price_at_time(prev_time, prev_yellow_slope)
            prev_purple = rm.purple_ray.get_price_at_time(prev_time, prev_purple_slope)
            prev_blue = rm.blue_ray.get_price_at_time(prev_time, prev_blue_slope)

            # Magenta and lime ray values at prev bar.
            prev_magenta = rm.magenta_ray.get_price_at_time(prev_time, rm.magenta_ray.adjusted_slope) if rm.magenta_ray is not None and rm.magenta_ray.adjusted_slope is not None else None
            prev_lime    = rm.lime_ray.get_price_at_time(prev_time, rm.lime_ray.adjusted_slope)       if rm.lime_ray    is not None and rm.lime_ray.adjusted_slope    is not None else None

            # Current-bar orange/yellow prices used for the 50-point proximity check.
            curr_orange = rm.orange_ray.get_price_at_time(time, prev_orange_slope)
            curr_yellow = rm.yellow_ray.get_price_at_time(time, prev_yellow_slope)

            # Liquidation: if already in a trade and the relevant ray is crossed
            # against the trade direction, close the position flat immediately.
            # Long  → liquidate on a downward cross of blue only.
            # Short → liquidate on an upward  cross of purple only.
            liquidated_this_bar = False

            # Hard stop-loss: if unrealized loss exceeds max_loss_per_trade,
            # exit immediately. If max_loss > 0: go flat. If max_loss < 0: reverse.
            stop_threshold = abs(cfg.max_loss_per_trade)
            stop_reverse   = cfg.max_loss_per_trade < 0
            if stop_threshold > 0 and temp_position != "flat" and temp_entry_price is not None:
                if temp_position == "long":
                    unrealized = current_close - temp_entry_price
                else:
                    unrealized = temp_entry_price - current_close
                if unrealized <= -stop_threshold:
                    if temp_position == "long":
                        session_realized_pl += current_close - temp_entry_price
                        sell_signals[time] = current_close
                        liquidation_timestamps.add(time)
                        if stop_reverse:
                            temp_position    = "short"
                            temp_entry_price = current_close
                            temp_entry_time  = time
                            temp_entry_bar   = i
                        else:
                            temp_position    = "flat"
                            temp_entry_price = None
                            temp_entry_time  = None
                    else:
                        session_realized_pl += temp_entry_price - current_close
                        buy_signals[time] = current_close
                        liquidation_timestamps.add(time)
                        if stop_reverse:
                            temp_position    = "long"
                            temp_entry_price = current_close
                            temp_entry_time  = time
                            temp_entry_bar   = i
                        else:
                            temp_position    = "flat"
                            temp_entry_price = None
                            temp_entry_time  = None
                    liquidated_this_bar = True

            # --- Trailing stop line ---
            # Activates after 75+ pts profit. Tightens after higher-high (long)
            # or lower-low (short) confirmation following a pullback.
            if not liquidated_this_bar and temp_position != "flat" and temp_entry_price is not None and i >= 5 and cfg.max_loss_per_trade != 999:
                if temp_position == "long":
                    unrealized_profit = current_close - temp_entry_price
                else:
                    unrealized_profit = temp_entry_price - current_close

                if unrealized_profit >= 75:
                    # Determine if we've had a higher-high confirmation.
                    # Look for: high > prev_high AND a pullback low exists between them.
                    has_hh_confirmation = False
                    confirmation_swing_price = None
                    confirmation_swing_time  = None

                    if temp_position == "long" and i >= 4:
                        # Scan backwards for pattern: high, pullback, higher high
                        highs = [float(full_data["High"].iloc[j]) for j in range(max(0, i-10), i+1)]
                        lows  = [float(full_data["Low"].iloc[j])  for j in range(max(0, i-10), i+1)]
                        times = [full_data.index[j] for j in range(max(0, i-10), i+1)]
                        # Find the highest high before current bar
                        if len(highs) >= 3:
                            for k in range(len(highs)-1, 1, -1):
                                if highs[k] > highs[k-2]:  # current high > high 2 bars ago
                                    # Check if there's a dip in between
                                    mid_low = lows[k-1]
                                    if highs[k] - mid_low >= 30:  # meaningful pullback
                                        has_hh_confirmation = True
                                        confirmation_swing_price = mid_low
                                        confirmation_swing_time  = times[k-1]
                                        break

                    elif temp_position == "short" and i >= 4:
                        highs = [float(full_data["High"].iloc[j]) for j in range(max(0, i-10), i+1)]
                        lows  = [float(full_data["Low"].iloc[j])  for j in range(max(0, i-10), i+1)]
                        times = [full_data.index[j] for j in range(max(0, i-10), i+1)]
                        if len(lows) >= 3:
                            for k in range(len(lows)-1, 1, -1):
                                if lows[k] < lows[k-2]:  # current low < low 2 bars ago
                                    mid_high = highs[k-1]
                                    if mid_high - lows[k] >= 30:
                                        has_hh_confirmation = True
                                        confirmation_swing_price = mid_high
                                        confirmation_swing_time  = times[k-1]
                                        break

                    # Set angle based on confirmation and profit level.
                    if has_hh_confirmation and unrealized_profit >= 150:
                        trail_angle = 60.0  # tight after confirmed trend + big profit
                    elif has_hh_confirmation:
                        trail_angle = 50.0  # moderate after confirmed trend
                    else:
                        trail_angle = 40.0  # loose before confirmation

                    trailing_slope = np.tan(np.deg2rad(trail_angle)) * (y_per_unit / x_per_unit)

                    # Use confirmation swing as anchor if available, else most recent swing.
                    anchor_price = None
                    anchor_time  = None

                    if has_hh_confirmation and confirmation_swing_price is not None:
                        anchor_price = confirmation_swing_price
                        anchor_time  = confirmation_swing_time
                    else:
                        # Fallback: find most recent significant swing in last 15 bars.
                        SWING_MIN = 50.0
                        for j in range(max(1, i-15), i):
                            if j >= len(full_data) - 1:
                                continue
                            if temp_position == "long":
                                lo = float(full_data["Low"].iloc[j])
                                prev_lo = float(full_data["Low"].iloc[j-1])
                                next_lo = float(full_data["Low"].iloc[j+1])
                                if prev_lo - lo >= SWING_MIN * 0.3 and next_lo - lo >= SWING_MIN * 0.3:
                                    if anchor_price is None or lo > anchor_price:
                                        anchor_price = lo
                                        anchor_time  = full_data.index[j]
                            else:
                                hi = float(full_data["High"].iloc[j])
                                prev_hi = float(full_data["High"].iloc[j-1])
                                next_hi = float(full_data["High"].iloc[j+1])
                                if hi - prev_hi >= SWING_MIN * 0.3 and hi - next_hi >= SWING_MIN * 0.3:
                                    if anchor_price is None or hi < anchor_price:
                                        anchor_price = hi
                                        anchor_time  = full_data.index[j]

                    if anchor_price is not None and anchor_time is not None:
                        t_diff = mdates.date2num(time) - mdates.date2num(anchor_time)
                        if t_diff > 0:
                            if temp_position == "long":
                                stop_level = anchor_price + trailing_slope * t_diff
                                if current_close < stop_level:
                                    session_realized_pl += current_close - temp_entry_price
                                    sell_signals[time] = current_close
                                    liquidation_timestamps.add(time)
                                    temp_position = "flat"
                                    temp_entry_price = None
                                    temp_entry_time  = None
                                    liquidated_this_bar = True
                            else:
                                stop_level = anchor_price - trailing_slope * t_diff
                                if current_close > stop_level:
                                    session_realized_pl += temp_entry_price - current_close
                                    buy_signals[time] = current_close
                                    liquidation_timestamps.add(time)
                                    temp_position = "flat"
                                    temp_entry_price = None
                                    temp_entry_time  = None
                                    liquidated_this_bar = True

            # --- Spike profit take ---
            # If unrealized profit >= spike_profit_pts within spike_profit_bars
            # of entry, exit flat immediately. Locks in explosive early gains.
            if (not liquidated_this_bar and temp_position != "flat"
                    and temp_entry_price is not None and temp_entry_time is not None
                    and cfg.spike_profit_bars > 0 and cfg.spike_profit_pts > 0):
                bars_since_entry = i - temp_entry_bar
                if 0 < bars_since_entry <= cfg.spike_profit_bars:
                    if temp_position == "long":
                        spike_unrealized = current_close - temp_entry_price
                    else:
                        spike_unrealized = temp_entry_price - current_close
                    if spike_unrealized >= cfg.spike_profit_pts:
                        if temp_position == "long":
                            session_realized_pl += current_close - temp_entry_price
                            sell_signals[time] = current_close
                        else:
                            session_realized_pl += temp_entry_price - current_close
                            buy_signals[time] = current_close
                        liquidation_timestamps.add(time)
                        temp_position = "flat"
                        temp_entry_price = None
                        temp_entry_time = None
                        liquidated_this_bar = True

            # Determine if this is the last bar of the session (go flat, not reverse).
            is_last_bar = (i == len(full_data) - 1)

            # Reversal guard: block reversals within min_reversal_minutes of entry.
            # EXCEPTION: if orange or yellow line is crossed, always allow (safety line override).
            mins_since_entry = (
                (time - temp_entry_time).total_seconds() / 60
                if temp_entry_time is not None else 999
            )

            # Check if orange or yellow line is being crossed this bar.
            orange_cross_buy  = (prev_close is not None and prev_orange is not None and
                                 prev_close <= prev_orange and current_close > prev_orange)
            yellow_cross_sell = (prev_close is not None and prev_yellow is not None and
                                 prev_close >= prev_yellow and current_close < prev_yellow)
            safety_line_override = (
                (temp_position == "short" and orange_cross_buy) or
                (temp_position == "long"  and yellow_cross_sell)
            )

            reversal_blocked = (
                cfg.min_reversal_minutes > 0
                and mins_since_entry < cfg.min_reversal_minutes
                and not safety_line_override
            )

            # BUY signals - triggers from flat or short (reversal).
            # Purple crosses suppressed when close is within proximity_points of orange.
            if temp_position != "long" and time not in buy_signals and not liquidated_this_bar:
                # Block reversal from short if not enough time has passed.
                if temp_position == "short" and reversal_blocked:
                    pass
                else:
                    buy_triggered = False

                    if prev_close is not None and prev_orange is not None:
                        if prev_close <= prev_orange and current_close > prev_orange:
                            buy_triggered = True

                    if not buy_triggered and prev_close is not None and prev_purple is not None:
                        angle_slope = prev_purple_slope
                        purple_angle = _display_angle_from_slope(angle_slope, x_per_unit, y_per_unit)
                        if purple_angle < cfg.steep_angle_threshold and prev_close <= prev_purple and current_close > prev_purple:
                            within_50 = (
                                abs(current_close - curr_orange) <= cfg.proximity_points
                            )
                            if not within_50:
                                buy_triggered = True

                    # Magenta swing high ray BUY trigger.
                    if not buy_triggered and prev_magenta is not None:
                        mag_slope = rm.magenta_ray.adjusted_slope
                        mag_angle = _display_angle_from_slope(mag_slope, x_per_unit, y_per_unit)
                        curr_magenta = rm.magenta_ray.get_price_at_time(time, mag_slope)
                        if mag_angle < cfg.steep_angle_threshold and prev_close <= prev_magenta and current_close > prev_magenta:
                            within_50 = abs(current_close - curr_orange) <= cfg.proximity_points
                            if not within_50:
                                buy_triggered = True

                    # Water mark shield: suppress BUY reversal if high cluster (resistance) is nearby
                    # Only active during day session (9:30-17:00 ET) — hurts overnight performance
                    _in_day_session = 9 <= time.hour < 17
                    if buy_triggered and temp_position == "short" and cfg.wm_shield_distance > 0 and i >= cfg.wm_lookback and _in_day_session:
                        ws = max(0, i - cfg.wm_lookback)
                        wm_highs = [float(full_data["High"].iloc[j]) for j in range(ws, i)]
                        wm_times = [full_data.index[j] for j in range(ws, i)]
                        for lvl, _ in _find_wm_clusters(wm_highs, wm_times, cfg.wm_tolerance, cfg.wm_min_touches, cfg.wm_min_span):
                            if lvl > current_close and (lvl - current_close) <= cfg.wm_shield_distance:
                                buy_triggered = False
                                break

                    if buy_triggered:
                        if temp_position == "short" and temp_entry_price is not None:
                            session_realized_pl += temp_entry_price - current_close
                        buy_signals[time] = current_close
                        if is_last_bar:
                            temp_position = "flat"
                            temp_entry_price = None
                            temp_entry_time  = None
                        else:
                            temp_position    = "long"
                            temp_entry_price = current_close
                            temp_entry_time  = time
                            temp_entry_bar   = i
                            trailing_stop_price = None
                            trailing_stop_anchor_price = None
                            trailing_stop_anchor_time  = None

            # SELL signals - triggers from flat or long (reversal).
            # SELL signals - triggers from flat or long (reversal).
            # Blue crosses suppressed when close is within proximity_points of yellow.
            if temp_position != "short" and time not in sell_signals and not liquidated_this_bar:
                # Block reversal from long if not enough time has passed.
                if temp_position == "long" and reversal_blocked:
                    pass
                else:
                    sell_triggered = False

                    if prev_close is not None and prev_yellow is not None:
                        if prev_close >= prev_yellow and current_close < prev_yellow:
                            sell_triggered = True

                    if not sell_triggered and prev_close is not None and prev_blue is not None:
                        angle_slope = prev_blue_slope
                        blue_angle = _display_angle_from_slope(angle_slope, x_per_unit, y_per_unit)
                        if blue_angle < cfg.steep_angle_threshold and prev_close >= prev_blue and current_close < prev_blue:
                            within_50 = (
                                abs(current_close - curr_yellow) <= cfg.proximity_points
                            )
                            if not within_50:
                                sell_triggered = True

                    # Lime swing low ray SELL trigger.
                    if not sell_triggered and prev_lime is not None:
                        lime_slope = rm.lime_ray.adjusted_slope
                        lime_angle = _display_angle_from_slope(lime_slope, x_per_unit, y_per_unit)
                        curr_lime = rm.lime_ray.get_price_at_time(time, lime_slope)
                        if lime_angle < cfg.steep_angle_threshold and prev_close >= prev_lime and current_close < prev_lime:
                            within_50 = abs(current_close - curr_yellow) <= cfg.proximity_points
                            if not within_50:
                                sell_triggered = True

                    # Water mark shield: suppress SELL reversal if low cluster (support) is nearby
                    # Only active during day session (9:30-17:00 ET) — hurts overnight performance
                    _in_day_session = 9 <= time.hour < 17
                    if sell_triggered and temp_position == "long" and cfg.wm_shield_distance > 0 and i >= cfg.wm_lookback and _in_day_session:
                        ws = max(0, i - cfg.wm_lookback)
                        wm_lows = [float(full_data["Low"].iloc[j]) for j in range(ws, i)]
                        wm_times = [full_data.index[j] for j in range(ws, i)]
                        for lvl, _ in _find_wm_clusters(wm_lows, wm_times, cfg.wm_tolerance, cfg.wm_min_touches, cfg.wm_min_span):
                            if lvl < current_close and (current_close - lvl) <= cfg.wm_shield_distance:
                                sell_triggered = False
                                break

                    if sell_triggered:
                        if temp_position == "long" and temp_entry_price is not None:
                            session_realized_pl += current_close - temp_entry_price
                        sell_signals[time] = current_close
                        if is_last_bar:
                            temp_position    = "flat"
                            temp_entry_price = None
                            temp_entry_time  = None
                        else:
                            temp_position    = "short"
                            temp_entry_price = current_close
                            temp_entry_time  = time
                            temp_entry_bar   = i
                            trailing_stop_price = None
                            trailing_stop_anchor_price = None
                            trailing_stop_anchor_time  = None

        # Update steep rays for the next iteration (this will be the
        # "previous-minute" state on the next loop iteration).
        current_data_so_far = full_data.iloc[: i + 1]
        rm.purple_ray = minute_purple_ray
        rm.blue_ray = minute_blue_ray
        rm.update_all_rays(current_data_so_far, x_per_unit, y_per_unit)
        minute_purple_ray = rm.purple_ray
        minute_blue_ray = rm.blue_ray

        # After updating, capture the ray geometry for this bar so the
        # caller can inspect/plot exactly what the algo used.
        # Orange / yellow use fixed angles; purple / blue come from
        # the trendline engine plus the walk-forward anchor logic.
        orange_slope_now = rm.orange_ray.adjusted_slope or rm.orange_ray.calculate_slope(x_per_unit, y_per_unit)
        yellow_slope_now = rm.yellow_ray.adjusted_slope or rm.yellow_ray.calculate_slope(x_per_unit, y_per_unit)
        purple_slope_now = rm.purple_ray.adjusted_slope or rm.purple_ray.calculate_slope(x_per_unit, y_per_unit)
        blue_slope_now = rm.blue_ray.adjusted_slope or rm.blue_ray.calculate_slope(x_per_unit, y_per_unit)

        orange_slopes.append(float(orange_slope_now))
        yellow_slopes.append(float(yellow_slope_now))
        purple_slopes.append(float(purple_slope_now))
        blue_slopes.append(float(blue_slope_now))

        orange_prices.append(float(rm.orange_ray.get_price_at_time(time, orange_slope_now)))
        yellow_prices.append(float(rm.yellow_ray.get_price_at_time(time, yellow_slope_now)))
        purple_prices.append(float(rm.purple_ray.get_price_at_time(time, purple_slope_now)))
        blue_prices.append(float(rm.blue_ray.get_price_at_time(time, blue_slope_now)))

        # Magenta and lime swing rays.
        if rm.magenta_ray is not None and rm.magenta_ray.adjusted_slope is not None:
            magenta_prices.append(float(rm.magenta_ray.get_price_at_time(time, rm.magenta_ray.adjusted_slope)))
        else:
            magenta_prices.append(float("nan"))

        if rm.lime_ray is not None and rm.lime_ray.adjusted_slope is not None:
            lime_prices.append(float(rm.lime_ray.get_price_at_time(time, rm.lime_ray.adjusted_slope)))
        else:
            lime_prices.append(float("nan"))

        # Anchor meta so the plotter/debug tools can see exactly where
        # the steep rays are based.
        purple_anchor_price = rm.purple_anchor_price if rm.purple_anchor_price is not None else rm.purple_ray.start_price
        purple_anchor_time = rm.purple_anchor_time if rm.purple_anchor_time is not None else rm.purple_ray.start_time
        blue_anchor_price = rm.blue_anchor_price if rm.blue_anchor_price is not None else rm.blue_ray.start_price
        blue_anchor_time = rm.blue_anchor_time if rm.blue_anchor_time is not None else rm.blue_ray.start_time

        purple_anchor_prices.append(float(purple_anchor_price))
        purple_anchor_times.append(purple_anchor_time)
        blue_anchor_prices.append(float(blue_anchor_price))
        blue_anchor_times.append(blue_anchor_time)

        # Ray start points (anchor after walk-forward) and visual angles.
        _end_num = mdates.date2num(full_data.index[-1])

        orange_ray_start_prices.append(float(rm.orange_ray.start_price))
        orange_ray_start_times.append(rm.orange_ray.start_time)
        yellow_ray_start_prices.append(float(rm.yellow_ray.start_price))
        yellow_ray_start_times.append(rm.yellow_ray.start_time)
        purple_ray_start_prices.append(float(rm.purple_ray.start_price))
        purple_ray_start_times.append(rm.purple_ray.start_time)
        blue_ray_start_prices.append(float(rm.blue_ray.start_price))
        blue_ray_start_times.append(rm.blue_ray.start_time)

        orange_angles.append(_display_angle_from_slope(orange_slope_now, x_per_unit, y_per_unit))
        yellow_angles.append(_display_angle_from_slope(yellow_slope_now, x_per_unit, y_per_unit))
        purple_angles.append(_display_angle_from_slope(purple_slope_now, x_per_unit, y_per_unit))
        blue_angles.append(_display_angle_from_slope(blue_slope_now, x_per_unit, y_per_unit))

        orange_ray_end_prices.append(float(
            rm.orange_ray.start_price + orange_slope_now * (_end_num - mdates.date2num(rm.orange_ray.start_time))))
        yellow_ray_end_prices.append(float(
            rm.yellow_ray.start_price + yellow_slope_now * (_end_num - mdates.date2num(rm.yellow_ray.start_time))))
        purple_ray_end_prices.append(float(
            rm.purple_ray.start_price + purple_slope_now * (_end_num - mdates.date2num(rm.purple_ray.start_time))))
        blue_ray_end_prices.append(float(
            rm.blue_ray.start_price + blue_slope_now * (_end_num - mdates.date2num(rm.blue_ray.start_time))))

    # Build and return enriched per-minute frame
    # per-bar geometry so plotting is a pure visualization step.
    result = _build_signals_frame(full_data, buy_signals, sell_signals, trading_halted, halt_time, liquidation_timestamps)

    result["orange_ray"] = orange_prices
    result["yellow_ray"] = yellow_prices
    result["purple_ray"] = purple_prices
    result["blue_ray"]   = blue_prices
    result["magenta_ray"] = magenta_prices
    result["lime_ray"]    = lime_prices

    result["orange_slope"] = orange_slopes
    result["yellow_slope"] = yellow_slopes
    result["purple_slope"] = purple_slopes
    result["blue_slope"] = blue_slopes

    result["purple_anchor_price"] = purple_anchor_prices
    result["purple_anchor_time"] = purple_anchor_times
    result["blue_anchor_price"] = blue_anchor_prices
    result["blue_anchor_time"] = blue_anchor_times

    result["orange_ray_start_price"] = orange_ray_start_prices
    result["orange_ray_start_time"]  = orange_ray_start_times
    result["yellow_ray_start_price"] = yellow_ray_start_prices
    result["yellow_ray_start_time"]  = yellow_ray_start_times
    result["purple_ray_start_price"] = purple_ray_start_prices
    result["purple_ray_start_time"]  = purple_ray_start_times
    result["blue_ray_start_price"]   = blue_ray_start_prices
    result["blue_ray_start_time"]    = blue_ray_start_times

    result["orange_angle"] = orange_angles
    result["yellow_angle"] = yellow_angles
    result["purple_angle"] = purple_angles
    result["blue_angle"]   = blue_angles

    result["orange_ray_end_price"] = orange_ray_end_prices
    result["yellow_ray_end_price"] = yellow_ray_end_prices
    result["purple_ray_end_price"] = purple_ray_end_prices
    result["blue_ray_end_price"]   = blue_ray_end_prices

    # ------------------------------------------------------------------ #
    # Display-layer pre-computations                                       #
    # These replace every remaining data aggregation inside plotFigure.py  #
    # so that module truly contains zero calculations.                     #
    # ------------------------------------------------------------------ #

    # Chart axis bounds — constant for the session.
    result["y_min"] = float(result["Low"].min()) - 20.0
    result["y_max"] = float(result["High"].max()) + 20.0

    # Session open price (first Close) — constant across all bars.
    result["session_open"] = float(result["Close"].iloc[0])

    # Per-bar running price change from the session open.
    result["rolling_price_change"] = result["Close"] - float(result["Close"].iloc[0])

    # Expanding (running) high/low extremes and their price range.
    result["rolling_max_high"] = result["High"].expanding().max()
    result["rolling_min_low"]  = result["Low"].expanding().min()
    result["rolling_range"]    = result["rolling_max_high"] - result["rolling_min_low"]

    # Timestamp of the current running max High and min Low.
    _running_max  = float("-inf")
    _running_min  = float("inf")
    _max_high_times: list = []
    _min_low_times: list  = []
    _last_max_t = result.index[0]
    _last_min_t = result.index[0]
    for _ts, _row in result.iterrows():
        if float(_row["High"]) >= _running_max:
            _running_max = float(_row["High"])
            _last_max_t  = _ts
        if float(_row["Low"]) <= _running_min:
            _running_min = float(_row["Low"])
            _last_min_t  = _ts
        _max_high_times.append(_last_max_t)
        _min_low_times.append(_last_min_t)
    result["rolling_max_high_time"] = _max_high_times
    result["rolling_min_low_time"]  = _min_low_times

    # Running cumulative signal counts.
    result["rolling_buy_count"]  = (result["signal"] == "BUY").cumsum().astype(int)
    result["rolling_sell_count"] = (result["signal"] == "SELL").cumsum().astype(int)

    return result

