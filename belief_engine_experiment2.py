"""
belief_engine_experiment2.py — Experimental Belief Engine v2

Dynamic Trend vs Chop detection adjusts parameters per-bar:
- TREND: spike_profit=200, cooldown=2min (first 5min only), profit-run past 10:30
- CHOP: spike_profit=100, cooldown=2min (first 5min only), hard exit at 10:30

Core discipline:
1. Warmup 12 bars + first entry must match dominant slope
2. Cooldown 2min, only applies within first 5 minutes of entry
3. Session end 10:30: profitable trades (>50pts) continue with trailing/normal exits
4. One-and-done: no re-entry after first exit to flat
5. Enhanced logging: all blocked signals with unrealized P/L and day_type
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional, List, Dict


@dataclass
class BeliefConfig2:
    """Parameters for the experimental belief engine v2."""
    partial_tp_pts: float = 50.0
    warmup_bars: int = 12
    min_reversal_minutes: float = 2.0        # cooldown between reversals
    cooldown_window_minutes: float = 5.0     # cooldown only applies within N min of entry
    session_end_time: str = "10:30"
    one_and_done: bool = True
    first_entry_trend_filter: bool = True
    profit_run_threshold: float = 50.0       # allow profitable trades to run past session end
    # First-trade protection
    first_trade_min_hold: int = 10           # NEW: min bars before first trade can be reversed
    first_trade_profit_buffer: bool = True   # NEW: if unrealized>0, block reversal during min_hold
    # Dynamic params (adjusted by day_type)
    spike_profit_pts_trend: float = 200.0
    spike_profit_pts_chop: float = 100.0
    spike_profit_bars: int = 9
    # Trend detection
    trend_bar_threshold: int = 10            # bars since last extreme to qualify as trending
    trend_slope_threshold: float = 0.3       # min slope magnitude (price/bar) to qualify
    # Resolve thresholds
    resolve_new_extreme_window: int = 5
    failed_expansion_reversal_bars: int = 3



@dataclass
class Evidence:
    """Single piece of evidence collected on a bar."""
    bar_idx: int
    time: object
    event_type: str
    direction: str
    weight: str
    description: str


class BeliefEngineV2:
    """Experimental belief engine with dynamic trend/chop adaptation."""

    def __init__(self, config: Optional[BeliefConfig2] = None):
        self.cfg = config or BeliefConfig2()

        # Position state
        self.position = 0
        self.contracts = 0
        self.entry_price = 0.0
        self.entry_bar_idx = 0
        self.entry_time = None
        self.partial_taken = False
        self.first_trade_done = False
        self.session_done = False

        # Belief state
        self.thesis_direction = 0
        self.confidence = 0.0
        self.resolve_state = "NO_RESOLVE"

        # Evidence tracking
        self.evidence_log: List[Evidence] = []
        self.failed_expansions = 0
        self.last_extreme_bar = 0

        # Reversal cooldown
        self.last_reversal_time = None

        # Line values
        self.purple_val = 0.0
        self.blue_val = 0.0
        self.orange_val = 0.0
        self.yellow_val = 0.0

        # History
        self.recent_highs: List[float] = []
        self.recent_lows: List[float] = []

        # Day type detection
        self.day_type = "UNKNOWN"  # TREND or CHOP
        self.bars_since_last_extreme = 0

        # P/L tracking
        self.session_pl = 0.0

        # Output
        self.bar_logs: List[Dict] = []
        self.blocked_signals: List[Dict] = []
        self.trades: List[Dict] = []

    def _detect_day_type(self, bar_idx: int) -> str:
        """Classify current market as TREND or CHOP based on recent extremes and slope."""
        if len(self.recent_highs) < self.cfg.trend_bar_threshold:
            return "UNKNOWN"

        # Check if making new extremes recently
        window = self.recent_highs[-self.cfg.trend_bar_threshold:]
        window_lows = self.recent_lows[-self.cfg.trend_bar_threshold:]

        # Slope: linear regression of closes approximated by high/low midpoints
        mids = [(h + l) / 2 for h, l in zip(window, window_lows)]
        n = len(mids)
        x_mean = (n - 1) / 2.0
        y_mean = sum(mids) / n
        num = sum((i - x_mean) * (mids[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n))
        slope = num / den if den != 0 else 0.0

        # New extremes: is the latest high/low near the window extreme?
        range_size = max(window) - min(window_lows)
        if range_size < 20:
            return "CHOP"

        bars_since = bar_idx - self.last_extreme_bar
        slope_mag = abs(slope)

        if bars_since <= self.cfg.trend_bar_threshold and slope_mag >= self.cfg.trend_slope_threshold:
            return "TREND"
        else:
            return "CHOP"

    def _get_spike_pts(self) -> float:
        """Return spike profit threshold based on day type."""
        if self.day_type == "TREND":
            return self.cfg.spike_profit_pts_trend
        return self.cfg.spike_profit_pts_chop

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

        # --- Update day type ---
        self.day_type = self._detect_day_type(bar_idx)

        # --- Session end check ---
        session_end_reached = False
        if hasattr(bar_time, 'strftime'):
            session_end_reached = bar_time.strftime("%H:%M") >= self.cfg.session_end_time

        # Session end: force exit unless profitable and trending
        if session_end_reached and self.position != 0:
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            if unrealized > self.cfg.profit_run_threshold:
                # Profit-run: let it continue, but suppress spike exit for trending trades
                pass  # fall through to normal processing
            else:
                action = "SESSION_EXIT"
                self._execute_action(action, bar_idx, bar)
                self.session_done = True
                self._log_bar(bar_idx, bar, [], action)
                return

        # Block new entries after session end
        if session_end_reached and self.position == 0:
            self.session_done = True

        if self.session_done and self.position == 0:
            self._log_bar(bar_idx, bar, [], "SESSION_DONE")
            return

        # --- Collect evidence ---
        bar_evidence = self._collect_evidence(bar_idx, bar, prev_close,
                                               prev_purple, prev_blue, prev_orange, prev_yellow)
        self.evidence_log.extend(bar_evidence)
        self._update_confidence(bar_evidence)
        self._update_resolve(bar_idx, high, low, close)

        self.recent_highs.append(high)
        self.recent_lows.append(low)
        if len(self.recent_highs) > 20:
            self.recent_highs.pop(0)
        if len(self.recent_lows) > 20:
            self.recent_lows.pop(0)

        # --- Decide and execute ---
        action = self._decide_action(bar_idx, bar, bar_evidence, session_end_reached)
        self._execute_action(action, bar_idx, bar)
        self._log_bar(bar_idx, bar, bar_evidence, action)

    def _collect_evidence(self, bar_idx, bar, prev_close, prev_purple, prev_blue, prev_orange, prev_yellow):
        close = bar["Close"]
        high = bar["High"]
        low = bar["Low"]
        ev = []

        if not np.isnan(prev_purple) and prev_close <= prev_purple and close > self.purple_val:
            ev.append(Evidence(bar_idx, bar["time"], "PURPLE_CROSS_ABOVE", "BULLISH", "MEDIUM",
                               f"Close {close:.0f} > purple {self.purple_val:.0f}"))
        if not np.isnan(prev_blue) and prev_close >= prev_blue and close < self.blue_val:
            ev.append(Evidence(bar_idx, bar["time"], "BLUE_CROSS_BELOW", "BEARISH", "MEDIUM",
                               f"Close {close:.0f} < blue {self.blue_val:.0f}"))
        if not np.isnan(prev_orange) and prev_close <= prev_orange and close > self.orange_val:
            ev.append(Evidence(bar_idx, bar["time"], "ORANGE_CROSS_ABOVE", "BULLISH", "HIGH",
                               f"Close {close:.0f} > orange {self.orange_val:.0f}"))
        if not np.isnan(prev_yellow) and prev_close >= prev_yellow and close < self.yellow_val:
            ev.append(Evidence(bar_idx, bar["time"], "YELLOW_CROSS_BELOW", "BEARISH", "HIGH",
                               f"Close {close:.0f} < yellow {self.yellow_val:.0f}"))

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

    def _update_resolve(self, bar_idx, high, low, close):
        if self.position == 0:
            self.resolve_state = "NO_RESOLVE"
            return
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

    def _decide_action(self, bar_idx, bar, bar_evidence, session_end_reached):
        close = bar["Close"]
        bar_time = bar["time"]

        if bar_idx < self.cfg.warmup_bars:
            return "WAIT"

        # --- Partial TP ---
        if self.position != 0 and not self.partial_taken and self.entry_price != 0.0:
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            if unrealized >= self.cfg.partial_tp_pts:
                return "PARTIAL_TP"

        # --- Spike exit (suppressed for profit-run trades past session end) ---
        spike_pts = self._get_spike_pts()
        if self.position != 0 and self.entry_price != 0.0:
            bars_held = bar_idx - self.entry_bar_idx
            if 0 < bars_held <= self.cfg.spike_profit_bars:
                unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
                if unrealized >= spike_pts:
                    # Suppress spike exit if in profit-run mode past session end
                    if session_end_reached and unrealized > self.cfg.profit_run_threshold:
                        pass  # let it run, don't spike exit
                    else:
                        return "SPIKE_EXIT"

        # --- Cooldown: only applies within first N minutes of entry ---
        reversal_allowed = True
        if self.cfg.min_reversal_minutes > 0 and self.last_reversal_time is not None:
            if hasattr(bar_time, 'timestamp') and hasattr(self.last_reversal_time, 'timestamp'):
                mins_since_reversal = (bar_time - self.last_reversal_time).total_seconds() / 60.0
                mins_since_entry = (bar_time - self.entry_time).total_seconds() / 60.0 if self.entry_time else 999.0
                # Cooldown only active within first N minutes of entry
                if mins_since_entry <= self.cfg.cooldown_window_minutes:
                    if mins_since_reversal < self.cfg.min_reversal_minutes:
                        reversal_allowed = False

        _unreal = 0.0
        if self.position != 0 and self.entry_price != 0.0:
            _unreal = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)

        # --- First-trade protection: min hold period ---
        # Block reversals during first N bars of the FIRST trade unless multiple failed expansions
        first_trade_protected = False
        if self.position != 0 and self.cfg.first_trade_min_hold > 0:
            bars_held = bar_idx - self.entry_bar_idx
            is_first_trade = (self.last_reversal_time is None or self.last_reversal_time == self.entry_time)
            if is_first_trade and bars_held < self.cfg.first_trade_min_hold:
                # Only allow reversal if 2+ failed expansions accumulated (strong evidence)
                if self.failed_expansions < 2:
                    # Profit buffer: if profitable, definitely block
                    if self.cfg.first_trade_profit_buffer and _unreal > 0:
                        first_trade_protected = True
                    else:
                        first_trade_protected = True

        # --- Thesis invalidation ---
        for ev in bar_evidence:
            if ev.event_type == "STRUCTURE_RECLAIM":
                if first_trade_protected:
                    self.blocked_signals.append({"time": bar_time, "action": "REVERSE",
                                                  "reason": "FIRST_TRADE_HOLD", "evidence": ev.event_type,
                                                  "unrealized_pl": _unreal, "day_type": self.day_type})
                elif reversal_allowed:
                    return "REVERSE"
                else:
                    self.blocked_signals.append({"time": bar_time, "action": "REVERSE",
                                                  "reason": "COOLDOWN", "evidence": ev.event_type,
                                                  "unrealized_pl": _unreal, "day_type": self.day_type})
            if ev.event_type in ("ORANGE_CROSS_ABOVE", "YELLOW_CROSS_BELOW"):
                if self.position == -1 and ev.direction == "BULLISH":
                    if first_trade_protected:
                        self.blocked_signals.append({"time": bar_time, "action": "REVERSE",
                                                      "reason": "FIRST_TRADE_HOLD", "evidence": ev.event_type,
                                                      "unrealized_pl": _unreal, "day_type": self.day_type})
                    elif reversal_allowed:
                        return "REVERSE"
                    else:
                        self.blocked_signals.append({"time": bar_time, "action": "REVERSE",
                                                      "reason": "COOLDOWN", "evidence": ev.event_type,
                                                      "unrealized_pl": _unreal, "day_type": self.day_type})
                if self.position == 1 and ev.direction == "BEARISH":
                    if first_trade_protected:
                        self.blocked_signals.append({"time": bar_time, "action": "REVERSE",
                                                      "reason": "FIRST_TRADE_HOLD", "evidence": ev.event_type,
                                                      "unrealized_pl": _unreal, "day_type": self.day_type})
                    elif reversal_allowed:
                        return "REVERSE"
                    else:
                        self.blocked_signals.append({"time": bar_time, "action": "REVERSE",
                                                      "reason": "COOLDOWN", "evidence": ev.event_type,
                                                      "unrealized_pl": _unreal, "day_type": self.day_type})

        # --- Flat: enter with trend filter ---
        if self.position == 0:
            for ev in bar_evidence:
                if ev.event_type in ("PURPLE_CROSS_ABOVE", "ORANGE_CROSS_ABOVE"):
                    if self._trend_filter_allows("BUY"):
                        return "BUY"
                    else:
                        self.blocked_signals.append({"time": bar_time, "action": "BUY",
                                                      "reason": "TREND_FILTER", "evidence": ev.event_type,
                                                      "unrealized_pl": 0.0, "day_type": self.day_type})
                if ev.event_type in ("BLUE_CROSS_BELOW", "YELLOW_CROSS_BELOW"):
                    if self._trend_filter_allows("SELL"):
                        return "SELL"
                    else:
                        self.blocked_signals.append({"time": bar_time, "action": "SELL",
                                                      "reason": "TREND_FILTER", "evidence": ev.event_type,
                                                      "unrealized_pl": 0.0, "day_type": self.day_type})
            return "HOLD"

        # --- In position: reversal ---
        has_opposing = any(
            (ev.event_type in ("PURPLE_CROSS_ABOVE", "ORANGE_CROSS_ABOVE") and self.position == -1) or
            (ev.event_type in ("BLUE_CROSS_BELOW", "YELLOW_CROSS_BELOW") and self.position == 1)
            for ev in bar_evidence
        )
        if has_opposing:
            if first_trade_protected:
                self.blocked_signals.append({"time": bar_time, "action": "REVERSE",
                                              "reason": "FIRST_TRADE_HOLD", "evidence": "opposing_cross",
                                              "unrealized_pl": _unreal, "day_type": self.day_type})
                return "HOLD"
            if not reversal_allowed:
                self.blocked_signals.append({"time": bar_time, "action": "REVERSE",
                                              "reason": "COOLDOWN", "evidence": "opposing_cross",
                                              "unrealized_pl": _unreal, "day_type": self.day_type})
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

    def _execute_action(self, action, bar_idx, bar):
        close = bar["Close"]
        bar_time = bar["time"]

        if action == "BUY":
            if self.position == -1:
                c = 1 if self.partial_taken else 2
                self.session_pl += (self.entry_price - close) * c
                self.last_reversal_time = bar_time
            self.position = 1; self.contracts = 2; self.entry_price = close
            self.entry_bar_idx = bar_idx; self.entry_time = bar_time
            self.partial_taken = False; self.failed_expansions = 0
            self.thesis_direction = 1; self.confidence = 1.5; self.first_trade_done = True

        elif action == "SELL":
            if self.position == 1:
                c = 1 if self.partial_taken else 2
                self.session_pl += (close - self.entry_price) * c
                self.last_reversal_time = bar_time
            self.position = -1; self.contracts = 2; self.entry_price = close
            self.entry_bar_idx = bar_idx; self.entry_time = bar_time
            self.partial_taken = False; self.failed_expansions = 0
            self.thesis_direction = -1; self.confidence = 1.5; self.first_trade_done = True

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

        elif action == "PARTIAL_TP":
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            self.session_pl += unrealized
            self.partial_taken = True; self.contracts = 1

        elif action == "SPIKE_EXIT":
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            c = 1 if self.partial_taken else 2
            self.session_pl += unrealized * c
            self.position = 0; self.contracts = 0; self.entry_price = 0.0
            self.partial_taken = False; self.thesis_direction = 0
            self.confidence = 0.0; self.failed_expansions = 0
            if self.cfg.one_and_done:
                self.session_done = True

        elif action == "SESSION_EXIT":
            if self.position == 1:
                c = 1 if self.partial_taken else 2
                self.session_pl += (close - self.entry_price) * c
            elif self.position == -1:
                c = 1 if self.partial_taken else 2
                self.session_pl += (self.entry_price - close) * c
            self.position = 0; self.contracts = 0; self.entry_price = 0.0
            self.partial_taken = False; self.session_done = True

    def _log_bar(self, bar_idx, bar, bar_evidence, action):
        close = bar["Close"]
        if self.position == 0 or self.entry_price == 0.0:
            display_pl = self.session_pl
        elif self.position == 1:
            display_pl = self.session_pl + (close - self.entry_price) * self.contracts
        else:
            display_pl = self.session_pl + (self.entry_price - close) * self.contracts

        self.bar_logs.append({
            "bar_idx": bar_idx, "time": bar["time"],
            "close": close, "position": self.position, "contracts": self.contracts,
            "entry_price": self.entry_price, "confidence": self.confidence,
            "resolve_state": self.resolve_state, "day_type": self.day_type,
            "failed_expansions": self.failed_expansions,
            "evidence_count": len(bar_evidence),
            "evidence_types": "|".join(e.event_type for e in bar_evidence),
            "action": action, "session_pl": display_pl,
            "partial_taken": self.partial_taken, "session_done": self.session_done,
        })

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
