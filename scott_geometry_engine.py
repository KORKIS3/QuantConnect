"""
scott_geometry_engine.py — Universal Scott Geometry

Swings = chunks of bars moving in one direction then reversing.
Not single-bar peaks. The rhythm of the market.

Orange/Yellow = session extremes, fixed shallow slope
Purple = descending resistance from recent swing highs (local)
Blue = ascending support from recent swing lows (local)

Containment: resistance above all highs, support below all lows.
Wick adjusts slope. Horizontal = removed. Renew from most recent swings.
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

        # Chunk-based swing detection
        self.swing_highs: List[tuple] = []  # (bar, price)
        self.swing_lows: List[tuple] = []
        self._direction = 0  # +1 = moving up, -1 = moving down, 0 = unknown
        self._chunk_high = -1e30
        self._chunk_high_bar = -1
        self._chunk_low = 1e30
        self._chunk_low_bar = -1
        self._chunk_start_bar = 0
        self._last_confirmed_high_bar = -1
        self._last_confirmed_low_bar = -1

        # Line IDs
        self._orange_id = -1
        self._yellow_id = -1
        self._purple_id = -1
        self._blue_id = -1

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

        # Orange/Yellow — also wick adjust, re-anchor when past horizontal
        if high > self.session_high:
            self.session_high = high
            self.session_high_bar = bar
            self._set_orange(bar, high)
        if low < self.session_low:
            self.session_low = low
            self.session_low_bar = bar
            self._set_yellow(bar, low)

        # Wick adjust orange/yellow
        self._wick_adjust_orange(bar)
        self._wick_adjust_yellow(bar)

        # Swing detection
        self._new_swing_this_bar = False
        self._detect_swings(bar)

        # Wick adjust
        self._wick_adjust_purple(bar)
        self._wick_adjust_blue(bar)

        # Break check
        self._check_breaks(bar)

        # Tactical lines
        self._check_tactical_lines(bar)

        # Only update purple/blue when a new swing was just confirmed
        if self._new_swing_this_bar:
            self._ensure_purple(bar)
            self._ensure_blue(bar)

        # Touches
        self._check_touches(bar)

    # ══════════════════════════════════════════════════════════════════
    # SWING DETECTION — Zigzag: confirm swing when price reverses from extreme
    # ══════════════════════════════════════════════════════════════════

    def _detect_swings(self, bar):
        """Zigzag swing detection. Track running high/low.
        When price reverses enough from the extreme, confirm the swing.
        'Enough' = price moves at least 15 pts away from the extreme OR
        3+ bars moving against the extreme."""
        if bar < 2:
            return

        high = self.highs[bar]
        low = self.lows[bar]
        close = self.closes[bar]
        REVERSAL_PTS = 30  # minimum reversal to confirm a swing

        if self._direction == 0:
            # Initialize: determine initial direction from first few bars
            if bar >= 3:
                if self.closes[bar] > self.closes[0]:
                    self._direction = 1
                else:
                    self._direction = -1
                self._chunk_high = max(self.highs[:bar+1])
                self._chunk_high_bar = list(self.highs[:bar+1]).index(self._chunk_high)
                self._chunk_low = min(self.lows[:bar+1])
                self._chunk_low_bar = list(self.lows[:bar+1]).index(self._chunk_low)
            return

        # Update running extremes
        if high > self._chunk_high:
            self._chunk_high = high
            self._chunk_high_bar = bar
        if low < self._chunk_low:
            self._chunk_low = low
            self._chunk_low_bar = bar

        if self._direction == 1:  # trending up
            # Confirm swing HIGH when price drops REVERSAL_PTS from the peak
            if self._chunk_high - low >= REVERSAL_PTS:
                # Confirm the peak as a swing high
                if self._chunk_high_bar != self._last_confirmed_high_bar:
                    self.swing_highs.append((self._chunk_high_bar, self._chunk_high))
                    self._last_confirmed_high_bar = self._chunk_high_bar
                    self._new_swing_this_bar = True
                # Switch to down
                self._direction = -1
                self._chunk_low = low
                self._chunk_low_bar = bar

        elif self._direction == -1:  # trending down
            # Confirm swing LOW when price rises REVERSAL_PTS from the trough
            if high - self._chunk_low >= REVERSAL_PTS:
                if self._chunk_low_bar != self._last_confirmed_low_bar:
                    self.swing_lows.append((self._chunk_low_bar, self._chunk_low))
                    self._last_confirmed_low_bar = self._chunk_low_bar
                    self._new_swing_this_bar = True
                # Switch to up
                self._direction = 1
                self._chunk_high = high
                self._chunk_high_bar = bar

    # ══════════════════════════════════════════════════════════════════
    # ORANGE / YELLOW — with wick adjustment and re-anchoring
    # ══════════════════════════════════════════════════════════════════

    def _set_orange(self, bar, price):
        if self._orange_id > 0:
            l = self._get(self._orange_id)
            if l:
                l.anchor_bar = bar
                l.anchor_price = price
                l.slope = -self.ORANGE_YELLOW_SLOPE  # reset slope on re-anchor
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
        """Orange must stay above all highs. If high pierces but close stays below,
        adjust slope. If slope goes past horizontal (>=0 would mean ascending), 
        re-anchor at most recent swing high."""
        orange = self._get(self._orange_id) if self._orange_id > 0 else None
        if not orange or orange.state != "ACTIVE":
            return
        lv = orange.value_at(bar)
        if self.highs[bar] > lv:
            # High pierced orange — adjust slope
            new_slope = self._resistance_slope(orange.anchor_bar, orange.anchor_price, bar)
            if new_slope is None or new_slope >= 0:
                # Past horizontal — re-anchor at most recent swing high
                if self.swing_highs:
                    sh_bar, sh_price = self.swing_highs[-1]
                    orange.anchor_bar = sh_bar
                    orange.anchor_price = sh_price
                    orange.slope = -self.ORANGE_YELLOW_SLOPE
                else:
                    orange.anchor_bar = bar
                    orange.anchor_price = self.highs[bar]
                    orange.slope = -self.ORANGE_YELLOW_SLOPE
            else:
                orange.slope = new_slope

    def _wick_adjust_yellow(self, bar):
        """Yellow must stay below all lows. If low pierces but close stays above,
        adjust slope. If slope goes past horizontal (<=0), re-anchor at most recent swing low."""
        yellow = self._get(self._yellow_id) if self._yellow_id > 0 else None
        if not yellow or yellow.state != "ACTIVE":
            return
        lv = yellow.value_at(bar)
        if self.lows[bar] < lv:
            # Low pierced yellow — adjust slope
            new_slope = self._support_slope(yellow.anchor_bar, yellow.anchor_price, bar)
            if new_slope is None or new_slope <= 0:
                # Past horizontal — re-anchor at most recent swing low
                if self.swing_lows:
                    sl_bar, sl_price = self.swing_lows[-1]
                    yellow.anchor_bar = sl_bar
                    yellow.anchor_price = sl_price
                    yellow.slope = +self.ORANGE_YELLOW_SLOPE
                else:
                    yellow.anchor_bar = bar
                    yellow.anchor_price = self.lows[bar]
                    yellow.slope = +self.ORANGE_YELLOW_SLOPE
            else:
                yellow.slope = new_slope

    # ══════════════════════════════════════════════════════════════════
    # PURPLE / BLUE — Local structure from recent swings
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

    def _ensure_purple(self, bar):
        """Purple from the TWO MOST RECENT swing highs (descending pair).
        When a new swing high forms, old purple breaks and new one takes over.
        If most recent pair isn't descending, search back one more."""
        if len(self.swing_highs) < 2:
            return

        # Always use the most recent pair first
        p2_bar, p2_price = self.swing_highs[-1]
        p1_bar, p1_price = self.swing_highs[-2]

        # Check if this pair is descending (P1 higher than P2)
        if p1_price > p2_price:
            # Valid descending pair — compute containment from P1
            slope = self._resistance_slope(p1_bar, p1_price, bar)
            if slope is not None and slope < 0:
                # If we already have a purple from this exact pair, skip
                existing = self._get(self._purple_id) if self._purple_id > 0 else None
                if existing and existing.anchor_bar == p1_bar and existing.state == "ACTIVE":
                    return
                # Break old purple
                if existing and existing.state == "ACTIVE":
                    existing.state = "BROKEN"
                    existing.broken_bar = bar
                # Create new
                line = ScottLine(self._new_id(), "PURPLE", p1_bar, p1_price,
                                 slope, "ACTIVE", "RESISTANCE", bar,
                                 p2_bar=p2_bar, p2_price=p2_price)
                self.lines.append(line)
                self._purple_id = line.line_id
                return

        # Most recent pair is ascending — try P1=[-3], P2=[-1] or P1=[-3], P2=[-2]
        if len(self.swing_highs) >= 3:
            for j in range(len(self.swing_highs) - 3, -1, -1):
                p1_bar, p1_price = self.swing_highs[j]
                if p1_price > p2_price:
                    slope = self._resistance_slope(p1_bar, p1_price, bar)
                    if slope is not None and slope < 0:
                        existing = self._get(self._purple_id) if self._purple_id > 0 else None
                        if existing and existing.anchor_bar == p1_bar and existing.state == "ACTIVE":
                            return
                        if existing and existing.state == "ACTIVE":
                            existing.state = "BROKEN"
                            existing.broken_bar = bar
                        line = ScottLine(self._new_id(), "PURPLE", p1_bar, p1_price,
                                         slope, "ACTIVE", "RESISTANCE", bar,
                                         p2_bar=p2_bar, p2_price=p2_price)
                        self.lines.append(line)
                        self._purple_id = line.line_id
                        return
                    break

    def _ensure_blue(self, bar):
        """Blue from the TWO MOST RECENT swing lows (ascending pair).
        Fresh structure every time a new swing low confirms."""
        if len(self.swing_lows) < 2:
            return

        p2_bar, p2_price = self.swing_lows[-1]
        p1_bar, p1_price = self.swing_lows[-2]

        if p1_price < p2_price:
            slope = self._support_slope(p1_bar, p1_price, bar)
            if slope is not None and slope > 0:
                existing = self._get(self._blue_id) if self._blue_id > 0 else None
                if existing and existing.anchor_bar == p1_bar and existing.state == "ACTIVE":
                    return
                if existing and existing.state == "ACTIVE":
                    existing.state = "BROKEN"
                    existing.broken_bar = bar
                line = ScottLine(self._new_id(), "BLUE", p1_bar, p1_price,
                                 slope, "ACTIVE", "SUPPORT", bar,
                                 p2_bar=p2_bar, p2_price=p2_price)
                self.lines.append(line)
                self._blue_id = line.line_id
                return

        if len(self.swing_lows) >= 3:
            for j in range(len(self.swing_lows) - 3, -1, -1):
                p1_bar, p1_price = self.swing_lows[j]
                if p1_price < p2_price:
                    slope = self._support_slope(p1_bar, p1_price, bar)
                    if slope is not None and slope > 0:
                        existing = self._get(self._blue_id) if self._blue_id > 0 else None
                        if existing and existing.anchor_bar == p1_bar and existing.state == "ACTIVE":
                            return
                        if existing and existing.state == "ACTIVE":
                            existing.state = "BROKEN"
                            existing.broken_bar = bar
                        line = ScottLine(self._new_id(), "BLUE", p1_bar, p1_price,
                                         slope, "ACTIVE", "SUPPORT", bar,
                                         p2_bar=p2_bar, p2_price=p2_price)
                        self.lines.append(line)
                        self._blue_id = line.line_id
                        return
                    break

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
    # TACTICAL LINES — Steeper lines when resolve changes direction
    # ══════════════════════════════════════════════════════════════════

    def _check_tactical_lines(self, bar):
        """Create steeper tactical lines when price resolves away from original lines.
        Tactical blue: price far above blue + ascending swing lows = protect upward resolve.
        Tactical purple: price far below purple + descending swing highs = protect downward resolve."""
        if bar < 15:
            return

        # === TACTICAL BLUE: price resolving UP away from blue ===
        blue = self._get(self._blue_id) if self._blue_id > 0 else None
        if blue and blue.state == "ACTIVE":
            blue_val = blue.value_at(bar)
            # Price is significantly above blue (resolve is active)
            if self.lows[bar] - blue_val > 30:
                # Check if we already have an active tactical blue
                has_tac_blue = any(l.line_type == "TACTICAL_BLUE" and l.state == "ACTIVE"
                                   for l in self.lines)
                if not has_tac_blue and len(self.swing_lows) >= 2:
                    # Find ascending swing low pair in recent bars
                    for i in range(len(self.swing_lows) - 1, 0, -1):
                        p2_bar, p2_price = self.swing_lows[i]
                        if p2_bar < bar - 50:
                            break
                        for j in range(i - 1, -1, -1):
                            p1_bar, p1_price = self.swing_lows[j]
                            if p1_price < p2_price and p1_bar >= bar - 50:
                                slope = self._support_slope(p1_bar, p1_price, bar)
                                if slope is not None and slope > 0:
                                    self.lines.append(ScottLine(
                                        self._new_id(), "TACTICAL_BLUE", p1_bar, p1_price,
                                        slope, "ACTIVE", "SUPPORT", bar,
                                        p2_bar=p2_bar, p2_price=p2_price))
                                    return
                        break

        # === TACTICAL PURPLE: price resolving DOWN away from purple ===
        purple = self._get(self._purple_id) if self._purple_id > 0 else None
        if purple and purple.state == "ACTIVE":
            purple_val = purple.value_at(bar)
            if purple_val - self.highs[bar] > 30:
                has_tac_purple = any(l.line_type == "TACTICAL_PURPLE" and l.state == "ACTIVE"
                                     for l in self.lines)
                if not has_tac_purple and len(self.swing_highs) >= 2:
                    for i in range(len(self.swing_highs) - 1, 0, -1):
                        p2_bar, p2_price = self.swing_highs[i]
                        if p2_bar < bar - 50:
                            break
                        for j in range(i - 1, -1, -1):
                            p1_bar, p1_price = self.swing_highs[j]
                            if p1_price > p2_price and p1_bar >= bar - 50:
                                slope = self._resistance_slope(p1_bar, p1_price, bar)
                                if slope is not None and slope < 0:
                                    self.lines.append(ScottLine(
                                        self._new_id(), "TACTICAL_PURPLE", p1_bar, p1_price,
                                        slope, "ACTIVE", "RESISTANCE", bar,
                                        p2_bar=p2_bar, p2_price=p2_price))
                                    return
                        break

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
