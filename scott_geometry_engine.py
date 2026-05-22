"""
scott_geometry_engine.py — Scott's Geometry Engine

Lines are NOT regression fits. Lines are containment boundaries.
Lines represent: ceilings, floors, active thesis, compression, resolve.

A line NEVER goes through candle bodies.
Resistance lives ABOVE price. Support lives BELOW price.
Lines must EARN existence through proven structure.

Visual benchmark: visualize_target_output.py (05/19 mockup)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ScottLine:
    """A single line in Scott's geometry."""
    line_id: int
    line_type: str       # ORANGE, YELLOW, PURPLE_ORIGINAL, BLUE_ORIGINAL,
                         # CONTINUATION_BLUE, TACTICAL_PURPLE
    anchor_bar: int      # P1 bar
    anchor_price: float  # P1 price
    slope: float         # pts/bar (negative=descending, positive=ascending)
    state: str           # ACTIVE, BROKEN, RECLAIMED, FLIPPED
    direction: str       # RESISTANCE (above price) or SUPPORT (below price)
    created_bar: int
    # P2 info (for lines that connect two pivots)
    p2_bar: int = -1
    p2_price: float = 0.0
    # Tracking
    touch_count: int = 0
    broken_bar: int = -1
    reclaimed_bar: int = -1
    # Quality
    bars_near_price: int = 0
    interactions: int = 0

    def value_at(self, bar: int) -> float:
        return self.anchor_price + self.slope * (bar - self.anchor_bar)


class ScottGeometryEngine:
    """
    Produces lines that Scott would naturally draw.

    Core principle: CONTAINMENT FIRST.
    - Resistance stays above all highs
    - Support stays below all lows
    - Slope is the SHALLOWEST that maintains containment
    - Lines earn existence through proven structure
    """

    def __init__(self, orange_slope_deg=2.5, min_swing_pts=15.0):
        """
        orange_slope_deg: fixed angle for orange/yellow (shallow containment)
        min_swing_pts: minimum prominence for a swing to qualify as P2
        """
        self.orange_slope_deg = orange_slope_deg
        self.min_swing_pts = min_swing_pts

        self.lines: List[ScottLine] = []
        self._next_id = 1

        # Session data
        self.highs: List[float] = []
        self.lows: List[float] = []
        self.closes: List[float] = []
        self.opens: List[float] = []
        self.n_bars = 0

        # Session extremes
        self.session_high = -1e30
        self.session_high_bar = -1
        self.session_low = 1e30
        self.session_low_bar = -1

        # Confirmed swing points
        self.swing_highs: List[tuple] = []  # (bar, price, prominence)
        self.swing_lows: List[tuple] = []

        # Purple/Blue state
        self._purple_created = False
        self._blue_created = False

        # Fixed slopes for orange/yellow (pts/bar, from degrees)
        # ~2.5 degrees on a standard chart ≈ 1.83 pts/bar
        self._orange_slope = -1.83  # descending
        self._yellow_slope = +1.83  # ascending

    def _new_id(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i

    # ──────────────────────────────────────────────────────────────────
    # CORE: Process one closed bar
    # ──────────────────────────────────────────────────────────────────

    def process_bar(self, open_p: float, high: float, low: float, close: float):
        """Process a single CLOSED bar."""
        bar = self.n_bars
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)
        self.opens.append(open_p)
        self.n_bars += 1

        # ── Session extremes → Orange/Yellow ──
        if high > self.session_high:
            self.session_high = high
            self.session_high_bar = bar
            self._create_orange(bar, high)

        if low < self.session_low:
            self.session_low = low
            self.session_low_bar = bar
            self._create_yellow(bar, low)

        # ── Detect confirmed swing points (1-bar lag) ──
        if bar >= 2:
            self._detect_swings(bar)

        # ── Try to create Purple/Blue from confirmed swings ──
        self._try_create_purple(bar)
        self._try_create_blue(bar)

        # ── Try to create continuation blues ──
        self._try_create_continuation_blue(bar)

        # ── Update line states (touches, breaks, reclaims) ──
        self._update_line_states(bar)

    # ──────────────────────────────────────────────────────────────────
    # ORANGE / YELLOW: Strategic ceiling and floor
    # ──────────────────────────────────────────────────────────────────

    def _create_orange(self, bar: int, price: float):
        """Orange: session high, shallow descending containment."""
        # Retire previous oranges
        for line in self.lines:
            if line.line_type == "ORANGE" and line.state == "ACTIVE":
                line.state = "BROKEN"
                line.broken_bar = bar

        self.lines.append(ScottLine(
            line_id=self._new_id(), line_type="ORANGE",
            anchor_bar=bar, anchor_price=price,
            slope=self._orange_slope, state="ACTIVE",
            direction="RESISTANCE", created_bar=bar,
        ))

    def _create_yellow(self, bar: int, price: float):
        """Yellow: session low, shallow ascending containment."""
        for line in self.lines:
            if line.line_type == "YELLOW" and line.state == "ACTIVE":
                line.state = "BROKEN"
                line.broken_bar = bar

        self.lines.append(ScottLine(
            line_id=self._new_id(), line_type="YELLOW",
            anchor_bar=bar, anchor_price=price,
            slope=self._yellow_slope, state="ACTIVE",
            direction="SUPPORT", created_bar=bar,
        ))

    # ──────────────────────────────────────────────────────────────────
    # SWING DETECTION
    # ──────────────────────────────────────────────────────────────────

    def _detect_swings(self, bar: int):
        """Detect confirmed swing highs and lows (1-bar confirmation)."""
        j = bar - 1  # candidate bar

        # Swing high: bar j higher than both neighbors
        h_j = self.highs[j]
        left_drop = h_j - self.highs[j - 1]
        right_drop = h_j - self.highs[bar]
        if left_drop >= self.min_swing_pts and right_drop >= self.min_swing_pts:
            prominence = (left_drop + right_drop) / 2
            self.swing_highs.append((j, h_j, prominence))

        # Swing low: bar j lower than both neighbors
        l_j = self.lows[j]
        left_rise = self.lows[j - 1] - l_j
        right_rise = self.lows[bar] - l_j
        if left_rise >= self.min_swing_pts and right_rise >= self.min_swing_pts:
            prominence = (left_rise + right_rise) / 2
            self.swing_lows.append((j, l_j, prominence))

    # ──────────────────────────────────────────────────────────────────
    # PURPLE ORIGINAL: Strategic bearish thesis
    # ──────────────────────────────────────────────────────────────────

    def _try_create_purple(self, bar: int):
        """Create purple when: session high + confirmed lower swing high.
        Slope = shallowest that stays ABOVE all highs between P1 and now."""
        if self._purple_created:
            return

        # Need at least one swing high that is LOWER than session high
        valid_p2s = [(b, p, prom) for b, p, prom in self.swing_highs
                     if b > self.session_high_bar and p < self.session_high]

        if not valid_p2s:
            return

        # Use the MOST RECENT valid swing high as P2
        p2_bar, p2_price, _ = valid_p2s[-1]

        # Compute containment slope: shallowest slope from P1 that stays
        # ABOVE all highs from P1 to current bar
        slope = self._shallowest_resistance_slope(
            self.session_high_bar, self.session_high, bar)

        if slope is None or slope >= 0:
            return  # can't create valid descending resistance

        self._purple_created = True
        self.lines.append(ScottLine(
            line_id=self._new_id(), line_type="PURPLE_ORIGINAL",
            anchor_bar=self.session_high_bar, anchor_price=self.session_high,
            slope=slope, state="ACTIVE", direction="RESISTANCE",
            created_bar=bar, p2_bar=p2_bar, p2_price=p2_price,
        ))

    # ──────────────────────────────────────────────────────────────────
    # BLUE ORIGINAL: Strategic bullish thesis
    # ──────────────────────────────────────────────────────────────────

    def _try_create_blue(self, bar: int):
        """Create blue when: session low + confirmed higher swing low.
        Slope = shallowest that stays BELOW all lows between P1 and now."""
        if self._blue_created:
            return

        valid_p2s = [(b, p, prom) for b, p, prom in self.swing_lows
                     if b > self.session_low_bar and p > self.session_low]

        if not valid_p2s:
            return

        p2_bar, p2_price, _ = valid_p2s[-1]

        slope = self._shallowest_support_slope(
            self.session_low_bar, self.session_low, bar)

        if slope is None or slope <= 0:
            return

        self._blue_created = True
        self.lines.append(ScottLine(
            line_id=self._new_id(), line_type="BLUE_ORIGINAL",
            anchor_bar=self.session_low_bar, anchor_price=self.session_low,
            slope=slope, state="ACTIVE", direction="SUPPORT",
            created_bar=bar, p2_bar=p2_bar, p2_price=p2_price,
        ))

    # ──────────────────────────────────────────────────────────────────
    # CONTINUATION BLUE: Tactical bullish evidence
    # ──────────────────────────────────────────────────────────────────

    def _try_create_continuation_blue(self, bar: int):
        """Create continuation blue from proven higher lows AFTER blue original exists."""
        if not self._blue_created:
            return
        if bar < 20:
            return

        # Find swing lows that are HIGHER than the previous continuation blue
        # (or higher than the original blue's last value)
        existing_cont = [l for l in self.lines
                         if l.line_type == "CONTINUATION_BLUE" and l.state == "ACTIVE"]

        # Get the most recent swing low
        if not self.swing_lows:
            return

        latest_sw = self.swing_lows[-1]
        sw_bar, sw_price, sw_prom = latest_sw

        # Don't create if we already have a continuation blue from this swing
        for l in existing_cont:
            if l.anchor_bar == sw_bar:
                return

        # Need at least 2 swing lows to connect
        if len(self.swing_lows) < 2:
            return

        # Find the best pair of recent swing lows (ascending)
        recent_lows = self.swing_lows[-5:]  # last 5 swing lows
        for i in range(len(recent_lows) - 1):
            p1_bar, p1_price, _ = recent_lows[i]
            p2_bar, p2_price, _ = recent_lows[-1]

            if p2_price <= p1_price:
                continue  # need ascending
            if p2_bar <= p1_bar:
                continue

            slope = self._shallowest_support_slope(p1_bar, p1_price, bar)
            if slope is None or slope <= 0:
                continue

            # Check it doesn't duplicate an existing line too closely
            duplicate = False
            for l in self.lines:
                if l.line_type == "CONTINUATION_BLUE" and l.state == "ACTIVE":
                    if abs(l.value_at(bar) - (p1_price + slope * (bar - p1_bar))) < 10:
                        duplicate = True
                        break
            if duplicate:
                continue

            self.lines.append(ScottLine(
                line_id=self._new_id(), line_type="CONTINUATION_BLUE",
                anchor_bar=p1_bar, anchor_price=p1_price,
                slope=slope, state="ACTIVE", direction="SUPPORT",
                created_bar=bar, p2_bar=p2_bar, p2_price=p2_price,
            ))
            break  # only create one per bar

    # ──────────────────────────────────────────────────────────────────
    # CONTAINMENT SLOPE COMPUTATION
    # ──────────────────────────────────────────────────────────────────

    def _shallowest_resistance_slope(self, p1_bar: int, p1_price: float,
                                      up_to_bar: int) -> Optional[float]:
        """Find the shallowest (least negative) slope from P1 that stays
        ABOVE all highs from P1+1 to up_to_bar.

        Returns None if no valid slope exists (price went above P1)."""
        max_required_slope = -1e30  # least negative = shallowest

        for i in range(p1_bar + 1, min(up_to_bar + 1, self.n_bars)):
            dt = i - p1_bar
            if dt == 0:
                continue
            # What slope would put the line exactly at this bar's high?
            required = (self.highs[i] - p1_price) / dt
            if required > max_required_slope:
                max_required_slope = required

        # Must be negative to be valid resistance
        if max_required_slope >= 0:
            return None

        # Add small buffer so line doesn't sit exactly on highs
        return max_required_slope - 0.1

    def _shallowest_support_slope(self, p1_bar: int, p1_price: float,
                                   up_to_bar: int) -> Optional[float]:
        """Find the shallowest (least positive) slope from P1 that stays
        BELOW all lows from P1+1 to up_to_bar."""
        min_required_slope = 1e30  # least positive = shallowest

        for i in range(p1_bar + 1, min(up_to_bar + 1, self.n_bars)):
            dt = i - p1_bar
            if dt == 0:
                continue
            required = (self.lows[i] - p1_price) / dt
            if required < min_required_slope:
                min_required_slope = required

        # Must be positive to be valid support
        if min_required_slope <= 0:
            return None

        # Add small buffer
        return min_required_slope + 0.1

    # ──────────────────────────────────────────────────────────────────
    # LINE STATE UPDATES
    # ──────────────────────────────────────────────────────────────────

    def _update_line_states(self, bar: int):
        """Update touches, breaks, reclaims for all active lines."""
        close = self.closes[bar]
        high = self.highs[bar]
        low = self.lows[bar]

        for line in self.lines:
            if line.state not in ("ACTIVE", "RECLAIMED"):
                # Still track broken lines for potential reclaim
                if line.state == "BROKEN":
                    line_val = line.value_at(bar)
                    if line.direction == "RESISTANCE" and close < line_val:
                        line.state = "RECLAIMED"
                        line.reclaimed_bar = bar
                    elif line.direction == "SUPPORT" and close > line_val:
                        line.state = "RECLAIMED"
                        line.reclaimed_bar = bar
                continue

            line_val = line.value_at(bar)

            # Proximity check: is price near this line?
            if line.direction == "RESISTANCE":
                dist = line_val - high
                if 0 <= dist <= 15:
                    line.interactions += 1
                    line.bars_near_price += 1
                    # Touch: approached and rejected
                    if close < line_val:
                        line.touch_count += 1

                # Break: close above resistance
                if close > line_val:
                    line.state = "BROKEN"
                    line.broken_bar = bar
                    # Adjust slope to maintain containment if only wick pierced
                    # (close above = confirmed break, no adjustment)

            elif line.direction == "SUPPORT":
                dist = low - line_val
                if 0 <= dist <= 15:
                    line.interactions += 1
                    line.bars_near_price += 1
                    if close > line_val:
                        line.touch_count += 1

                # Break: close below support
                if close < line_val:
                    line.state = "BROKEN"
                    line.broken_bar = bar

    # ──────────────────────────────────────────────────────────────────
    # WICK ADJUSTMENT (after close, if wick pierced but close held)
    # ──────────────────────────────────────────────────────────────────

    def adjust_for_wicks(self, bar: int):
        """If a wick pierced an active line but close held inside,
        adjust slope to re-encompass. Called after process_bar."""
        close = self.closes[bar]

        for line in self.lines:
            if line.state != "ACTIVE":
                continue

            line_val = line.value_at(bar)

            if line.direction == "RESISTANCE":
                # High pierced above line but close stayed below
                if self.highs[bar] > line_val and close <= line_val:
                    # Recompute slope to encompass this wick
                    new_slope = self._shallowest_resistance_slope(
                        line.anchor_bar, line.anchor_price, bar)
                    if new_slope is not None and new_slope < 0:
                        line.slope = new_slope

            elif line.direction == "SUPPORT":
                if self.lows[bar] < line_val and close >= line_val:
                    new_slope = self._shallowest_support_slope(
                        line.anchor_bar, line.anchor_price, bar)
                    if new_slope is not None and new_slope > 0:
                        line.slope = new_slope

    # ──────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────

    def run_session(self, day_data):
        """Process an entire session DataFrame."""
        for i in range(len(day_data)):
            row = day_data.iloc[i]
            self.process_bar(float(row['Open']), float(row['High']),
                           float(row['Low']), float(row['Close']))
            self.adjust_for_wicks(self.n_bars - 1)

    def get_active_lines(self) -> List[ScottLine]:
        return [l for l in self.lines if l.state in ("ACTIVE", "RECLAIMED")]

    def get_all_lines(self) -> List[ScottLine]:
        return self.lines

    def validate_containment(self) -> List[dict]:
        """Verify no active line cuts through candle bodies."""
        violations = []
        for line in self.lines:
            if line.state not in ("ACTIVE", "RECLAIMED"):
                continue
            for i in range(line.anchor_bar, self.n_bars):
                line_val = line.value_at(i)
                body_hi = max(self.opens[i], self.closes[i])
                body_lo = min(self.opens[i], self.closes[i])

                if line.direction == "RESISTANCE":
                    if line_val < body_hi:  # line cuts through body
                        violations.append({
                            'line_id': line.line_id, 'line_type': line.line_type,
                            'bar': i, 'line_val': line_val, 'body_hi': body_hi,
                        })
                elif line.direction == "SUPPORT":
                    if line_val > body_lo:
                        violations.append({
                            'line_id': line.line_id, 'line_type': line.line_type,
                            'bar': i, 'line_val': line_val, 'body_lo': body_lo,
                        })
        return violations
