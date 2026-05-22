"""
scott_geometry_engine.py — Universal Scott Geometry

CORE RULES:
- ONE orange, ONE yellow (session extremes, fixed slope)
- ONE purple (descending resistance, adjusts slope via wicks until horizontal → removed → renew)
- ONE blue (ascending support, adjusts slope via wicks until horizontal → removed → renew)
- 1-3 tactical/continuation lines after structure proves itself
- Lines NEVER go through candle bodies
- Wicks adjust slope. Only CLOSE beyond = break.
- Line removed only when slope goes horizontal or past horizontal.
- Minimum swing distance: 25 pts
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ScottLine:
    line_id: int
    line_type: str       # ORANGE, YELLOW, PURPLE, BLUE, TACTICAL_PURPLE, CONTINUATION_BLUE
    anchor_bar: int
    anchor_price: float
    slope: float
    state: str           # ACTIVE, BROKEN, REMOVED
    direction: str       # RESISTANCE or SUPPORT
    created_bar: int
    p2_bar: int = -1
    p2_price: float = 0.0
    touch_count: int = 0
    broken_bar: int = -1

    def value_at(self, bar: int) -> float:
        return self.anchor_price + self.slope * (bar - self.anchor_bar)


class ScottGeometryEngine:
    ORANGE_YELLOW_SLOPE = 1.83
    MIN_SWING_PTS = 25.0
    MAX_SLOPE = 12.0

    def __init__(self):
        self.lines: List[ScottLine] = []
        self._next_id = 1
        self.highs: List[float] = []
        self.lows: List[float] = []
        self.closes: List[float] = []
        self.opens: List[float] = []
        self.n_bars = 0
        self.session_high = -1e30
        self.session_high_bar = -1
        self.session_low = 1e30
        self.session_low_bar = -1
        self.swing_highs: List[tuple] = []  # (bar, price)
        self.swing_lows: List[tuple] = []
        # Active line IDs (one per role)
        self._orange_id = -1
        self._yellow_id = -1
        self._purple_id = -1
        self._blue_id = -1

    def _new_id(self):
        i = self._next_id
        self._next_id += 1
        return i

    def _get_line(self, line_id):
        for l in self.lines:
            if l.line_id == line_id:
                return l
        return None

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

        # 1. Session extremes → Orange/Yellow
        if high > self.session_high:
            self.session_high = high
            self.session_high_bar = bar
            self._set_orange(bar, high)
        if low < self.session_low:
            self.session_low = low
            self.session_low_bar = bar
            self._set_yellow(bar, low)

        # 2. Detect swings (1-bar confirmation)
        if bar >= 2:
            j = bar - 1
            if (self.highs[j] - self.highs[j-1] >= self.MIN_SWING_PTS and
                self.highs[j] - self.highs[bar] >= self.MIN_SWING_PTS):
                self.swing_highs.append((j, self.highs[j]))
            if (self.lows[j-1] - self.lows[j] >= self.MIN_SWING_PTS and
                self.lows[bar] - self.lows[j] >= self.MIN_SWING_PTS):
                self.swing_lows.append((j, self.lows[j]))

        # 3. Wick adjustments on active purple/blue (BEFORE break check)
        self._adjust_purple_wick(bar)
        self._adjust_blue_wick(bar)

        # 4. Break check (close beyond line)
        self._check_breaks(bar)

        # 5. Try to create/renew purple and blue
        self._ensure_purple(bar)
        self._ensure_blue(bar)

        # 6. Touches
        self._check_touches(bar)

    # ══════════════════════════════════════════════════════════════════
    # ORANGE / YELLOW
    # ══════════════════════════════════════════════════════════════════

    def _set_orange(self, bar, price):
        if self._orange_id > 0:
            l = self._get_line(self._orange_id)
            if l:
                l.anchor_bar = bar
                l.anchor_price = price
                l.state = "ACTIVE"
                l.broken_bar = -1
                return
        line = ScottLine(self._new_id(), "ORANGE", bar, price,
                         -self.ORANGE_YELLOW_SLOPE, "ACTIVE", "RESISTANCE", bar)
        self.lines.append(line)
        self._orange_id = line.line_id

    def _set_yellow(self, bar, price):
        if self._yellow_id > 0:
            l = self._get_line(self._yellow_id)
            if l:
                l.anchor_bar = bar
                l.anchor_price = price
                l.state = "ACTIVE"
                l.broken_bar = -1
                return
        line = ScottLine(self._new_id(), "YELLOW", bar, price,
                         +self.ORANGE_YELLOW_SLOPE, "ACTIVE", "SUPPORT", bar)
        self.lines.append(line)
        self._yellow_id = line.line_id

    # ══════════════════════════════════════════════════════════════════
    # PURPLE — Wick adjustment, break, removal, renewal
    # ══════════════════════════════════════════════════════════════════

    def _adjust_purple_wick(self, bar):
        """If high pushes above purple but close stays below: adjust slope.
        If slope becomes >= 0 (horizontal or ascending): REMOVE the line."""
        purple = self._get_line(self._purple_id) if self._purple_id > 0 else None
        if purple is None or purple.state != "ACTIVE":
            return

        lv = purple.value_at(bar)
        high = self.highs[bar]
        close = self.closes[bar]

        if high > lv and close <= lv:
            # Wick pierced — recompute shallowest containment slope
            new_slope = self._shallowest_resistance(purple.anchor_bar, purple.anchor_price, bar)
            if new_slope is None or new_slope >= 0:
                # Can't maintain descending — remove
                purple.state = "REMOVED"
                self._purple_id = -1
            else:
                purple.slope = new_slope

    def _adjust_blue_wick(self, bar):
        """If low pushes below blue but close stays above: adjust slope.
        If slope becomes <= 0 (horizontal or descending): REMOVE the line."""
        blue = self._get_line(self._blue_id) if self._blue_id > 0 else None
        if blue is None or blue.state != "ACTIVE":
            return

        lv = blue.value_at(bar)
        low = self.lows[bar]
        close = self.closes[bar]

        if low < lv and close >= lv:
            new_slope = self._shallowest_support(blue.anchor_bar, blue.anchor_price, bar)
            if new_slope is None or new_slope <= 0:
                blue.state = "REMOVED"
                self._blue_id = -1
            else:
                blue.slope = new_slope

    # ══════════════════════════════════════════════════════════════════
    # BREAK CHECK — Close beyond line
    # ══════════════════════════════════════════════════════════════════

    def _check_breaks(self, bar):
        close = self.closes[bar]
        for line in self.lines:
            if line.state != "ACTIVE":
                continue
            if line.line_type in ("ORANGE", "YELLOW"):
                continue  # orange/yellow don't break, they update on new extremes
            lv = line.value_at(bar)
            if line.direction == "RESISTANCE" and close > lv:
                line.state = "BROKEN"
                line.broken_bar = bar
                if line.line_id == self._purple_id:
                    self._purple_id = -1
            elif line.direction == "SUPPORT" and close < lv:
                line.state = "BROKEN"
                line.broken_bar = bar
                if line.line_id == self._blue_id:
                    self._blue_id = -1

    # ══════════════════════════════════════════════════════════════════
    # ENSURE PURPLE/BLUE — Create or renew when missing
    # ══════════════════════════════════════════════════════════════════

    def _ensure_purple(self, bar):
        """If no active purple exists AND a new swing high has formed since last purple broke,
        create one from the best available swing pair."""
        if self._purple_id > 0:
            return

        # Don't renew on the same bar as a break — wait for new structure
        last_broken_purple = None
        for l in reversed(self.lines):
            if l.line_type == "PURPLE" and l.state == "BROKEN":
                last_broken_purple = l
                break

        if last_broken_purple:
            # Need a new swing high AFTER the break to justify renewal
            new_swings_after_break = [(b, p) for b, p in self.swing_highs if b > last_broken_purple.broken_bar]
            if not new_swings_after_break:
                return  # wait for new structure

        # Find best descending swing high pair
        anchor = None
        p2 = None

        # Try session high → first lower swing high
        for b, p in self.swing_highs:
            if b > self.session_high_bar and p < self.session_high:
                anchor = (self.session_high_bar, self.session_high)
                p2 = (b, p)
                break

        # Fallback: most recent descending pair
        if anchor is None and len(self.swing_highs) >= 2:
            for i in range(len(self.swing_highs) - 1, 0, -1):
                b2, p2_price = self.swing_highs[i]
                for j in range(i - 1, -1, -1):
                    b1, p1_price = self.swing_highs[j]
                    if p1_price > p2_price:
                        anchor = (b1, p1_price)
                        p2 = (b2, p2_price)
                        break
                if anchor:
                    break

        if anchor is None or p2 is None:
            return

        slope = self._shallowest_resistance(anchor[0], anchor[1], bar)
        if slope is None or slope >= 0 or slope < -self.MAX_SLOPE:
            return

        line = ScottLine(self._new_id(), "PURPLE", anchor[0], anchor[1],
                         slope, "ACTIVE", "RESISTANCE", bar,
                         p2_bar=p2[0], p2_price=p2[1])
        self.lines.append(line)
        self._purple_id = line.line_id

    def _ensure_blue(self, bar):
        """If no active blue exists AND a new swing low has formed since last blue broke,
        create one from the best available swing pair."""
        if self._blue_id > 0:
            return

        last_broken_blue = None
        for l in reversed(self.lines):
            if l.line_type == "BLUE" and l.state == "BROKEN":
                last_broken_blue = l
                break

        if last_broken_blue:
            new_swings_after_break = [(b, p) for b, p in self.swing_lows if b > last_broken_blue.broken_bar]
            if not new_swings_after_break:
                return

        anchor = None
        p2 = None

        # Try session low → first higher swing low
        for b, p in self.swing_lows:
            if b > self.session_low_bar and p > self.session_low:
                anchor = (self.session_low_bar, self.session_low)
                p2 = (b, p)
                break

        # Fallback: most recent ascending pair
        if anchor is None and len(self.swing_lows) >= 2:
            for i in range(len(self.swing_lows) - 1, 0, -1):
                b2, p2_price = self.swing_lows[i]
                for j in range(i - 1, -1, -1):
                    b1, p1_price = self.swing_lows[j]
                    if p1_price < p2_price:
                        anchor = (b1, p1_price)
                        p2 = (b2, p2_price)
                        break
                if anchor:
                    break

        if anchor is None or p2 is None:
            return

        slope = self._shallowest_support(anchor[0], anchor[1], bar)
        if slope is None or slope <= 0 or slope > self.MAX_SLOPE:
            return

        line = ScottLine(self._new_id(), "BLUE", anchor[0], anchor[1],
                         slope, "ACTIVE", "SUPPORT", bar,
                         p2_bar=p2[0], p2_price=p2[1])
        self.lines.append(line)
        self._blue_id = line.line_id

    # ══════════════════════════════════════════════════════════════════
    # TOUCHES
    # ══════════════════════════════════════════════════════════════════

    def _check_touches(self, bar):
        high = self.highs[bar]
        low = self.lows[bar]
        close = self.closes[bar]
        for line in self.lines:
            if line.state != "ACTIVE":
                continue
            lv = line.value_at(bar)
            if line.direction == "RESISTANCE":
                if 0 <= lv - high <= 10 and close < lv:
                    line.touch_count += 1
            elif line.direction == "SUPPORT":
                if 0 <= low - lv <= 10 and close > lv:
                    line.touch_count += 1

    # ══════════════════════════════════════════════════════════════════
    # CONTAINMENT SLOPE
    # ══════════════════════════════════════════════════════════════════

    def _shallowest_resistance(self, p1_bar, p1_price, up_to_bar):
        """Shallowest (least negative) slope staying ABOVE all highs."""
        max_slope = -1e30
        for i in range(p1_bar + 1, min(up_to_bar + 1, self.n_bars)):
            required = (self.highs[i] - p1_price) / (i - p1_bar)
            if required > max_slope:
                max_slope = required
        return max_slope if max_slope < 0 else None

    def _shallowest_support(self, p1_bar, p1_price, up_to_bar):
        """Shallowest (least positive) slope staying BELOW all lows."""
        min_slope = 1e30
        for i in range(p1_bar + 1, min(up_to_bar + 1, self.n_bars)):
            required = (self.lows[i] - p1_price) / (i - p1_bar)
            if required < min_slope:
                min_slope = required
        return min_slope if min_slope > 0 else None

    # ══════════════════════════════════════════════════════════════════
    # PUBLIC
    # ══════════════════════════════════════════════════════════════════

    def run_session(self, day_data):
        for i in range(len(day_data)):
            row = day_data.iloc[i]
            self.process_bar(float(row['Open']), float(row['High']),
                           float(row['Low']), float(row['Close']))

    def get_all_lines(self):
        return self.lines

    def get_active_lines(self):
        return [l for l in self.lines if l.state == "ACTIVE"]
