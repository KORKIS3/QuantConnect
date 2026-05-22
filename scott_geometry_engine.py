"""
scott_geometry_engine.py — Universal Scott Geometry

Multiple simultaneous lines. Steeper recent = triggers. Shallower older = targets.
Every valid swing pair creates a line. All lines maintain containment.
Lines near current price are most relevant.
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ScottLine:
    line_id: int
    line_type: str       # ORANGE, YELLOW, PURPLE, BLUE
    anchor_bar: int
    anchor_price: float
    slope: float
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
    """Every valid swing pair creates a containment line.
    Multiple purples and blues coexist. Recent steep = triggers. Old shallow = targets."""

    ORANGE_YELLOW_SLOPE = 1.83
    MIN_SWING_PTS = 15.0
    MAX_SLOPE = 10.0

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
        self.swing_highs: List[tuple] = []
        self.swing_lows: List[tuple] = []
        self._orange_id = -1
        self._yellow_id = -1
        self._purple_pairs_created = set()  # track (p1_bar, p2_bar) to avoid duplicates
        self._blue_pairs_created = set()

    def _new_id(self):
        i = self._next_id
        self._next_id += 1
        return i

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

        # Detect swings
        if bar >= 2:
            j = bar - 1
            if (self.highs[j] - self.highs[j-1] >= self.MIN_SWING_PTS and
                self.highs[j] - self.highs[bar] >= self.MIN_SWING_PTS):
                self.swing_highs.append((j, self.highs[j]))
                self._create_purples_from_new_swing_high(bar)
            if (self.lows[j-1] - self.lows[j] >= self.MIN_SWING_PTS and
                self.lows[bar] - self.lows[j] >= self.MIN_SWING_PTS):
                self.swing_lows.append((j, self.lows[j]))
                self._create_blues_from_new_swing_low(bar)

        # Update states
        self._update_states(bar)

    # ── ORANGE / YELLOW ──

    def _set_orange(self, bar, price):
        if self._orange_id > 0:
            for l in self.lines:
                if l.line_id == self._orange_id:
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
            for l in self.lines:
                if l.line_id == self._yellow_id:
                    l.anchor_bar = bar
                    l.anchor_price = price
                    l.state = "ACTIVE"
                    l.broken_bar = -1
                    return
        line = ScottLine(self._new_id(), "YELLOW", bar, price,
                         +self.ORANGE_YELLOW_SLOPE, "ACTIVE", "SUPPORT", bar)
        self.lines.append(line)
        self._yellow_id = line.line_id

    # ── PURPLE: from every valid descending swing high pair ──

    def _create_purples_from_new_swing_high(self, bar):
        """When a new swing high is confirmed:
        1. Create purple from this swing high alone (containment from this peak)
        2. Also pair with earlier HIGHER swing highs (descending pairs)"""
        if len(self.swing_highs) < 1:
            return

        new_bar, new_price = self.swing_highs[-1]

        # Always create a purple from this swing high alone
        # (containment slope from this peak forward)
        solo_key = (new_bar, new_bar)
        if solo_key not in self._purple_pairs_created:
            slope = self._resistance_containment(new_bar, new_price, bar)
            if slope is not None and slope < 0 and slope >= -self.MAX_SLOPE:
                self._purple_pairs_created.add(solo_key)
                self.lines.append(ScottLine(
                    self._new_id(), "PURPLE", new_bar, new_price,
                    slope, "ACTIVE", "RESISTANCE", bar,
                    p2_bar=new_bar, p2_price=new_price))

        # Also pair with earlier higher swing highs (descending pairs)
        if len(self.swing_highs) >= 2:
            for i in range(len(self.swing_highs) - 2, -1, -1):
                p1_bar, p1_price = self.swing_highs[i]
                if p1_price <= new_price:
                    continue

                pair_key = (p1_bar, new_bar)
                if pair_key in self._purple_pairs_created:
                    continue

                slope = self._resistance_containment(p1_bar, p1_price, bar)
                if slope is None or slope >= 0 or slope < -self.MAX_SLOPE:
                    continue

                self._purple_pairs_created.add(pair_key)
                self.lines.append(ScottLine(
                    self._new_id(), "PURPLE", p1_bar, p1_price,
                    slope, "ACTIVE", "RESISTANCE", bar,
                    p2_bar=new_bar, p2_price=new_price))

        # Also pair with session high
        if self.session_high > new_price and self.session_high_bar < new_bar:
            pair_key = (self.session_high_bar, new_bar)
            if pair_key not in self._purple_pairs_created:
                slope = self._resistance_containment(self.session_high_bar, self.session_high, bar)
                if slope is not None and slope < 0 and slope >= -self.MAX_SLOPE:
                    self._purple_pairs_created.add(pair_key)
                    self.lines.append(ScottLine(
                        self._new_id(), "PURPLE", self.session_high_bar, self.session_high,
                        slope, "ACTIVE", "RESISTANCE", bar,
                        p2_bar=new_bar, p2_price=new_price))

    # ── BLUE: from every valid ascending swing low pair ──

    def _create_blues_from_new_swing_low(self, bar):
        """When a new swing low is confirmed:
        1. Create blue from this swing low alone (containment from this trough)
        2. Also pair with earlier LOWER swing lows (ascending pairs)"""
        if len(self.swing_lows) < 1:
            return

        new_bar, new_price = self.swing_lows[-1]

        # Always create a blue from this swing low alone
        solo_key = (new_bar, new_bar)
        if solo_key not in self._blue_pairs_created:
            slope = self._support_containment(new_bar, new_price, bar)
            if slope is not None and slope > 0 and slope <= self.MAX_SLOPE:
                self._blue_pairs_created.add(solo_key)
                self.lines.append(ScottLine(
                    self._new_id(), "BLUE", new_bar, new_price,
                    slope, "ACTIVE", "SUPPORT", bar,
                    p2_bar=new_bar, p2_price=new_price))

        # Also pair with earlier lower swing lows (ascending pairs)
        if len(self.swing_lows) >= 2:
            for i in range(len(self.swing_lows) - 2, -1, -1):
                p1_bar, p1_price = self.swing_lows[i]
                if p1_price >= new_price:
                    continue

                pair_key = (p1_bar, new_bar)
                if pair_key in self._blue_pairs_created:
                    continue

                slope = self._support_containment(p1_bar, p1_price, bar)
                if slope is None or slope <= 0 or slope > self.MAX_SLOPE:
                    continue

                self._blue_pairs_created.add(pair_key)
                self.lines.append(ScottLine(
                    self._new_id(), "BLUE", p1_bar, p1_price,
                    slope, "ACTIVE", "SUPPORT", bar,
                    p2_bar=new_bar, p2_price=new_price))

        # Also pair with session low
        if self.session_low < new_price and self.session_low_bar < new_bar:
            pair_key = (self.session_low_bar, new_bar)
            if pair_key not in self._blue_pairs_created:
                slope = self._support_containment(self.session_low_bar, self.session_low, bar)
                if slope is not None and slope > 0 and slope <= self.MAX_SLOPE:
                    self._blue_pairs_created.add(pair_key)
                    self.lines.append(ScottLine(
                        self._new_id(), "BLUE", self.session_low_bar, self.session_low,
                        slope, "ACTIVE", "SUPPORT", bar,
                        p2_bar=new_bar, p2_price=new_price))

    # ── CONTAINMENT ──

    def _resistance_containment(self, p1_bar, p1_price, up_to_bar):
        max_slope = -1e30
        for i in range(p1_bar + 1, min(up_to_bar + 1, self.n_bars)):
            required = (self.highs[i] - p1_price) / (i - p1_bar)
            if required > max_slope:
                max_slope = required
        return max_slope if max_slope < 0 else None

    def _support_containment(self, p1_bar, p1_price, up_to_bar):
        min_slope = 1e30
        for i in range(p1_bar + 1, min(up_to_bar + 1, self.n_bars)):
            required = (self.lows[i] - p1_price) / (i - p1_bar)
            if required < min_slope:
                min_slope = required
        return min_slope if min_slope > 0 else None

    # ── STATE UPDATES ──

    def _update_states(self, bar):
        close = self.closes[bar]
        for line in self.lines:
            lv = line.value_at(bar)
            if line.state == "BROKEN":
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
                if 0 <= lv - self.highs[bar] <= 10 and close < lv:
                    line.touch_count += 1
                if close > lv:
                    line.state = "BROKEN"
                    line.broken_bar = bar
            elif line.direction == "SUPPORT":
                if 0 <= self.lows[bar] - lv <= 10 and close > lv:
                    line.touch_count += 1
                if close < lv:
                    line.state = "BROKEN"
                    line.broken_bar = bar

    # ── PUBLIC ──

    def run_session(self, day_data):
        for i in range(len(day_data)):
            row = day_data.iloc[i]
            self.process_bar(float(row['Open']), float(row['High']),
                           float(row['Low']), float(row['Close']))

    def get_all_lines(self):
        return self.lines

    def get_active_lines(self):
        return [l for l in self.lines if l.state in ("ACTIVE", "RECLAIMED")]
