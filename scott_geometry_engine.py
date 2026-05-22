"""
scott_geometry_engine.py — Universal Scott Geometry

TWO tiers of lines:
STRATEGIC: Orange/Yellow from session extremes (big picture)
LOCAL: Purple/Blue from recent swing structure within rolling window (active argument)

Swing detection: rolling window of last 20 bars. Find highest high and lowest low
within that window. When a new swing confirms, update local lines.

All lines maintain containment. Wick adjusts slope. Horizontal = removed.
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ScottLine:
    line_id: int
    line_type: str
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
    LOCAL_WINDOW = 20  # bars to look back for local swing structure

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
        self._orange_id = -1
        self._yellow_id = -1
        # Strategic purple/blue: from session extremes, wick adjusts until horizontal
        self._strategic_purple_id = -1
        self._strategic_blue_id = -1
        # Local purple/blue: from recent swings within rolling window
        self._local_purple_id = -1
        self._local_blue_id = -1

    def _new_id(self):
        i = self._next_id
        self._next_id += 1
        return i

    def _get(self, lid):
        for l in self.lines:
            if l.line_id == lid:
                return l
        return None

    # ══════════════════════════════════════════════════════════════════
    # MAIN
    # ══════════════════════════════════════════════════════════════════

    def process_bar(self, open_p: float, high: float, low: float, close: float):
        bar = self.n_bars
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)
        self.opens.append(open_p)
        self.n_bars += 1

        # Orange/Yellow
        if high > self.session_high:
            self.session_high = high
            self.session_high_bar = bar
            self._set_orange(bar, high)
        if low < self.session_low:
            self.session_low = low
            self.session_low_bar = bar
            self._set_yellow(bar, low)

        # Wick adjust all active lines
        self._wick_adjust_orange(bar)
        self._wick_adjust_yellow(bar)
        self._wick_adjust_line(self._strategic_purple_id, bar)
        self._wick_adjust_line(self._strategic_blue_id, bar)
        self._wick_adjust_line(self._local_purple_id, bar)
        self._wick_adjust_line(self._local_blue_id, bar)

        # Break check
        self._check_breaks(bar)

        # Strategic purple/blue: from session high/low, created once
        if self._strategic_purple_id <= 0 and bar >= 5:
            self._create_strategic_purple(bar)
        if self._strategic_blue_id <= 0 and bar >= 5:
            self._create_strategic_blue(bar)

        # Local purple/blue: from recent swings, update every 5 bars
        if bar >= self.LOCAL_WINDOW and bar % 5 == 0:
            self._update_local_purple(bar)
            self._update_local_blue(bar)

        # Touches
        self._check_touches(bar)

    # ══════════════════════════════════════════════════════════════════
    # ORANGE / YELLOW
    # ══════════════════════════════════════════════════════════════════

    def _set_orange(self, bar, price):
        if self._orange_id > 0:
            l = self._get(self._orange_id)
            if l:
                l.anchor_bar = bar
                l.anchor_price = price
                l.slope = -self.ORANGE_YELLOW_SLOPE
                l.state = "ACTIVE"
                return
        line = ScottLine(self._new_id(), "ORANGE", bar, price,
                         -self.ORANGE_YELLOW_SLOPE, "ACTIVE", "RESISTANCE", bar)
        self.lines.append(line)
        self._orange_id = line.line_id

    def _set_yellow(self, bar, price):
        if self._yellow_id > 0:
            l = self._get(self._yellow_id)
            if l:
                l.anchor_bar = bar
                l.anchor_price = price
                l.slope = +self.ORANGE_YELLOW_SLOPE
                l.state = "ACTIVE"
                return
        line = ScottLine(self._new_id(), "YELLOW", bar, price,
                         +self.ORANGE_YELLOW_SLOPE, "ACTIVE", "SUPPORT", bar)
        self.lines.append(line)
        self._yellow_id = line.line_id

    def _wick_adjust_orange(self, bar):
        orange = self._get(self._orange_id) if self._orange_id > 0 else None
        if not orange or orange.state != "ACTIVE":
            return
        lv = orange.value_at(bar)
        if self.highs[bar] > lv:
            new_slope = self._resistance_slope(orange.anchor_bar, orange.anchor_price, bar)
            if new_slope is None or new_slope >= 0:
                # Past horizontal — re-anchor at current bar's high
                orange.anchor_bar = bar
                orange.anchor_price = self.highs[bar]
                orange.slope = -self.ORANGE_YELLOW_SLOPE
            else:
                orange.slope = new_slope

    def _wick_adjust_yellow(self, bar):
        yellow = self._get(self._yellow_id) if self._yellow_id > 0 else None
        if not yellow or yellow.state != "ACTIVE":
            return
        lv = yellow.value_at(bar)
        if self.lows[bar] < lv:
            new_slope = self._support_slope(yellow.anchor_bar, yellow.anchor_price, bar)
            if new_slope is None or new_slope <= 0:
                yellow.anchor_bar = bar
                yellow.anchor_price = self.lows[bar]
                yellow.slope = +self.ORANGE_YELLOW_SLOPE
            else:
                yellow.slope = new_slope

    # ══════════════════════════════════════════════════════════════════
    # LOCAL PURPLE / BLUE — From rolling window of recent swings
    # ══════════════════════════════════════════════════════════════════

    def _create_local_purple(self, bar):
        """Create purple from the most recent descending swing high pair.
        BUT: if a previous purple existed from a higher anchor, reuse that anchor."""
        window_start = max(0, bar - self.LOCAL_WINDOW * 2)

        # Check if there's a previous purple we should reuse the anchor from
        best_old_anchor = None
        for l in self.lines:
            if l.line_type == "PURPLE" and l.state == "BROKEN":
                if best_old_anchor is None or l.anchor_price > best_old_anchor[1]:
                    best_old_anchor = (l.anchor_bar, l.anchor_price)

        if best_old_anchor:
            slope = self._resistance_slope(best_old_anchor[0], best_old_anchor[1], bar)
            if slope is not None and slope < 0:
                line = ScottLine(self._new_id(), "PURPLE", best_old_anchor[0], best_old_anchor[1],
                                 slope, "ACTIVE", "RESISTANCE", bar,
                                 p2_bar=bar, p2_price=self.highs[bar])
                self.lines.append(line)
                self._purple_id = line.line_id
                return

        # No previous anchor — find from rolling window
        local_highs = []
        for i in range(window_start + 1, bar - 1):
            if self.highs[i] > self.highs[i-1] and self.highs[i] > self.highs[i+1]:
                local_highs.append((i, self.highs[i]))

        if len(local_highs) < 2:
            return

        p2_bar, p2_price = local_highs[-1]
        best_p1 = None
        for i in range(len(local_highs) - 2, -1, -1):
            p1_bar, p1_price = local_highs[i]
            if p1_price > p2_price:
                best_p1 = (p1_bar, p1_price)
                break

        if best_p1 is None:
            return

        slope = self._resistance_slope(best_p1[0], best_p1[1], bar)
        if slope is None or slope >= 0:
            return

        line = ScottLine(self._new_id(), "PURPLE", best_p1[0], best_p1[1],
                         slope, "ACTIVE", "RESISTANCE", bar,
                         p2_bar=p2_bar, p2_price=p2_price)
        self.lines.append(line)
        self._purple_id = line.line_id

    def _create_local_blue(self, bar):
        """Create blue from the most recent ascending swing low pair
        within the rolling window. BUT: if a previous blue existed from a lower
        anchor, reuse that anchor (just recompute slope)."""
        window_start = max(0, bar - self.LOCAL_WINDOW * 2)

        # Check if there's a previous blue we should reuse the anchor from
        # (the lowest anchor from any previous blue that hasn't been REMOVED)
        best_old_anchor = None
        for l in self.lines:
            if l.line_type == "BLUE" and l.state == "BROKEN":
                if best_old_anchor is None or l.anchor_price < best_old_anchor[1]:
                    best_old_anchor = (l.anchor_bar, l.anchor_price)

        if best_old_anchor:
            # Reuse the old anchor — just compute new containment slope
            slope = self._support_slope(best_old_anchor[0], best_old_anchor[1], bar)
            if slope is not None and slope > 0:
                line = ScottLine(self._new_id(), "BLUE", best_old_anchor[0], best_old_anchor[1],
                                 slope, "ACTIVE", "SUPPORT", bar,
                                 p2_bar=bar, p2_price=self.lows[bar])
                self.lines.append(line)
                self._blue_id = line.line_id
                return

        # No previous anchor — find from rolling window
        local_lows = []
        for i in range(window_start + 1, bar - 1):
            if self.lows[i] < self.lows[i-1] and self.lows[i] < self.lows[i+1]:
                local_lows.append((i, self.lows[i]))

        if len(local_lows) < 2:
            return

        p2_bar, p2_price = local_lows[-1]
        best_p1 = None
        for i in range(len(local_lows) - 2, -1, -1):
            p1_bar, p1_price = local_lows[i]
            if p1_price < p2_price:
                best_p1 = (p1_bar, p1_price)
                break

        if best_p1 is None:
            return

        slope = self._support_slope(best_p1[0], best_p1[1], bar)
        if slope is None or slope <= 0:
            return

        line = ScottLine(self._new_id(), "BLUE", best_p1[0], best_p1[1],
                         slope, "ACTIVE", "SUPPORT", bar,
                         p2_bar=p2_bar, p2_price=p2_price)
        self.lines.append(line)
        self._blue_id = line.line_id

    # ══════════════════════════════════════════════════════════════════
    # WICK ADJUST PURPLE / BLUE
    # ══════════════════════════════════════════════════════════════════

    def _wick_adjust_purple(self, bar):
        purple = self._get(self._purple_id) if self._purple_id > 0 else None
        if not purple or purple.state != "ACTIVE":
            return
        lv = purple.value_at(bar)
        if self.highs[bar] > lv and self.closes[bar] <= lv:
            new_slope = self._resistance_slope(purple.anchor_bar, purple.anchor_price, bar)
            if new_slope is None or new_slope >= 0:
                purple.state = "REMOVED"
                self._purple_id = -1
            else:
                purple.slope = new_slope

    def _wick_adjust_blue(self, bar):
        blue = self._get(self._blue_id) if self._blue_id > 0 else None
        if not blue or blue.state != "ACTIVE":
            return
        lv = blue.value_at(bar)
        if self.lows[bar] < lv and self.closes[bar] >= lv:
            new_slope = self._support_slope(blue.anchor_bar, blue.anchor_price, bar)
            if new_slope is None or new_slope <= 0:
                blue.state = "REMOVED"
                self._blue_id = -1
            else:
                blue.slope = new_slope

    # ══════════════════════════════════════════════════════════════════
    # BREAK CHECK
    # ══════════════════════════════════════════════════════════════════

    def _check_breaks(self, bar):
        close = self.closes[bar]
        for line in self.lines:
            if line.state != "ACTIVE":
                continue
            if line.line_type in ("ORANGE", "YELLOW"):
                continue
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
    # CONTAINMENT
    # ══════════════════════════════════════════════════════════════════

    def _resistance_slope(self, p1_bar, p1_price, up_to_bar):
        max_s = -1e30
        for i in range(p1_bar + 1, min(up_to_bar + 1, self.n_bars)):
            s = (self.highs[i] - p1_price) / (i - p1_bar)
            if s > max_s:
                max_s = s
        return max_s if max_s < 0 else None

    def _support_slope(self, p1_bar, p1_price, up_to_bar):
        min_s = 1e30
        for i in range(p1_bar + 1, min(up_to_bar + 1, self.n_bars)):
            s = (self.lows[i] - p1_price) / (i - p1_bar)
            if s < min_s:
                min_s = s
        return min_s if min_s > 0 else None

    # ══════════════════════════════════════════════════════════════════
    # TOUCHES
    # ══════════════════════════════════════════════════════════════════

    def _check_touches(self, bar):
        for line in self.lines:
            if line.state != "ACTIVE":
                continue
            lv = line.value_at(bar)
            if line.direction == "RESISTANCE":
                if 0 <= lv - self.highs[bar] <= 10 and self.closes[bar] < lv:
                    line.touch_count += 1
            elif line.direction == "SUPPORT":
                if 0 <= self.lows[bar] - lv <= 10 and self.closes[bar] > lv:
                    line.touch_count += 1

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
