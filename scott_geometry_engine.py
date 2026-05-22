"""
scott_geometry_engine.py — Universal Scott Geometry Formula

One repeatable formula. Works on every session.
No fitting to specific days. Containment is the law.

CORE RULE: A line is valid ONLY if it is a containment boundary.
- Resistance stays ABOVE all closed bars in its active window.
- Support stays BELOW all closed bars in its active window.
- No line may run through candle bodies.

FORMULA:
1. Identify confirmed swing points (min 25 pts prominence)
2. Create strategic lines (Orange, Yellow, Purple Original, Blue Original)
3. Create tactical/continuation lines only after structure is proven
4. Keep only meaningful active lines (~4-6 visible at any moment)
5. Broken lines remain visible but faded
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
    anchor_bar: int      # P1 bar
    anchor_price: float  # P1 price
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
    """Universal Scott Geometry. One formula for all sessions."""

    # Fixed parameters
    ORANGE_YELLOW_SLOPE = 1.83   # ~2.5 degrees
    MIN_SWING_DISTANCE = 15.0    # minimum prominence for a swing to matter
    MAX_USEFUL_SLOPE = 10.0      # lines steeper than this leave price too fast

    def __init__(self):
        self.lines: List[ScottLine] = []
        self._next_id = 1

        # Bar data
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

        # Confirmed swings
        self.swing_highs: List[tuple] = []  # (bar, price)
        self.swing_lows: List[tuple] = []

        # Creation flags
        self._purple_id = -1
        self._blue_id = -1
        self._orange_id = -1
        self._yellow_id = -1
        self._tactical_purple_id = -1
        self._last_cont_blue_bar = -1

    def _new_id(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i

    # ══════════════════════════════════════════════════════════════════
    # MAIN LOOP
    # ══════════════════════════════════════════════════════════════════

    def process_bar(self, open_p: float, high: float, low: float, close: float):
        bar = self.n_bars
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)
        self.opens.append(open_p)
        self.n_bars += 1

        # ── 1. Session extremes → Orange / Yellow ──
        if high > self.session_high:
            self.session_high = high
            self.session_high_bar = bar
            self._set_orange(bar, high)

        if low < self.session_low:
            self.session_low = low
            self.session_low_bar = bar
            self._set_yellow(bar, low)

        # ── 2. Detect confirmed swings (1-bar lag) ──
        if bar >= 2:
            j = bar - 1
            # Swing high
            if (self.highs[j] - self.highs[j-1] >= self.MIN_SWING_DISTANCE and
                self.highs[j] - self.highs[bar] >= self.MIN_SWING_DISTANCE):
                self.swing_highs.append((j, self.highs[j]))
            # Swing low
            if (self.lows[j-1] - self.lows[j] >= self.MIN_SWING_DISTANCE and
                self.lows[bar] - self.lows[j] >= self.MIN_SWING_DISTANCE):
                self.swing_lows.append((j, self.lows[j]))

        # ── 3. Strategic lines ──
        self._try_purple_original(bar)
        self._try_blue_original(bar)

        # ── 4. Tactical/continuation lines ──
        self._try_continuation_blue(bar)
        self._try_tactical_purple(bar)

        # ── 5. Update states (breaks, touches) ──
        self._update_states(bar)

    # ══════════════════════════════════════════════════════════════════
    # ORANGE / YELLOW — Fixed slope, from session extreme
    # ══════════════════════════════════════════════════════════════════

    def _set_orange(self, bar: int, price: float):
        """One orange. Updates in place when new session high forms."""
        if self._orange_id > 0:
            for l in self.lines:
                if l.line_id == self._orange_id:
                    l.anchor_bar = bar
                    l.anchor_price = price
                    l.state = "ACTIVE"
                    l.broken_bar = -1
                    return
        line = ScottLine(
            line_id=self._new_id(), line_type="ORANGE",
            anchor_bar=bar, anchor_price=price,
            slope=-self.ORANGE_YELLOW_SLOPE, state="ACTIVE",
            direction="RESISTANCE", created_bar=bar)
        self.lines.append(line)
        self._orange_id = line.line_id

    def _set_yellow(self, bar: int, price: float):
        """One yellow. Updates in place when new session low forms."""
        if self._yellow_id > 0:
            for l in self.lines:
                if l.line_id == self._yellow_id:
                    l.anchor_bar = bar
                    l.anchor_price = price
                    l.state = "ACTIVE"
                    l.broken_bar = -1
                    return
        line = ScottLine(
            line_id=self._new_id(), line_type="YELLOW",
            anchor_bar=bar, anchor_price=price,
            slope=+self.ORANGE_YELLOW_SLOPE, state="ACTIVE",
            direction="SUPPORT", created_bar=bar)
        self.lines.append(line)
        self._yellow_id = line.line_id

    # ══════════════════════════════════════════════════════════════════
    # PURPLE ORIGINAL — Descending resistance from session high
    # ══════════════════════════════════════════════════════════════════

    def _try_purple_original(self, bar: int):
        """Purple: descending resistance from recent swing highs.
        ALWAYS maintains an active purple near current price.
        When current purple becomes irrelevant (broken and far from price),
        create a new one from the most recent swing high pair."""
        if bar < 3:
            return
        if len(self.swing_highs) < 2:
            return

        # Check if current purple is still relevant (near price)
        current_purple = None
        if self._purple_id > 0:
            for l in self.lines:
                if l.line_id == self._purple_id:
                    current_purple = l
                    break

        need_new = False
        if current_purple is None:
            need_new = True
        elif current_purple.state == "BROKEN":
            # Is it far from current price? (irrelevant)
            purple_val = current_purple.value_at(bar)
            if abs(purple_val - self.highs[bar]) > 100:
                need_new = True

        if not need_new:
            return

        # Find the best pair of recent swing highs (descending)
        # Use the two most recent swing highs where the second is lower
        best_p1 = None
        best_p2 = None
        for i in range(len(self.swing_highs) - 1, 0, -1):
            p2_bar, p2_price = self.swing_highs[i]
            for j in range(i - 1, -1, -1):
                p1_bar, p1_price = self.swing_highs[j]
                if p1_price > p2_price:  # descending pair
                    best_p1 = (p1_bar, p1_price)
                    best_p2 = (p2_bar, p2_price)
                    break
            if best_p1:
                break

        # Also try session high as P1
        if self.session_high_bar >= 0:
            for b, p in self.swing_highs:
                if b > self.session_high_bar and p < self.session_high:
                    # Session high → lower swing high is a valid pair
                    if best_p1 is None or self.session_high > best_p1[1]:
                        best_p1 = (self.session_high_bar, self.session_high)
                        best_p2 = (b, p)
                    break

        if best_p1 is None or best_p2 is None:
            return

        # Compute containment slope
        slope = self._resistance_containment(best_p1[0], best_p1[1], bar)
        if slope is None or slope >= 0:
            return
        if slope < -self.MAX_USEFUL_SLOPE:
            return

        # Mark old purple as broken if replacing
        if current_purple and current_purple.state == "BROKEN":
            pass  # already broken, leave it

        line = ScottLine(
            line_id=self._new_id(), line_type="PURPLE_ORIGINAL",
            anchor_bar=best_p1[0], anchor_price=best_p1[1],
            slope=slope, state="ACTIVE", direction="RESISTANCE", created_bar=bar,
            p2_bar=best_p2[0], p2_price=best_p2[1])
        self.lines.append(line)
        self._purple_id = line.line_id

    # ══════════════════════════════════════════════════════════════════
    # BLUE ORIGINAL — Ascending support from session low
    # ══════════════════════════════════════════════════════════════════

    def _try_blue_original(self, bar: int):
        """Blue: ascending support from recent swing lows.
        ALWAYS maintains an active blue near current price.
        When current blue becomes irrelevant, create new from recent swing lows."""
        if bar < 3:
            return
        if len(self.swing_lows) < 2:
            return

        current_blue = None
        if self._blue_id > 0:
            for l in self.lines:
                if l.line_id == self._blue_id:
                    current_blue = l
                    break

        need_new = False
        if current_blue is None:
            need_new = True
        elif current_blue.state == "BROKEN":
            blue_val = current_blue.value_at(bar)
            if abs(blue_val - self.lows[bar]) > 100:
                need_new = True

        if not need_new:
            return

        # Find best pair of recent swing lows (ascending)
        best_p1 = None
        best_p2 = None
        for i in range(len(self.swing_lows) - 1, 0, -1):
            p2_bar, p2_price = self.swing_lows[i]
            for j in range(i - 1, -1, -1):
                p1_bar, p1_price = self.swing_lows[j]
                if p1_price < p2_price:  # ascending pair
                    best_p1 = (p1_bar, p1_price)
                    best_p2 = (p2_bar, p2_price)
                    break
            if best_p1:
                break

        # Also try session low as P1
        if self.session_low_bar >= 0:
            for b, p in self.swing_lows:
                if b > self.session_low_bar and p > self.session_low:
                    if best_p1 is None or self.session_low < best_p1[1]:
                        best_p1 = (self.session_low_bar, self.session_low)
                        best_p2 = (b, p)
                    break

        if best_p1 is None or best_p2 is None:
            return

        slope = self._support_containment(best_p1[0], best_p1[1], bar)
        if slope is None or slope <= 0:
            return
        if slope > self.MAX_USEFUL_SLOPE:
            return

        line = ScottLine(
            line_id=self._new_id(), line_type="BLUE_ORIGINAL",
            anchor_bar=best_p1[0], anchor_price=best_p1[1],
            slope=slope, state="ACTIVE", direction="SUPPORT", created_bar=bar,
            p2_bar=best_p2[0], p2_price=best_p2[1])
        self.lines.append(line)
        self._blue_id = line.line_id

    # ══════════════════════════════════════════════════════════════════
    # CONTINUATION BLUE — From proven bounce lows during resolve
    # ══════════════════════════════════════════════════════════════════

    def _try_continuation_blue(self, bar: int):
        """Created when: price makes low, bounces, resumes, confirms low mattered.
        Slope = containment (stays below all lows from anchor to now).
        If containment slope exceeds MAX_USEFUL_SLOPE, skip this line."""
        if bar < 10:
            return
        if not self.swing_lows:
            return

        latest_bar, latest_price = self.swing_lows[-1]

        if latest_bar <= self._last_cont_blue_bar:
            return
        if self._last_cont_blue_bar > 0 and latest_bar - self._last_cont_blue_bar < 5:
            return

        # Compute containment slope from this swing low
        slope = self._support_containment(latest_bar, latest_price, bar)
        if slope is None or slope <= 0:
            return
        if slope > self.MAX_USEFUL_SLOPE:
            return  # too steep, line would leave price field

        line = ScottLine(
            line_id=self._new_id(), line_type="CONTINUATION_BLUE",
            anchor_bar=latest_bar, anchor_price=latest_price,
            slope=slope, state="ACTIVE", direction="SUPPORT", created_bar=bar,
            p2_bar=latest_bar, p2_price=latest_price)
        self.lines.append(line)
        self._last_cont_blue_bar = latest_bar

    # ══════════════════════════════════════════════════════════════════
    # TACTICAL PURPLE — Steeper profit protection during resolve
    # ══════════════════════════════════════════════════════════════════

    def _try_tactical_purple(self, bar: int):
        """Created when: bounce high fails to reclaim original purple, resumes lower.
        P1 = first bounce peak below purple. Slope through subsequent lower highs.
        Must stay above all closed bars. Must be steeper than purple original."""
        if self._tactical_purple_id > 0:
            return
        if self._purple_id <= 0:
            return
        if bar < 20:
            return

        purple = None
        for l in self.lines:
            if l.line_id == self._purple_id:
                purple = l
                break
        if purple is None:
            return

        # Need price well below purple (resolve is active)
        if purple.value_at(bar) - self.highs[bar] < 30:
            return

        # Find swing highs below purple (bounce peaks during resolve)
        peaks_below = [(b, p) for b, p in self.swing_highs
                       if b > purple.anchor_bar + 3 and p <= purple.value_at(b) + 2]

        if len(peaks_below) < 2:
            return

        # Try each peak as P1, use next peak as P2
        for i in range(len(peaks_below) - 1):
            p1_bar, p1_price = peaks_below[i]
            p2_bar, p2_price = peaks_below[i + 1]

            if p2_price >= p1_price:
                continue  # need descending

            # Compute slope from P1 to P2
            dt = p2_bar - p1_bar
            if dt <= 0:
                continue
            slope = (p2_price - p1_price) / dt

            if slope >= 0 or slope >= purple.slope:
                continue  # must be steeper (more negative) than purple

            # Verify containment from P1 to current bar
            valid = True
            for k in range(p1_bar + 1, self.n_bars):
                lv = p1_price + slope * (k - p1_bar)
                if self.highs[k] > lv + 2:
                    # Containment violated — recompute
                    slope = self._resistance_containment(p1_bar, p1_price, bar)
                    if slope is None or slope >= 0 or slope >= purple.slope:
                        valid = False
                    break

            if not valid:
                continue
            if slope < -self.MAX_USEFUL_SLOPE:
                continue

            line = ScottLine(
                line_id=self._new_id(), line_type="TACTICAL_PURPLE",
                anchor_bar=p1_bar, anchor_price=p1_price,
                slope=slope, state="ACTIVE", direction="RESISTANCE", created_bar=bar,
                p2_bar=p2_bar, p2_price=p2_price)
            self.lines.append(line)
            self._tactical_purple_id = line.line_id
            return

    # ══════════════════════════════════════════════════════════════════
    # CONTAINMENT SLOPE COMPUTATION
    # ══════════════════════════════════════════════════════════════════

    def _resistance_containment(self, p1_bar: int, p1_price: float,
                                 up_to_bar: int) -> Optional[float]:
        """Shallowest slope from P1 that stays ABOVE all highs."""
        max_slope = -1e30
        for i in range(p1_bar + 1, min(up_to_bar + 1, self.n_bars)):
            dt = i - p1_bar
            required = (self.highs[i] - p1_price) / dt
            if required > max_slope:
                max_slope = required
        if max_slope >= 0:
            return None
        return max_slope

    def _support_containment(self, p1_bar: int, p1_price: float,
                              up_to_bar: int) -> Optional[float]:
        """Shallowest slope from P1 that stays BELOW all lows."""
        min_slope = 1e30
        for i in range(p1_bar + 1, min(up_to_bar + 1, self.n_bars)):
            dt = i - p1_bar
            required = (self.lows[i] - p1_price) / dt
            if required < min_slope:
                min_slope = required
        if min_slope <= 0:
            return None
        return min_slope

    # ══════════════════════════════════════════════════════════════════
    # STATE UPDATES
    # ══════════════════════════════════════════════════════════════════

    def _update_states(self, bar: int):
        """Check breaks, touches, reclaims."""
        close = self.closes[bar]
        high = self.highs[bar]
        low = self.lows[bar]

        for line in self.lines:
            lv = line.value_at(bar)

            if line.state == "BROKEN":
                # Check for reclaim
                if line.direction == "RESISTANCE" and close < lv:
                    line.state = "RECLAIMED"
                    line.reclaimed_bar = bar
                elif line.direction == "SUPPORT" and close > lv:
                    line.state = "RECLAIMED"
                    line.reclaimed_bar = bar
                continue

            if line.state not in ("ACTIVE", "RECLAIMED"):
                continue

            if line.direction == "RESISTANCE":
                # Touch: high within 10 pts, close below
                if 0 <= lv - high <= 10 and close < lv:
                    line.touch_count += 1
                # Break: close above
                if close > lv:
                    line.state = "BROKEN"
                    line.broken_bar = bar
            elif line.direction == "SUPPORT":
                if 0 <= low - lv <= 10 and close > lv:
                    line.touch_count += 1
                if close < lv:
                    line.state = "BROKEN"
                    line.broken_bar = bar

    # ══════════════════════════════════════════════════════════════════
    # PUBLIC API
    # ══════════════════════════════════════════════════════════════════

    def run_session(self, day_data):
        for i in range(len(day_data)):
            row = day_data.iloc[i]
            self.process_bar(float(row['Open']), float(row['High']),
                           float(row['Low']), float(row['Close']))

    def get_active_lines(self) -> List[ScottLine]:
        return [l for l in self.lines if l.state in ("ACTIVE", "RECLAIMED")]

    def get_all_lines(self) -> List[ScottLine]:
        return self.lines
