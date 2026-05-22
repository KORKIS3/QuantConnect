"""
scott_geometry_engine.py — Scott's Geometry Engine

Lines are containment boundaries, NOT regression fits.
Resistance lives ABOVE price. Support lives BELOW price.
A line NEVER goes through candle bodies.

Target benchmark: visualize_target_output.py (02/11 mockup)
Expected output on 02/11:
  - Orange: 50585 bar 2, slope -1.8
  - Yellow: 50459 bar 0, slope +1.8 (ONE yellow, not 20)
  - Blue Original: 50459 bar 0, slope +9.0, broken at bar 6
  - Purple Original: 50585 bar 2, slope -2.93
  - Continuation Blues: from proven bounce lows (ascending +1.83)
  - Tactical Purple: from bounce peak 50544 bar 16, slope -8.80, visible from bar 32
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ScottLine:
    """A single line in Scott's geometry."""
    line_id: int
    line_type: str       # ORANGE, YELLOW, PURPLE_ORIGINAL, BLUE_ORIGINAL,
                         # CONTINUATION_BLUE, TACTICAL_PURPLE
    anchor_bar: int
    anchor_price: float
    slope: float         # pts/bar
    state: str           # ACTIVE, BROKEN, RECLAIMED
    direction: str       # RESISTANCE or SUPPORT
    created_bar: int
    p2_bar: int = -1
    p2_price: float = 0.0
    touch_count: int = 0
    broken_bar: int = -1
    reclaimed_bar: int = -1

    def value_at(self, bar: int) -> float:
        return self.anchor_price + self.slope * (bar - self.anchor_bar)


class ScottGeometryEngine:
    """
    Produces lines Scott would naturally draw.
    Containment-first. Never through bodies. Structure earns existence.
    """

    def __init__(self, min_swing_pts=15.0, continuation_slope=1.83):
        self.min_swing_pts = min_swing_pts
        self.continuation_slope = continuation_slope  # fixed ascending slope for cont. blues

        self.lines: List[ScottLine] = []
        self._next_id = 1

        self.highs: List[float] = []
        self.lows: List[float] = []
        self.closes: List[float] = []
        self.opens: List[float] = []
        self.n_bars = 0

        # Session extremes (for Orange/Yellow — only ONE of each active)
        self.session_high = -1e30
        self.session_high_bar = -1
        self.session_low = 1e30
        self.session_low_bar = -1

        # Swing tracking
        self.swing_highs: List[tuple] = []  # (bar, price, prominence)
        self.swing_lows: List[tuple] = []

        # Line creation state
        self._purple_orig_id = -1  # id of active purple original
        self._blue_orig_id = -1
        self._orange_id = -1
        self._yellow_id = -1

        # Continuation blue tracking
        self._last_cont_blue_bar = -1
        self._cont_blue_count = 0

        # Tactical purple tracking
        self._tactical_purple_created = False

    def _new_id(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i

    # ──────────────────────────────────────────────────────────────────
    # CORE
    # ──────────────────────────────────────────────────────────────────

    def process_bar(self, open_p: float, high: float, low: float, close: float):
        bar = self.n_bars
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)
        self.opens.append(open_p)
        self.n_bars += 1

        # ── Orange: ONE active, from session high ──
        if high > self.session_high:
            self.session_high = high
            self.session_high_bar = bar
            self._update_orange(bar, high)

        # ── Yellow: ONE active, from session low ──
        if low < self.session_low:
            self.session_low = low
            self.session_low_bar = bar
            self._update_yellow(bar, low)

        # ── Detect swings (1-bar confirmation) ──
        if bar >= 2:
            self._detect_swings(bar)

        # ── Purple Original ──
        self._try_create_purple_original(bar)

        # ── Blue Original ──
        self._try_create_blue_original(bar)

        # ── Continuation Blues ──
        self._try_create_continuation_blue(bar)

        # ── Tactical Purple ──
        self._try_create_tactical_purple(bar)

        # ── Update states (breaks, touches) ──
        self._update_states(bar)

        # ── Wick adjustments (slope correction if wick pierced but close held) ──
        self._adjust_wicks(bar)

    # ──────────────────────────────────────────────────────────────────
    # ORANGE / YELLOW — One active at a time
    # ──────────────────────────────────────────────────────────────────

    def _update_orange(self, bar: int, price: float):
        """Orange: ONE line from the session high. Only updates when a NEW session
        high is made — does not create oranges from intermediate highs."""
        # Only create/update if this is truly a new session high
        # (the caller already checks high > session_high)
        if self._orange_id > 0:
            # Replace existing orange (new session high supersedes)
            for l in self.lines:
                if l.line_id == self._orange_id:
                    # Update in place — same line, new anchor
                    l.anchor_bar = bar
                    l.anchor_price = price
                    l.state = "ACTIVE"
                    return

        line = ScottLine(
            line_id=self._new_id(), line_type="ORANGE",
            anchor_bar=bar, anchor_price=price,
            slope=-1.83, state="ACTIVE", direction="RESISTANCE", created_bar=bar)
        self.lines.append(line)
        self._orange_id = line.line_id

    def _update_yellow(self, bar: int, price: float):
        """Yellow: ONE line from the session low. Updates in place on new session low."""
        if self._yellow_id > 0:
            for l in self.lines:
                if l.line_id == self._yellow_id:
                    l.anchor_bar = bar
                    l.anchor_price = price
                    l.state = "ACTIVE"
                    return

        line = ScottLine(
            line_id=self._new_id(), line_type="YELLOW",
            anchor_bar=bar, anchor_price=price,
            slope=+1.83, state="ACTIVE", direction="SUPPORT", created_bar=bar)
        self.lines.append(line)
        self._yellow_id = line.line_id

    # ──────────────────────────────────────────────────────────────────
    # SWING DETECTION
    # ──────────────────────────────────────────────────────────────────

    def _detect_swings(self, bar: int):
        j = bar - 1
        # Swing high
        h_j = self.highs[j]
        if (h_j - self.highs[j-1] >= self.min_swing_pts and
            h_j - self.highs[bar] >= self.min_swing_pts):
            self.swing_highs.append((j, h_j, (h_j - self.highs[j-1] + h_j - self.highs[bar]) / 2))

        # Swing low
        l_j = self.lows[j]
        if (self.lows[j-1] - l_j >= self.min_swing_pts and
            self.lows[bar] - l_j >= self.min_swing_pts):
            self.swing_lows.append((j, l_j, (self.lows[j-1] - l_j + self.lows[bar] - l_j) / 2))

    # ──────────────────────────────────────────────────────────────────
    # PURPLE ORIGINAL
    # ──────────────────────────────────────────────────────────────────

    def _try_create_purple_original(self, bar: int):
        """Create once: session high + first confirmed lower swing high.
        Slope = shallowest containment (stays above all highs)."""
        if self._purple_orig_id > 0:
            return  # already created

        # Need a swing high LOWER than session high
        candidates = [(b, p) for b, p, _ in self.swing_highs
                      if b > self.session_high_bar and p < self.session_high]
        if not candidates:
            return

        p2_bar, p2_price = candidates[-1]  # most recent

        # Shallowest containment slope from session high
        slope = self._containment_resistance_slope(self.session_high_bar, self.session_high, bar)
        if slope is None or slope >= 0:
            return

        line = ScottLine(
            line_id=self._new_id(), line_type="PURPLE_ORIGINAL",
            anchor_bar=self.session_high_bar, anchor_price=self.session_high,
            slope=slope, state="ACTIVE", direction="RESISTANCE", created_bar=bar,
            p2_bar=p2_bar, p2_price=p2_price)
        self.lines.append(line)
        self._purple_orig_id = line.line_id

    # ──────────────────────────────────────────────────────────────────
    # BLUE ORIGINAL
    # ──────────────────────────────────────────────────────────────────

    def _try_create_blue_original(self, bar: int):
        """Create once: session low + first meaningful higher low.
        Uses either a confirmed swing low OR a bar whose low is significantly
        above session low (proving support is rising).
        Slope = shallowest containment (stays below all lows)."""
        if self._blue_orig_id > 0:
            return
        if bar < 3:
            return

        # Method 1: confirmed swing low higher than session low
        candidates = [(b, p) for b, p, _ in self.swing_lows
                      if b > self.session_low_bar and p > self.session_low]

        # Method 2: if no swing low yet, look for a bar with low significantly
        # above session low (at least 20 pts) that has been confirmed by next bar
        if not candidates and bar >= self.session_low_bar + 2:
            for j in range(self.session_low_bar + 1, bar):
                lo_j = self.lows[j]
                # Must be meaningfully above session low
                if lo_j - self.session_low < 20:
                    continue
                # Must be confirmed: next bar's low is also above this bar's low
                # (price didn't immediately make new low)
                if j + 1 < self.n_bars and self.lows[j + 1] >= lo_j - 5:
                    candidates.append((j, lo_j))
                    break  # use first valid one

        if not candidates:
            return

        p2_bar, p2_price = candidates[0]

        slope = self._containment_support_slope(self.session_low_bar, self.session_low, bar)
        if slope is None or slope <= 0:
            return

        line = ScottLine(
            line_id=self._new_id(), line_type="BLUE_ORIGINAL",
            anchor_bar=self.session_low_bar, anchor_price=self.session_low,
            slope=slope, state="ACTIVE", direction="SUPPORT", created_bar=bar,
            p2_bar=p2_bar, p2_price=p2_price)
        self.lines.append(line)
        self._blue_orig_id = line.line_id

    # ──────────────────────────────────────────────────────────────────
    # CONTINUATION BLUE
    # ──────────────────────────────────────────────────────────────────

    def _try_create_continuation_blue(self, bar: int):
        """Create from proven bounce lows. Fixed ascending slope (+1.83).
        A bounce low = price made a low, then rose meaningfully from it.
        This proves that low mattered — support existed there."""
        if bar < 15:
            return

        # Check if bar-3 was a bounce low (3-bar confirmation)
        # A bounce low: lows[j] is lower than lows[j-1] AND lows[j+1] AND lows[j+2]
        # AND the bounce is meaningful (high within next 3 bars is 15+ above the low)
        j = bar - 3
        if j < 1:
            return

        lo_j = self.lows[j]

        # Must be lower than neighbors
        if self.lows[j-1] <= lo_j or self.lows[j+1] <= lo_j:
            return

        # Bounce must be meaningful: price rose at least 15 pts from that low
        max_bounce = max(self.highs[j+1], self.highs[j+2]) - lo_j
        if max_bounce < self.min_swing_pts:
            return

        # Don't duplicate: check if we already have a continuation blue near this price
        for l in self.lines:
            if l.line_type == "CONTINUATION_BLUE" and abs(l.anchor_price - lo_j) < 15:
                return

        # Minimum spacing from last continuation blue
        if self._last_cont_blue_bar > 0 and j - self._last_cont_blue_bar < 4:
            return

        line = ScottLine(
            line_id=self._new_id(), line_type="CONTINUATION_BLUE",
            anchor_bar=j, anchor_price=lo_j,
            slope=self.continuation_slope, state="ACTIVE",
            direction="SUPPORT", created_bar=bar,
            p2_bar=j, p2_price=lo_j)
        self.lines.append(line)
        self._last_cont_blue_bar = j
        self._cont_blue_count += 1

    # ──────────────────────────────────────────────────────────────────
    # TACTICAL PURPLE (profit protection)
    # ──────────────────────────────────────────────────────────────────

    def _try_create_tactical_purple(self, bar: int):
        """Tactical purple: steeper profit protection line over descending highs.
        Created AFTER price has resolved well below the original purple.
        Anchors at the first bounce peak after resolve begins, slopes through
        subsequent lower highs. Containment-correct (stays above all highs)."""
        if self._tactical_purple_created:
            return
        if self._purple_orig_id <= 0:
            return
        if bar < 20:
            return

        # Get purple original
        purple = None
        for l in self.lines:
            if l.line_id == self._purple_orig_id:
                purple = l
                break
        if purple is None:
            return

        # Price must be well below purple (resolve is active)
        purple_val = purple.value_at(bar)
        current_high = self.highs[bar]
        if purple_val - current_high < 30:
            return  # not enough separation yet

        # Find swing highs that are AT or BELOW the purple line
        # These are the bounce peaks during the downward resolve
        bounce_peaks = [(b, p) for b, p, _ in self.swing_highs
                        if b > purple.anchor_bar + 3 and p <= purple.value_at(b) + 2]

        if len(bounce_peaks) < 2:
            return

        # Try each bounce peak as P1, use the NEXT bounce peak as P2
        # Slope = from P1 through P2 (not full-session containment)
        for i in range(len(bounce_peaks) - 1):
            p1_bar, p1_price = bounce_peaks[i]
            p2_bar, p2_price = bounce_peaks[i + 1]

            # Compute slope from P1 to P2
            dt = p2_bar - p1_bar
            if dt <= 0:
                continue
            slope = (p2_price - p1_price) / dt

            # Must be descending (negative)
            if slope >= 0:
                continue

            # Must be steeper than purple original (more negative)
            if slope >= purple.slope:
                continue

            # Verify containment from P1 to P2 (no highs above the line between them)
            valid = True
            for k in range(p1_bar + 1, p2_bar):
                line_val = p1_price + slope * (k - p1_bar)
                if k < self.n_bars and self.highs[k] > line_val + 2:
                    valid = False
                    break

            if not valid:
                # Try containment slope instead (shallowest from P1 to P2 only)
                max_s = -1e30
                for k in range(p1_bar + 1, min(p2_bar + 1, self.n_bars)):
                    dt_k = k - p1_bar
                    req = (self.highs[k] - p1_price) / dt_k
                    if req > max_s:
                        max_s = req
                if max_s >= 0 or max_s >= purple.slope:
                    continue
                slope = max_s

            line = ScottLine(
                line_id=self._new_id(), line_type="TACTICAL_PURPLE",
                anchor_bar=p1_bar, anchor_price=p1_price,
                slope=slope, state="ACTIVE", direction="RESISTANCE", created_bar=bar,
                p2_bar=p2_bar, p2_price=p2_price)
            self.lines.append(line)
            self._tactical_purple_created = True
            return

    # ──────────────────────────────────────────────────────────────────
    # CONTAINMENT SLOPE COMPUTATION
    # ──────────────────────────────────────────────────────────────────

    def _containment_resistance_slope(self, p1_bar: int, p1_price: float,
                                       up_to_bar: int) -> Optional[float]:
        """Shallowest (least negative) slope that stays ABOVE all highs."""
        max_slope = -1e30
        for i in range(p1_bar + 1, min(up_to_bar + 1, self.n_bars)):
            dt = i - p1_bar
            required = (self.highs[i] - p1_price) / dt
            if required > max_slope:
                max_slope = required
        if max_slope >= 0:
            return None
        return max_slope  # no buffer — line sits exactly on the binding high

    def _containment_support_slope(self, p1_bar: int, p1_price: float,
                                    up_to_bar: int) -> Optional[float]:
        """Shallowest (least positive) slope that stays BELOW all lows."""
        min_slope = 1e30
        for i in range(p1_bar + 1, min(up_to_bar + 1, self.n_bars)):
            dt = i - p1_bar
            required = (self.lows[i] - p1_price) / dt
            if required < min_slope:
                min_slope = required
        if min_slope <= 0:
            return None
        return min_slope

    # ──────────────────────────────────────────────────────────────────
    # STATE UPDATES
    # ──────────────────────────────────────────────────────────────────

    def _update_states(self, bar: int):
        """Check for breaks and touches on active lines."""
        close = self.closes[bar]
        high = self.highs[bar]
        low = self.lows[bar]

        for line in self.lines:
            if line.state != "ACTIVE":
                # Check for reclaim on broken lines
                if line.state == "BROKEN":
                    lv = line.value_at(bar)
                    if line.direction == "RESISTANCE" and close < lv:
                        line.state = "RECLAIMED"
                        line.reclaimed_bar = bar
                    elif line.direction == "SUPPORT" and close > lv:
                        line.state = "RECLAIMED"
                        line.reclaimed_bar = bar
                continue

            lv = line.value_at(bar)

            if line.direction == "RESISTANCE":
                # Touch: high within 10 pts of line, close below
                if 0 <= lv - high <= 10 and close < lv:
                    line.touch_count += 1
                # Break: close above line
                if close > lv:
                    line.state = "BROKEN"
                    line.broken_bar = bar

            elif line.direction == "SUPPORT":
                if 0 <= low - lv <= 10 and close > lv:
                    line.touch_count += 1
                if close < lv:
                    line.state = "BROKEN"
                    line.broken_bar = bar

    # ──────────────────────────────────────────────────────────────────
    # WICK ADJUSTMENTS
    # ──────────────────────────────────────────────────────────────────

    def _adjust_wicks(self, bar: int):
        """If wick pierced but close held, adjust slope to re-encompass."""
        close = self.closes[bar]
        for line in self.lines:
            if line.state != "ACTIVE":
                continue
            lv = line.value_at(bar)

            if line.direction == "RESISTANCE":
                if self.highs[bar] > lv and close <= lv:
                    new_slope = self._containment_resistance_slope(
                        line.anchor_bar, line.anchor_price, bar)
                    if new_slope is not None and new_slope < 0:
                        line.slope = new_slope
            elif line.direction == "SUPPORT":
                if self.lows[bar] < lv and close >= lv:
                    new_slope = self._containment_support_slope(
                        line.anchor_bar, line.anchor_price, bar)
                    if new_slope is not None and new_slope > 0:
                        line.slope = new_slope

    # ──────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────

    def run_session(self, day_data):
        for i in range(len(day_data)):
            row = day_data.iloc[i]
            self.process_bar(float(row['Open']), float(row['High']),
                           float(row['Low']), float(row['Close']))

    def get_active_lines(self) -> List[ScottLine]:
        return [l for l in self.lines if l.state in ("ACTIVE", "RECLAIMED")]

    def get_all_lines(self) -> List[ScottLine]:
        return self.lines
