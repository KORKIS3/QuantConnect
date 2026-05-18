"""
belief_engine_experiment.py — Comprehensive Experimental Belief Engine

All tweaks from 6/7-day analysis consolidated:
1. First-trade hold (10 bars, bypass only on 2+ failed expansions)
   - Blocked evidence does NOT decay confidence during hold
2. Dynamic spike exit: TREND=200pts, CHOP=100pts
3. Warmup 12 bars + first entry must match dominant slope
4. Reversal cooldown: 2min within first 5min of entry
5. Profit-run: trades >50pts at 10:30 continue; one-and-done after first exit
6. Trend detection: slope threshold 0.1 (relaxed from 0.3)
7. Afternoon chop filter: 12:00-13:45 only enter on HIGH-weight evidence
8. Full logging: unrealized_pl, reason, trade type, day_type on every action
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional, List, Dict


@dataclass
class BeliefConfig:
    """All tunable parameters."""
    partial_tp_pts: float = 50.0
    warmup_bars: int = 12
    min_reversal_minutes: float = 2.0
    cooldown_window_minutes: float = 5.0
    session_end_time: str = "10:30"
    one_and_done: bool = True
    first_entry_trend_filter: bool = True
    profit_run_threshold: float = 50.0
    # First-trade protection
    first_trade_min_hold: int = 10
    first_trade_profit_buffer: bool = True
    # Dynamic spike
    spike_profit_pts_trend: float = 200.0
    spike_profit_pts_chop: float = 100.0
    spike_profit_bars: int = 9
    # Trend detection (relaxed)
    trend_bar_threshold: int = 10
    trend_slope_threshold: float = 0.1
    # Afternoon chop filter
    afternoon_chop_start: str = "12:00"
    afternoon_chop_end: str = "13:45"
    afternoon_chop_require_high_weight: bool = True
    # Resolve
    resolve_new_extreme_window: int = 5


@dataclass
class Evidence:
    bar_idx: int
    time: object
    event_type: str
    direction: str  # BULLISH / BEARISH
    weight: str     # HIGH / MEDIUM / LOW
    description: str


class BeliefEngineExperiment:
    def __init__(self, config: Optional[BeliefConfig] = None):
        self.cfg = config or BeliefConfig()
        # Position
        self.position = 0  # +1 long, -1 short, 0 flat
        self.contracts = 0
        self.entry_price = 0.0
        self.entry_bar_idx = 0
        self.entry_time = None
        self.partial_taken = False
        self.first_trade_done = False
        self.session_done = False
        # Belief
        self.thesis_direction = 0
        self.confidence = 0.0
        self.resolve_state = "NO_RESOLVE"
        # Evidence
        self.evidence_log: List[Evidence] = []
        self.failed_expansions = 0
        self.last_extreme_bar = 0
        # Cooldown
        self.last_reversal_time = None
        # Lines
        self.purple_val = 0.0
        self.blue_val = 0.0
        self.orange_val = 0.0
        self.yellow_val = 0.0
        # History
        self.recent_highs: List[float] = []
        self.recent_lows: List[float] = []
        # Day type
        self.day_type = "UNKNOWN"
        # P/L
        self.session_pl = 0.0
        # Logs
        self.bar_logs: List[Dict] = []
        self.blocked_signals: List[Dict] = []
        self.trades: List[Dict] = []

    # ------------------------------------------------------------------
    # Day type detection
    # ------------------------------------------------------------------
    def _detect_day_type(self, bar_idx: int) -> str:
        if len(self.recent_highs) < self.cfg.trend_bar_threshold:
            return "UNKNOWN"
        window = self.recent_highs[-self.cfg.trend_bar_threshold:]
        window_lows = self.recent_lows[-self.cfg.trend_bar_threshold:]
        mids = [(h + l) / 2 for h, l in zip(window, window_lows)]
        n = len(mids)
        x_mean = (n - 1) / 2.0
        y_mean = sum(mids) / n
        num = sum((i - x_mean) * (mids[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n))
        slope = num / den if den != 0 else 0.0
        range_size = max(window) - min(window_lows)
        if range_size < 20:
            return "CHOP"
        bars_since = bar_idx - self.last_extreme_bar
        if bars_since <= self.cfg.trend_bar_threshold and abs(slope) >= self.cfg.trend_slope_threshold:
            return "TREND"
        return "CHOP"

    def _get_spike_pts(self) -> float:
        return self.cfg.spike_profit_pts_trend if self.day_type == "TREND" else self.cfg.spike_profit_pts_chop

    # ------------------------------------------------------------------
    # Main bar processing
    # ------------------------------------------------------------------
    def process_bar(self, bar_idx: int, bar: dict, lines: dict, mech_signal: str = ""):
        close = bar["Close"]
        high = bar["High"]
        low = bar["Low"]
        bar_time = bar["time"]
        prev_close = bar.get("prev_close", close)

        self.purple_val = lines.get("purple", np.nan)
        self.blue_val = lines.get("blue", np.nan)
        self.orange_val = lines.get("orange", np.nan)
        self.yellow_val = lines.get("yellow", np.nan)
        prev_purple = lines.get("prev_purple", np.nan)
        prev_blue = lines.get("prev_blue", np.nan)
        prev_orange = lines.get("prev_orange", np.nan)
        prev_yellow = lines.get("prev_yellow", np.nan)

        self.day_type = self._detect_day_type(bar_idx)

        # --- Session end ---
        session_end_reached = False
        if hasattr(bar_time, 'strftime'):
            session_end_reached = bar_time.strftime("%H:%M") >= self.cfg.session_end_time

        if session_end_reached and self.position != 0:
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            if unrealized > self.cfg.profit_run_threshold:
                pass  # profit-run: continue
            else:
                self._execute("SESSION_EXIT", bar_idx, bar)
                self.session_done = True
                self._log(bar_idx, bar, [], "SESSION_EXIT")
                return

        if session_end_reached and self.position == 0:
            self.session_done = True
        if self.session_done and self.position == 0:
            self._log(bar_idx, bar, [], "SESSION_DONE")
            return

        # --- Evidence ---
        bar_evidence = self._collect_evidence(bar_idx, bar, prev_close,
                                               prev_purple, prev_blue, prev_orange, prev_yellow)
        self.evidence_log.extend(bar_evidence)

        # --- First-trade protection check (computed before confidence update) ---
        first_trade_protected = False
        _unreal = 0.0
        if self.position != 0 and self.entry_price != 0.0:
            _unreal = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)

        if self.position != 0 and self.cfg.first_trade_min_hold > 0:
            bars_held = bar_idx - self.entry_bar_idx
            is_first_trade = (self.last_reversal_time is None or self.last_reversal_time == self.entry_time)
            if is_first_trade and bars_held < self.cfg.first_trade_min_hold:
                if self.failed_expansions < 2:
                    first_trade_protected = True

        # --- Confidence update (suppress if evidence would be blocked by hold) ---
        if first_trade_protected:
            # Only update confidence from evidence that SUPPORTS current position
            self._update_confidence_filtered(bar_evidence)
        else:
            self._update_confidence(bar_evidence)

        # --- Resolve ---
        self._update_resolve(bar_idx, high, low, close)

        # --- History ---
        self.recent_highs.append(high)
        self.recent_lows.append(low)
        if len(self.recent_highs) > 20:
            self.recent_highs.pop(0)
        if len(self.recent_lows) > 20:
            self.recent_lows.pop(0)

        # --- Decide & execute ---
        action = self._decide(bar_idx, bar, bar_evidence, session_end_reached, first_trade_protected, _unreal)
        self._execute(action, bar_idx, bar)
        self._log(bar_idx, bar, bar_evidence, action)

    # ------------------------------------------------------------------
    # Evidence collection
    # ------------------------------------------------------------------
    def _collect_evidence(self, bar_idx, bar, prev_close, prev_purple, prev_blue, prev_orange, prev_yellow):
        close = bar["Close"]; high = bar["High"]; low = bar["Low"]
        ev = []
        if not np.isnan(prev_purple) and prev_close <= prev_purple and close > self.purple_val:
            ev.append(Evidence(bar_idx, bar["time"], "PURPLE_CROSS_ABOVE", "BULLISH", "MEDIUM", ""))
        if not np.isnan(prev_blue) and prev_close >= prev_blue and close < self.blue_val:
            ev.append(Evidence(bar_idx, bar["time"], "BLUE_CROSS_BELOW", "BEARISH", "MEDIUM", ""))
        if not np.isnan(prev_orange) and prev_close <= prev_orange and close > self.orange_val:
            ev.append(Evidence(bar_idx, bar["time"], "ORANGE_CROSS_ABOVE", "BULLISH", "HIGH", ""))
        if not np.isnan(prev_yellow) and prev_close >= prev_yellow and close < self.yellow_val:
            ev.append(Evidence(bar_idx, bar["time"], "YELLOW_CROSS_BELOW", "BEARISH", "HIGH", ""))
        # Failed expansion
        if self.resolve_state in ("ESTABLISHED", "STRONG") and len(self.recent_highs) >= 2:
            prev_high = max(self.recent_highs[-3:]) if len(self.recent_highs) >= 3 else self.recent_highs[-1]
            if high > prev_high and close < prev_high - 10.0:
                self.failed_expansions += 1
                ev.append(Evidence(bar_idx, bar["time"], "FAILED_EXPANSION_UP", "BEARISH", "MEDIUM", ""))
        if self.resolve_state in ("ESTABLISHED", "STRONG") and len(self.recent_lows) >= 2:
            prev_low = min(self.recent_lows[-3:]) if len(self.recent_lows) >= 3 else self.recent_lows[-1]
            if low < prev_low and close > prev_low + 10.0:
                self.failed_expansions += 1
                ev.append(Evidence(bar_idx, bar["time"], "FAILED_EXPANSION_DOWN", "BULLISH", "MEDIUM", ""))
        # Structure reclaim
        if self.position == -1 and not np.isnan(prev_purple):
            if prev_close <= prev_purple and close > self.purple_val:
                ev.append(Evidence(bar_idx, bar["time"], "STRUCTURE_RECLAIM", "BULLISH", "HIGH", ""))
        if self.position == 1 and not np.isnan(prev_blue):
            if prev_close >= prev_blue and close < self.blue_val:
                ev.append(Evidence(bar_idx, bar["time"], "STRUCTURE_RECLAIM", "BEARISH", "HIGH", ""))
        return ev

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------
    def _update_confidence(self, bar_evidence):
        w_map = {"HIGH": 3.0, "MEDIUM": 1.5, "LOW": 0.5}
        for ev in bar_evidence:
            w = w_map.get(ev.weight, 1.0)
            if self.position == 1:
                self.confidence += w if ev.direction == "BULLISH" else -w
            elif self.position == -1:
                self.confidence += w if ev.direction == "BEARISH" else -w
            else:
                self.confidence += w if ev.direction == "BULLISH" else -w

    def _update_confidence_filtered(self, bar_evidence):
        """During first-trade hold: only apply evidence that SUPPORTS current position."""
        w_map = {"HIGH": 3.0, "MEDIUM": 1.5, "LOW": 0.5}
        for ev in bar_evidence:
            w = w_map.get(ev.weight, 1.0)
            if self.position == 1 and ev.direction == "BULLISH":
                self.confidence += w
            elif self.position == -1 and ev.direction == "BEARISH":
                self.confidence += w
            # Opposing evidence is suppressed — no confidence decay

    # ------------------------------------------------------------------
    # Resolve
    # ------------------------------------------------------------------
    def _update_resolve(self, bar_idx, high, low, close):
        if self.position == 0:
            self.resolve_state = "NO_RESOLVE"; return
        bars_in_trade = bar_idx - self.entry_bar_idx
        making_new = False
        if self.position == 1 and len(self.recent_highs) >= 3:
            if high >= max(self.recent_highs[-3:]):
                making_new = True; self.last_extreme_bar = bar_idx
        elif self.position == -1 and len(self.recent_lows) >= 3:
            if low <= min(self.recent_lows[-3:]):
                making_new = True; self.last_extreme_bar = bar_idx
        bse = bar_idx - self.last_extreme_bar
        if bars_in_trade < 3:
            self.resolve_state = "NO_RESOLVE"
        elif self.failed_expansions >= 2:
            self.resolve_state = "WEAKENING"
        elif bse <= self.cfg.resolve_new_extreme_window and making_new:
            self.resolve_state = "STRONG" if bars_in_trade >= 15 and self.confidence >= 5.0 else "ESTABLISHED"
        elif bse <= 10 and self.confidence >= 2.0:
            self.resolve_state = "ESTABLISHED"
        elif self.confidence >= 1.0:
            self.resolve_state = "EMERGING"
        else:
            self.resolve_state = "NO_RESOLVE"

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------
    def _decide(self, bar_idx, bar, bar_evidence, session_end_reached, first_trade_protected, _unreal):
        close = bar["Close"]; bar_time = bar["time"]

        if bar_idx < self.cfg.warmup_bars:
            return "WAIT"

        # --- Partial TP ---
        if self.position != 0 and not self.partial_taken and self.entry_price != 0.0:
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            if unrealized >= self.cfg.partial_tp_pts:
                return "PARTIAL_TP"

        # --- Spike exit (suppressed during profit-run past session end) ---
        spike_pts = self._get_spike_pts()
        if self.position != 0 and self.entry_price != 0.0:
            bars_held = bar_idx - self.entry_bar_idx
            if 0 < bars_held <= self.cfg.spike_profit_bars:
                unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
                if unrealized >= spike_pts:
                    if session_end_reached and unrealized > self.cfg.profit_run_threshold:
                        pass  # suppress spike during profit-run
                    else:
                        return "SPIKE_EXIT"

        # --- Cooldown (only within first N minutes of entry) ---
        reversal_allowed = True
        if self.cfg.min_reversal_minutes > 0 and self.last_reversal_time is not None:
            if hasattr(bar_time, 'timestamp') and hasattr(self.last_reversal_time, 'timestamp'):
                mins_since_rev = (bar_time - self.last_reversal_time).total_seconds() / 60.0
                mins_since_entry = (bar_time - self.entry_time).total_seconds() / 60.0 if self.entry_time else 999.0
                if mins_since_entry <= self.cfg.cooldown_window_minutes:
                    if mins_since_rev < self.cfg.min_reversal_minutes:
                        reversal_allowed = False

        # --- Afternoon chop filter ---
        in_afternoon_chop = False
        if hasattr(bar_time, 'strftime'):
            hm = bar_time.strftime("%H:%M")
            if self.cfg.afternoon_chop_start <= hm < self.cfg.afternoon_chop_end:
                if self.day_type != "TREND":
                    in_afternoon_chop = True

        # --- Thesis invalidation / reversal signals ---
        for ev in bar_evidence:
            if ev.event_type == "STRUCTURE_RECLAIM":
                if first_trade_protected:
                    self._block("REVERSE", bar_time, "FIRST_TRADE_HOLD", ev.event_type, _unreal)
                elif reversal_allowed:
                    return "REVERSE"
                else:
                    self._block("REVERSE", bar_time, "COOLDOWN", ev.event_type, _unreal)
            if ev.event_type in ("ORANGE_CROSS_ABOVE", "YELLOW_CROSS_BELOW"):
                if self.position == -1 and ev.direction == "BULLISH":
                    if first_trade_protected:
                        self._block("REVERSE", bar_time, "FIRST_TRADE_HOLD", ev.event_type, _unreal)
                    elif reversal_allowed:
                        return "REVERSE"
                    else:
                        self._block("REVERSE", bar_time, "COOLDOWN", ev.event_type, _unreal)
                if self.position == 1 and ev.direction == "BEARISH":
                    if first_trade_protected:
                        self._block("REVERSE", bar_time, "FIRST_TRADE_HOLD", ev.event_type, _unreal)
                    elif reversal_allowed:
                        return "REVERSE"
                    else:
                        self._block("REVERSE", bar_time, "COOLDOWN", ev.event_type, _unreal)

        # --- Flat: enter with trend filter + afternoon chop filter ---
        if self.position == 0:
            for ev in bar_evidence:
                if ev.event_type in ("PURPLE_CROSS_ABOVE", "ORANGE_CROSS_ABOVE"):
                    if in_afternoon_chop and ev.weight != "HIGH":
                        self._block("BUY", bar_time, "AFTERNOON_CHOP", ev.event_type, 0.0)
                        continue
                    if self._trend_filter_allows("BUY"):
                        return "BUY"
                    else:
                        self._block("BUY", bar_time, "TREND_FILTER", ev.event_type, 0.0)
                if ev.event_type in ("BLUE_CROSS_BELOW", "YELLOW_CROSS_BELOW"):
                    if in_afternoon_chop and ev.weight != "HIGH":
                        self._block("SELL", bar_time, "AFTERNOON_CHOP", ev.event_type, 0.0)
                        continue
                    if self._trend_filter_allows("SELL"):
                        return "SELL"
                    else:
                        self._block("SELL", bar_time, "TREND_FILTER", ev.event_type, 0.0)
            return "HOLD"

        # --- In position: opposing cross reversal ---
        has_opposing = any(
            (ev.event_type in ("PURPLE_CROSS_ABOVE", "ORANGE_CROSS_ABOVE") and self.position == -1) or
            (ev.event_type in ("BLUE_CROSS_BELOW", "YELLOW_CROSS_BELOW") and self.position == 1)
            for ev in bar_evidence
        )
        if has_opposing:
            if first_trade_protected:
                self._block("REVERSE", bar_time, "FIRST_TRADE_HOLD", "opposing_cross", _unreal)
                return "HOLD"
            if not reversal_allowed:
                self._block("REVERSE", bar_time, "COOLDOWN", "opposing_cross", _unreal)
                return "HOLD"
            if self.resolve_state in ("NO_RESOLVE", "EMERGING", "WEAKENING"):
                return "REVERSE"
            elif self.resolve_state == "ESTABLISHED":
                if self.failed_expansions >= 2 or self.confidence <= 0:
                    return "REVERSE"
                return "HOLD"
            elif self.resolve_state == "STRONG":
                if self.confidence <= -3.0:
                    return "REVERSE"
                return "HOLD"

        return "HOLD"

    def _block(self, action, bar_time, reason, evidence, unrealized_pl):
        self.blocked_signals.append({
            "time": bar_time, "action": action, "reason": reason,
            "evidence": evidence, "unrealized_pl": unrealized_pl, "day_type": self.day_type
        })

    def _trend_filter_allows(self, direction: str) -> bool:
        if not self.cfg.first_entry_trend_filter or self.first_trade_done:
            return True
        if len(self.recent_highs) < 5:
            return True
        first_avg = np.mean(self.recent_highs[-5:][:3])
        second_avg = np.mean(self.recent_highs[-5:][3:])
        if direction == "BUY":
            return second_avg >= first_avg
        else:
            return second_avg <= first_avg

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def _execute(self, action, bar_idx, bar):
        close = bar["Close"]; bar_time = bar["time"]

        if action == "BUY":
            if self.position == -1:
                c = 1 if self.partial_taken else 2
                self.session_pl += (self.entry_price - close) * c
                self.last_reversal_time = bar_time
            self.position = 1; self.contracts = 2; self.entry_price = close
            self.entry_bar_idx = bar_idx; self.entry_time = bar_time
            self.partial_taken = False; self.failed_expansions = 0
            self.thesis_direction = 1; self.confidence = 1.5; self.first_trade_done = True
            self.trades.append({"time": bar_time, "action": "BUY", "price": close, "type": "entry"})

        elif action == "SELL":
            if self.position == 1:
                c = 1 if self.partial_taken else 2
                self.session_pl += (close - self.entry_price) * c
                self.last_reversal_time = bar_time
            self.position = -1; self.contracts = 2; self.entry_price = close
            self.entry_bar_idx = bar_idx; self.entry_time = bar_time
            self.partial_taken = False; self.failed_expansions = 0
            self.thesis_direction = -1; self.confidence = 1.5; self.first_trade_done = True
            self.trades.append({"time": bar_time, "action": "SELL", "price": close, "type": "entry"})

        elif action == "REVERSE":
            if self.position == 1:
                c = 1 if self.partial_taken else 2
                self.session_pl += (close - self.entry_price) * c
                self.position = -1; self.thesis_direction = -1
            elif self.position == -1:
                c = 1 if self.partial_taken else 2
                self.session_pl += (self.entry_price - close) * c
                self.position = 1; self.thesis_direction = 1
            self.contracts = 2; self.entry_price = close
            self.entry_bar_idx = bar_idx; self.entry_time = bar_time
            self.partial_taken = False; self.failed_expansions = 0
            self.confidence = 1.5; self.last_reversal_time = bar_time
            self.trades.append({"time": bar_time, "action": "REVERSE", "price": close, "type": "reversal"})

        elif action == "PARTIAL_TP":
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            self.session_pl += unrealized
            self.partial_taken = True; self.contracts = 1
            self.trades.append({"time": bar_time, "action": "PARTIAL_TP", "price": close, "type": "partial_tp"})

        elif action == "SPIKE_EXIT":
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            c = 1 if self.partial_taken else 2
            self.session_pl += unrealized * c
            self.position = 0; self.contracts = 0; self.entry_price = 0.0
            self.partial_taken = False; self.thesis_direction = 0
            self.confidence = 0.0; self.failed_expansions = 0
            if self.cfg.one_and_done:
                self.session_done = True
            self.trades.append({"time": bar_time, "action": "SPIKE_EXIT", "price": close, "type": "spike_exit"})

        elif action == "SESSION_EXIT":
            if self.position == 1:
                c = 1 if self.partial_taken else 2
                self.session_pl += (close - self.entry_price) * c
            elif self.position == -1:
                c = 1 if self.partial_taken else 2
                self.session_pl += (self.entry_price - close) * c
            self.position = 0; self.contracts = 0; self.entry_price = 0.0
            self.partial_taken = False; self.session_done = True
            self.trades.append({"time": bar_time, "action": "SESSION_EXIT", "price": close, "type": "session_exit"})

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    def _log(self, bar_idx, bar, bar_evidence, action):
        close = bar["Close"]
        if self.position == 0 or self.entry_price == 0.0:
            display_pl = self.session_pl
        elif self.position == 1:
            display_pl = self.session_pl + (close - self.entry_price) * self.contracts
        else:
            display_pl = self.session_pl + (self.entry_price - close) * self.contracts
        self.bar_logs.append({
            "bar_idx": bar_idx, "time": bar["time"], "close": close,
            "position": self.position, "contracts": self.contracts,
            "entry_price": self.entry_price, "confidence": self.confidence,
            "resolve_state": self.resolve_state, "day_type": self.day_type,
            "failed_expansions": self.failed_expansions,
            "evidence_types": "|".join(e.event_type for e in bar_evidence),
            "action": action, "session_pl": display_pl,
            "partial_taken": self.partial_taken, "session_done": self.session_done,
        })

    # ------------------------------------------------------------------
    # Session runner
    # ------------------------------------------------------------------
    def run_session(self, algo_df: pd.DataFrame) -> pd.DataFrame:
        n = len(algo_df)
        for i in range(n):
            row = algo_df.iloc[i]
            prev_row = algo_df.iloc[i - 1] if i > 0 else row
            bar = {
                "time": algo_df.index[i],
                "Open": float(row["Open"]), "High": float(row["High"]),
                "Low": float(row["Low"]), "Close": float(row["Close"]),
                "prev_close": float(prev_row["Close"]),
            }
            lines = {
                "purple": float(row["purple_ray"]) if "purple_ray" in row.index and not pd.isna(row["purple_ray"]) else np.nan,
                "blue": float(row["blue_ray"]) if "blue_ray" in row.index and not pd.isna(row["blue_ray"]) else np.nan,
                "orange": float(row["orange_ray"]) if "orange_ray" in row.index and not pd.isna(row["orange_ray"]) else np.nan,
                "yellow": float(row["yellow_ray"]) if "yellow_ray" in row.index and not pd.isna(row["yellow_ray"]) else np.nan,
                "prev_purple": float(prev_row["purple_ray"]) if "purple_ray" in prev_row.index and not pd.isna(prev_row["purple_ray"]) else np.nan,
                "prev_blue": float(prev_row["blue_ray"]) if "blue_ray" in prev_row.index and not pd.isna(prev_row["blue_ray"]) else np.nan,
                "prev_orange": float(prev_row["orange_ray"]) if "orange_ray" in prev_row.index and not pd.isna(prev_row["orange_ray"]) else np.nan,
                "prev_yellow": float(prev_row["yellow_ray"]) if "yellow_ray" in prev_row.index and not pd.isna(prev_row["yellow_ray"]) else np.nan,
            }
            mech_signal = ""
            if "signal" in row.index:
                sig = row["signal"]
                if sig in ("BUY", "SELL"):
                    mech_signal = sig
            self.process_bar(i, bar, lines, mech_signal)
        return pd.DataFrame(self.bar_logs)
