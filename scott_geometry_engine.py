"""
scott_geometry_engine.py — Universal Scott Geometry (Clean Rewrite)

TWO TIERS:
  Strategic: Orange/Yellow from session extremes (big picture boundaries)
  Local: Purple/Blue from recent swing pairs (active argument near current price)

Both tiers coexist and are visible simultaneously.
Strategic = where price COULD go. Local = where the current argument IS.

Lines wick-adjust (slope gets flatter when price pushes against them).
Lines are removed when slope goes past horizontal.
Broken lines stay visible but faded.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ScottLine:
    line_id: int
    line_type: str       # ORANGE, YELLOW, PURPLE, BLUE
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
    LOCAL_WINDOW = 20

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
        # Line IDs (one per role)
        self._orange_id = -1
        self._yellow_id = -1
        self._strategic_purple_id = -1
        self._strategic_blue_id = -1
        self._local_purple_id = -1
        self._local_blue_id = -1

    def _id(self):
        i = self._next_id
        self._next_id += 1
        return i

    def _line(self, lid):
        if lid <= 0:
            return None
        for l in self.lines:
            if l.line_id == lid:
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

        # 1. Orange/Yellow — session extremes
        if high > self.session_high:
            self.session_high = high
            self.session_high_bar = bar
            self._update_orange(bar, high)
        if low < self.session_low:
            self.session_low = low
            self.session_low_bar = bar
            self._update_yellow(bar, low)

        # 2. Wick adjust orange/yellow
        self._wick_orange(bar)
        self._wick_yellow(bar)

        # 3. Wick adjust strategic purple/blue
        self._wick_line(self._strategic_purple_id, bar)
        self._wick_line(self._strategic_blue_id, bar)

        # 4. Wick adjust local purple/blue
        self._wick_line(self._local_purple_id, bar)
        self._wick_line(self._local_blue_id, bar)

        # 5. Break check (close beyond line)
        self._check_breaks(bar)

        # 6. Strategic purple/blue — create once from session extremes
        if self._strategic_purple_id <= 0 and bar >= 5:
            self._create_strategic_purple(bar)
        if self._strategic_blue_id <= 0 and bar >= 5:
            self._create_strategic_blue(bar)

        # 7. Local purple/blue — only create when we don't have one
        if self._local_purple_id <= 0 and bar >= self.LOCAL_WINDOW:
            self._create_local_purple(bar)
        if self._local_blue_id <= 0 and bar >= self.LOCAL_WINDOW:
            self._create_local_blue(bar)

        # 8. Touches
        self._check_touches(bar)

    # ══════════════════════════════════════════════════════════════════
    # ORANGE / YELLOW — Strategic boundaries
    # ══════════════════════════════════════════════════════════════════

    def _update_orange(self, bar, price):
        """One orange. Re-anchors at new session high. Fixed slope."""
        l = self._line(self._orange_id)
        if l:
            l.anchor_bar = bar
            l.anchor_price = price
            l.slope = -self.ORANGE_YELLOW_SLOPE
            l.state = "ACTIVE"
        else:
            line = ScottLine(self._id(), "ORANGE", bar, price,
                             -self.ORANGE_YELLOW_SLOPE, "ACTIVE", "RESISTANCE", bar)
            self.lines.append(line)
            self._orange_id = line.line_id

    def _update_yellow(self, bar, price):
        """One yellow. Re-anchors at new session low. Fixed slope."""
        l = self._line(self._yellow_id)
        if l:
            l.anchor_bar = bar
            l.anchor_price = price
            l.slope = +self.ORANGE_YELLOW_SLOPE
            l.state = "ACTIVE"
        else:
            line = ScottLine(self._id(), "YELLOW", bar, price,
                             +self.ORANGE_YELLOW_SLOPE, "ACTIVE", "SUPPORT", bar)
            self.lines.append(line)
            self._yellow_id = line.line_id

    def _wick_orange(self, bar):
        """Orange adjusts slope when high pierces it. Re-anchors when horizontal."""
        l = self._line(self._orange_id)
        if not l or l.state != "ACTIVE":
            return
        if self.highs[bar] > l.value_at(bar):
            new_slope = self._res_slope(l.anchor_bar, l.anchor_price, bar)
            if new_slope is None or new_slope >= 0:
                l.anchor_bar = bar
                l.anchor_price = self.highs[bar]
                l.slope = -self.ORANGE_YELLOW_SLOPE
            else:
                l.slope = new_slope

    def _wick_yellow(self, bar):
        """Yellow adjusts slope when low pierces it. Re-anchors when horizontal."""
        l = self._line(self._yellow_id)
        if not l or l.state != "ACTIVE":
            return
        if self.lows[bar] < l.value_at(bar):
            new_slope = self._sup_slope(l.anchor_bar, l.anchor_price, bar)
            if new_slope is None or new_slope <= 0:
                l.anchor_bar = bar
                l.anchor_price = self.lows[bar]
                l.slope = +self.ORANGE_YELLOW_SLOPE
            else:
                l.slope = new_slope

    # ══════════════════════════════════════════════════════════════════
    # STRATEGIC PURPLE / BLUE — From session extremes
    # ══════════════════════════════════════════════════════════════════

    def _create_strategic_purple(self, bar):
        """From session high, containment slope. Created once."""
        slope = self._res_slope(self.session_high_bar, self.session_high, bar)
        if slope is None or slope >= 0:
            return
        line = ScottLine(self._id(), "PURPLE", self.session_high_bar, self.session_high,
                         slope, "ACTIVE", "RESISTANCE", bar)
        self.lines.append(line)
        self._strategic_purple_id = line.line_id

    def _create_strategic_blue(self, bar):
        """From session low, containment slope. Created once."""
        slope = self._sup_slope(self.session_low_bar, self.session_low, bar)
        if slope is None or slope <= 0:
            return
        line = ScottLine(self._id(), "BLUE", self.session_low_bar, self.session_low,
                         slope, "ACTIVE", "SUPPORT", bar)
        self.lines.append(line)
        self._strategic_blue_id = line.line_id

    # ══════════════════════════════════════════════════════════════════
    # LOCAL PURPLE / BLUE — From recent swings (rolling window)
    # ══════════════════════════════════════════════════════════════════

    def _create_local_purple(self, bar):
        """Find descending swing high pair in rolling window.
        P1 = HIGHEST swing high in window (anchor stays at the top).
        P2 = most recent swing high lower than P1."""
        window_start = max(0, bar - self.LOCAL_WINDOW * 2)

        peaks = []
        for i in range(max(window_start + 1, 1), bar - 1):
            if self.highs[i] > self.highs[i-1] and self.highs[i] > self.highs[i+1]:
                peaks.append((i, self.highs[i]))

        if len(peaks) < 2:
            return

        # P1 = HIGHEST swing high in window (anchor at the top)
        best_p1 = max(peaks, key=lambda x: x[1])

        # P2 = most recent swing high LOWER than P1 and AFTER P1
        p2 = None
        for i in range(len(peaks) - 1, -1, -1):
            if peaks[i][1] < best_p1[1] and peaks[i][0] > best_p1[0]:
                p2 = peaks[i]
                break

        if p2 is None:
            return

        slope = self._res_slope(best_p1[0], best_p1[1], bar)
        if slope is None or slope >= 0:
            return

        existing = self._line(self._local_purple_id)
        if existing and existing.state == "ACTIVE":
            return  # already have one, let wick adjust handle it

        line = ScottLine(self._id(), "PURPLE", best_p1[0], best_p1[1],
                         slope, "ACTIVE", "RESISTANCE", bar,
                         p2_bar=p2[0], p2_price=p2[1])
        self.lines.append(line)
        self._local_purple_id = line.line_id

    def _create_local_blue(self, bar):
        """Find ascending swing low pair in rolling window.
        P1 = LOWEST swing low in window (anchor stays at the bottom).
        P2 = most recent swing low higher than P1."""
        window_start = max(0, bar - self.LOCAL_WINDOW * 2)

        troughs = []
        for i in range(max(window_start + 1, 1), bar - 1):
            if self.lows[i] < self.lows[i-1] and self.lows[i] < self.lows[i+1]:
                troughs.append((i, self.lows[i]))

        if len(troughs) < 2:
            return

        # P1 = LOWEST swing low in window (anchor at the bottom)
        best_p1 = min(troughs, key=lambda x: x[1])

        # P2 = most recent swing low HIGHER than P1 and AFTER P1
        p2 = None
        for i in range(len(troughs) - 1, -1, -1):
            if troughs[i][1] > best_p1[1] and troughs[i][0] > best_p1[0]:
                p2 = troughs[i]
                break

        if p2 is None:
            return

        slope = self._sup_slope(best_p1[0], best_p1[1], bar)
        if slope is None or slope <= 0:
            return

        existing = self._line(self._local_blue_id)
        if existing and existing.state == "ACTIVE":
            return  # already have one, let wick adjust handle it

        line = ScottLine(self._id(), "BLUE", best_p1[0], best_p1[1],
                         slope, "ACTIVE", "SUPPORT", bar,
                         p2_bar=p2[0], p2_price=p2[1])
        self.lines.append(line)
        self._local_blue_id = line.line_id

    # ══════════════════════════════════════════════════════════════════
    # GENERIC WICK ADJUST
    # ══════════════════════════════════════════════════════════════════

    def _wick_line(self, lid, bar):
        """Adjust slope when price pushes against line. Remove if horizontal."""
        l = self._line(lid)
        if not l or l.state != "ACTIVE":
            return
        lv = l.value_at(bar)

        if l.direction == "RESISTANCE":
            if self.highs[bar] > lv and self.closes[bar] <= lv:
                new_slope = self._res_slope(l.anchor_bar, l.anchor_price, bar)
                if new_slope is None or new_slope >= 0:
                    l.state = "REMOVED"
                    self._clear_ref(lid)
                else:
                    l.slope = new_slope
        elif l.direction == "SUPPORT":
            if self.lows[bar] < lv and self.closes[bar] >= lv:
                new_slope = self._sup_slope(l.anchor_bar, l.anchor_price, bar)
                if new_slope is None or new_slope <= 0:
                    l.state = "REMOVED"
                    self._clear_ref(lid)
                else:
                    l.slope = new_slope

    def _clear_ref(self, lid):
        if self._strategic_purple_id == lid: self._strategic_purple_id = -1
        elif self._strategic_blue_id == lid: self._strategic_blue_id = -1
        elif self._local_purple_id == lid: self._local_purple_id = -1
        elif self._local_blue_id == lid: self._local_blue_id = -1

    # ══════════════════════════════════════════════════════════════════
    # BREAK CHECK
    # ══════════════════════════════════════════════════════════════════

    def _check_breaks(self, bar):
        close = self.closes[bar]
        for line in self.lines:
            if line.state != "ACTIVE":
                continue
            if line.line_type in ("ORANGE", "YELLOW"):
                continue  # these re-anchor, don't break
            lv = line.value_at(bar)
            if line.direction == "RESISTANCE" and close > lv:
                line.state = "BROKEN"
                line.broken_bar = bar
                self._clear_ref(line.line_id)
            elif line.direction == "SUPPORT" and close < lv:
                line.state = "BROKEN"
                line.broken_bar = bar
                self._clear_ref(line.line_id)

    # ══════════════════════════════════════════════════════════════════
    # CONTAINMENT SLOPE
    # ══════════════════════════════════════════════════════════════════

    def _res_slope(self, p1_bar, p1_price, up_to_bar):
        """Shallowest slope staying ABOVE all highs."""
        max_s = -1e30
        for i in range(p1_bar + 1, min(up_to_bar + 1, self.n_bars)):
            s = (self.highs[i] - p1_price) / (i - p1_bar)
            if s > max_s:
                max_s = s
        return max_s if max_s < 0 else None

    def _sup_slope(self, p1_bar, p1_price, up_to_bar):
        """Shallowest slope staying BELOW all lows."""
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
