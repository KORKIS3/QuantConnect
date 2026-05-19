"""
frozen_ray_engine.py — Phase 1: Structure Engine

Computes frozen geometric rays from closed-bar data.
No trading signals. No execution. Structure only.

Rules:
- Lines NEVER pass through closed candle bodies or wicks
- Lines are frozen once created (no rolling regression)
- Open bars do not move lines
- Containment is mandatory (resistance >= all highs, support <= all lows)
- Hierarchy: Orange/Yellow (1) > Original Purple/Blue (2) > Rescue (3)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------

@dataclass
class FrozenRay:
    """A single frozen geometric ray."""
    line_id: int
    line_type: str          # ORANGE, YELLOW, PURPLE_ORIGINAL, BLUE_ORIGINAL, PURPLE_PROFIT, BLUE_PROFIT
    authority_rank: int     # 1=orange/yellow, 2=original purple/blue, 3=profit protection
    anchor_price: float     # P1 price
    anchor_bar: int         # P1 bar index
    slope: float            # pts/bar (negative=descending, positive=ascending)
    status: str             # FROZEN, PROVISIONAL, RETIRED
    direction: str          # RESISTANCE (above price) or SUPPORT (below price)
    created_at_bar: int
    touch_count: int = 0
    wick_adjust_count: int = 0
    retired_at_bar: int = -1
    parent_id: int = -1     # if profit protection, references parent

    def value_at(self, bar_idx: int) -> float:
        """Compute ray value at a given bar."""
        return self.anchor_price + self.slope * (bar_idx - self.anchor_bar)


# ---------------------------------------------------------------------------
# Structure Engine
# ---------------------------------------------------------------------------

class FrozenRayEngine:
    """Phase 1: Computes and maintains frozen structural rays."""

    def __init__(self, swing_threshold: float = 10.0, touch_lookback: int = 14):
        self.swing_threshold = swing_threshold
        self.touch_lookback = touch_lookback
        self.lines: List[FrozenRay] = []
        self._next_id = 1
        self.quadrant_state = "UNKNOWN"
        # Session tracking
        self.session_high = -1e30
        self.session_high_bar = -1
        self.session_low = 1e30
        self.session_low_bar = -1
        # Bar data (closed bars only)
        self.highs: List[float] = []
        self.lows: List[float] = []
        self.closes: List[float] = []
        self.opens: List[float] = []
        self.n_bars = 0
        # Dynamic touch threshold
        self._bar_ranges: List[float] = []

    def _new_id(self) -> int:
        id_ = self._next_id
        self._next_id += 1
        return id_

    def _touch_threshold(self) -> float:
        """Dynamic: max(10, 0.5 * avg bar range over lookback)."""
        if len(self._bar_ranges) < 5:
            return 10.0
        recent = self._bar_ranges[-self.touch_lookback:]
        return max(10.0, 0.5 * np.mean(recent))

    # ------------------------------------------------------------------
    # Core: process one closed bar
    # ------------------------------------------------------------------

    def process_bar(self, open_p: float, high: float, low: float, close: float):
        """Process a single CLOSED bar. Updates all structure."""
        bar_idx = self.n_bars
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)
        self.opens.append(open_p)
        self._bar_ranges.append(high - low)
        self.n_bars += 1

        # --- Orange/Yellow: session extremes ---
        if high > self.session_high:
            self.session_high = high
            self.session_high_bar = bar_idx
            self._create_orange(bar_idx, high)

        if low < self.session_low:
            self.session_low = low
            self.session_low_bar = bar_idx
            self._create_yellow(bar_idx, low)

        # --- Blue P2 search (support, ascending) ---
        self._search_blue_p2(bar_idx)

        # --- Purple P2 search (resistance, descending) ---
        self._search_purple_p2(bar_idx)

        # --- Wick adjustment on frozen lines ---
        self._check_wick_adjustments(bar_idx)

        # --- Touch counting ---
        self._update_touches(bar_idx)

        # --- Profit protection line search ---
        self._search_profit_protection(bar_idx)

        # --- Update quadrant state ---
        self._update_quadrant(bar_idx)

    # ------------------------------------------------------------------
    # Orange / Yellow creation
    # ------------------------------------------------------------------

    def _create_orange(self, bar_idx: int, price: float):
        """Create new orange ray from session high. Retire previous."""
        # Retire existing oranges
        for line in self.lines:
            if line.line_type == "ORANGE" and line.status != "RETIRED":
                line.status = "RETIRED"
                line.retired_at_bar = bar_idx

        # Fixed slope: ~-1.83 pts/bar (2.5 degrees approximation)
        slope = -1.83
        self.lines.append(FrozenRay(
            line_id=self._new_id(), line_type="ORANGE", authority_rank=1,
            anchor_price=price, anchor_bar=bar_idx, slope=slope,
            status="FROZEN", direction="RESISTANCE", created_at_bar=bar_idx,
        ))

    def _create_yellow(self, bar_idx: int, price: float):
        """Create new yellow ray from session low. Retire previous."""
        for line in self.lines:
            if line.line_type == "YELLOW" and line.status != "RETIRED":
                line.status = "RETIRED"
                line.retired_at_bar = bar_idx

        slope = +1.83
        self.lines.append(FrozenRay(
            line_id=self._new_id(), line_type="YELLOW", authority_rank=1,
            anchor_price=price, anchor_bar=bar_idx, slope=slope,
            status="FROZEN", direction="SUPPORT", created_at_bar=bar_idx,
        ))

    # ------------------------------------------------------------------
    # Blue P2 confirmation
    # ------------------------------------------------------------------

    def _search_blue_p2(self, bar_idx: int):
        """Search for P2 to freeze provisional blue lines."""
        if bar_idx < 2:
            return
        # Check if bar_idx-1 is a confirmed swing low
        j = bar_idx - 1
        if j < 1:
            return
        lo_j = self.lows[j]
        if (self.lows[j-1] - lo_j >= self.swing_threshold and
            self.lows[bar_idx] - lo_j >= self.swing_threshold):
            # Confirmed swing low at j
            for line in self.lines:
                if line.line_type == "BLUE_ORIGINAL" and line.status == "PROVISIONAL":
                    if lo_j > line.anchor_price:  # higher than P1
                        # Compute containment slope
                        slope = self._min_legal_support_slope(line.anchor_bar, line.anchor_price, bar_idx)
                        if slope is not None and slope > 0:
                            line.slope = slope
                            line.status = "FROZEN"

    def _search_purple_p2(self, bar_idx: int):
        """Search for P2 to freeze provisional purple lines."""
        if bar_idx < 2:
            return
        j = bar_idx - 1
        if j < 1:
            return
        hi_j = self.highs[j]
        if (hi_j - self.highs[j-1] >= self.swing_threshold and
            hi_j - self.highs[bar_idx] >= self.swing_threshold):
            # Confirmed swing high at j
            for line in self.lines:
                if line.line_type == "PURPLE_ORIGINAL" and line.status == "PROVISIONAL":
                    if hi_j < line.anchor_price:  # lower than P1
                        slope = self._min_legal_resistance_slope(line.anchor_bar, line.anchor_price, bar_idx)
                        if slope is not None and slope < 0:
                            line.slope = slope
                            line.status = "FROZEN"

    # ------------------------------------------------------------------
    # Containment-first slope computation
    # ------------------------------------------------------------------

    def _min_legal_resistance_slope(self, p1_bar: int, p1_price: float, up_to_bar: int) -> Optional[float]:
        """Find minimum legal slope for resistance (must stay ABOVE all highs)."""
        max_required = -1e30
        for i in range(p1_bar + 1, up_to_bar + 1):
            if i >= self.n_bars:
                break
            required = (self.highs[i] - p1_price) / (i - p1_bar)
            if required > max_required:
                max_required = required
        # Must be negative (descending) to be valid resistance
        if max_required >= 0:
            return None  # cannot create valid resistance
        return max_required

    def _min_legal_support_slope(self, p1_bar: int, p1_price: float, up_to_bar: int) -> Optional[float]:
        """Find maximum legal slope for support (must stay BELOW all lows)."""
        min_required = 1e30
        for i in range(p1_bar + 1, up_to_bar + 1):
            if i >= self.n_bars:
                break
            required = (self.lows[i] - p1_price) / (i - p1_bar)
            if required < min_required:
                min_required = required
        # Must be positive (ascending) to be valid support
        if min_required <= 0:
            return None
        return min_required

    # ------------------------------------------------------------------
    # Wick adjustment
    # ------------------------------------------------------------------

    def _check_wick_adjustments(self, bar_idx: int):
        """After close: if wick pierced line but close held, adjust slope minimally."""
        for line in self.lines:
            if line.status != "FROZEN":
                continue
            line_val = line.value_at(bar_idx)

            if line.direction == "RESISTANCE":
                if self.highs[bar_idx] > line_val:
                    if self.closes[bar_idx] > line_val:
                        # Confirmed break — retire line
                        line.status = "RETIRED"
                        line.retired_at_bar = bar_idx
                    else:
                        # Wick only — adjust slope to encompass
                        new_slope = self._min_legal_resistance_slope(
                            line.anchor_bar, line.anchor_price, bar_idx)
                        if new_slope is not None and new_slope < 0:
                            line.slope = new_slope
                            line.wick_adjust_count += 1
                        else:
                            line.status = "RETIRED"
                            line.retired_at_bar = bar_idx

            elif line.direction == "SUPPORT":
                if self.lows[bar_idx] < line_val:
                    if self.closes[bar_idx] < line_val:
                        # Confirmed break — retire line
                        line.status = "RETIRED"
                        line.retired_at_bar = bar_idx
                    else:
                        new_slope = self._min_legal_support_slope(
                            line.anchor_bar, line.anchor_price, bar_idx)
                        if new_slope is not None and new_slope > 0:
                            line.slope = new_slope
                            line.wick_adjust_count += 1
                        else:
                            line.status = "RETIRED"
                            line.retired_at_bar = bar_idx

    # ------------------------------------------------------------------
    # Touch counting
    # ------------------------------------------------------------------

    def _update_touches(self, bar_idx: int):
        """Count touches: price approaches line and moves away without break."""
        threshold = self._touch_threshold()
        for line in self.lines:
            if line.status != "FROZEN":
                continue
            line_val = line.value_at(bar_idx)

            if line.direction == "RESISTANCE":
                distance = line_val - self.highs[bar_idx]
                if 0 <= distance <= threshold:
                    # Price is close to resistance
                    if bar_idx >= 2 and self.highs[bar_idx - 1] < self.highs[bar_idx]:
                        # Was approaching
                        if self.closes[bar_idx] < line_val:
                            # Rejected (close held below)
                            line.touch_count += 1

            elif line.direction == "SUPPORT":
                distance = self.lows[bar_idx] - line_val
                if 0 <= distance <= threshold:
                    if bar_idx >= 2 and self.lows[bar_idx - 1] > self.lows[bar_idx]:
                        if self.closes[bar_idx] > line_val:
                            line.touch_count += 1

    # ------------------------------------------------------------------
    # Profit protection lines (steeper, only after proof)
    # ------------------------------------------------------------------

    def _search_profit_protection(self, bar_idx: int):
        """Create profit protection lines only after structure proves itself."""
        if bar_idx < 20:
            return  # need enough history

        # Find active original purple
        active_purple = None
        for line in self.lines:
            if line.line_type == "PURPLE_ORIGINAL" and line.status == "FROZEN":
                active_purple = line
                break

        if active_purple is None:
            return

        # Check if conditions met for steeper purple:
        # 1. Price resolved below purple (bearish)
        # 2. At least 2 bounce attempts that failed
        # 3. New lows made after bounces
        # 4. No existing profit protection purple active

        existing_pp = any(l.line_type == "PURPLE_PROFIT" and l.status == "FROZEN" for l in self.lines)
        if existing_pp:
            return

        # Find failed bounces: swing highs that are below purple and declining
        bounce_highs = []
        for i in range(active_purple.anchor_bar + 5, bar_idx - 1):
            if i < 2 or i >= self.n_bars - 1:
                continue
            hi = self.highs[i]
            if (hi - self.highs[i-1] >= self.swing_threshold and
                hi - self.highs[i+1] >= self.swing_threshold and
                hi < active_purple.value_at(i)):
                bounce_highs.append((i, hi))

        if len(bounce_highs) < 2:
            return  # need at least 2 failed bounces

        # Verify bounces are declining (second lower than first)
        if bounce_highs[-1][1] >= bounce_highs[0][1]:
            return  # bounces not declining — not proven

        # Verify new lows were made after the bounces
        last_bounce_bar = bounce_highs[-1][0]
        if bar_idx - last_bounce_bar < 3:
            return  # too soon after last bounce

        lows_after = self.lows[last_bounce_bar:bar_idx]
        lows_before = self.lows[bounce_highs[0][0]:bounce_highs[-1][0]]
        if not lows_after or not lows_before:
            return
        if min(lows_after) >= min(lows_before):
            return  # no new lows — not proven

        # Create profit protection purple from first bounce peak
        p1_bar = bounce_highs[0][0]
        p1_price = bounce_highs[0][1]
        slope = self._min_legal_resistance_slope(p1_bar, p1_price, bar_idx)

        if slope is not None and slope < 0:
            self.lines.append(FrozenRay(
                line_id=self._new_id(), line_type="PURPLE_PROFIT", authority_rank=3,
                anchor_price=p1_price, anchor_bar=p1_bar, slope=slope,
                status="FROZEN", direction="RESISTANCE", created_at_bar=bar_idx,
                parent_id=active_purple.line_id,
            ))

    # ------------------------------------------------------------------
    # Quadrant state
    # ------------------------------------------------------------------

    def _update_quadrant(self, bar_idx: int):
        """Label current quadrant based on price position relative to structure."""
        close = self.closes[bar_idx]

        # Find active lines by type
        active_purple = None
        active_blue = None
        active_orange = None
        active_yellow = None

        for line in self.lines:
            if line.status != "FROZEN":
                continue
            if line.line_type == "PURPLE_ORIGINAL" and active_purple is None:
                active_purple = line
            elif line.line_type == "BLUE_ORIGINAL" and active_blue is None:
                active_blue = line
            elif line.line_type == "ORANGE":
                active_orange = line  # latest
            elif line.line_type == "YELLOW":
                active_yellow = line  # latest

        # Determine quadrant
        above_purple = active_purple and close > active_purple.value_at(bar_idx)
        below_blue = active_blue and close < active_blue.value_at(bar_idx)
        above_orange = active_orange and close > active_orange.value_at(bar_idx)
        below_yellow = active_yellow and close < active_yellow.value_at(bar_idx)

        if above_orange:
            self.quadrant_state = "STRONG_BULLISH"
        elif above_purple:
            self.quadrant_state = "RESOLVING_UP"
        elif below_yellow:
            self.quadrant_state = "STRONG_BEARISH"
        elif below_blue:
            self.quadrant_state = "RESOLVING_DOWN"
        else:
            self.quadrant_state = "NEUTRAL"

    # ------------------------------------------------------------------
    # Session runner
    # ------------------------------------------------------------------

    def run_session(self, df):
        """Process an entire session DataFrame (must have Open, High, Low, Close)."""
        # Create initial provisional lines from first bar
        first_high = float(df.iloc[0]['High'])
        first_low = float(df.iloc[0]['Low'])

        # Provisional purple and blue (waiting for P2)
        self.lines.append(FrozenRay(
            line_id=self._new_id(), line_type="PURPLE_ORIGINAL", authority_rank=2,
            anchor_price=first_high, anchor_bar=0, slope=0.0,
            status="PROVISIONAL", direction="RESISTANCE", created_at_bar=0,
        ))
        self.lines.append(FrozenRay(
            line_id=self._new_id(), line_type="BLUE_ORIGINAL", authority_rank=2,
            anchor_price=first_low, anchor_bar=0, slope=0.0,
            status="PROVISIONAL", direction="SUPPORT", created_at_bar=0,
        ))

        for i in range(len(df)):
            row = df.iloc[i]
            self.process_bar(float(row['Open']), float(row['High']),
                           float(row['Low']), float(row['Close']))

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_containment(self) -> List[dict]:
        """Check all frozen lines for containment violations. Returns list of violations."""
        violations = []
        for line in self.lines:
            if line.status == "RETIRED" and line.retired_at_bar >= 0:
                check_end = line.retired_at_bar
            elif line.status == "FROZEN":
                check_end = self.n_bars
            else:
                continue

            for i in range(line.anchor_bar, check_end):
                if i >= self.n_bars:
                    break
                line_val = line.value_at(i)
                if line.direction == "RESISTANCE":
                    if self.highs[i] > line_val + 0.5:  # 0.5 tolerance
                        violations.append({
                            'line_id': line.line_id, 'line_type': line.line_type,
                            'bar': i, 'line_val': line_val, 'high': self.highs[i],
                            'violation': self.highs[i] - line_val,
                        })
                elif line.direction == "SUPPORT":
                    if self.lows[i] < line_val - 0.5:
                        violations.append({
                            'line_id': line.line_id, 'line_type': line.line_type,
                            'bar': i, 'line_val': line_val, 'low': self.lows[i],
                            'violation': line_val - self.lows[i],
                        })
        return violations

    def get_active_lines(self) -> List[FrozenRay]:
        """Return all non-retired lines."""
        return [l for l in self.lines if l.status != "RETIRED"]

    def get_all_lines(self) -> List[FrozenRay]:
        """Return all lines including retired (for visualization)."""
        return self.lines
