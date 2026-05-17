"""
belief_engine_experiment2.py — Experimental Belief Engine v2

Changes from baseline (fred_belief_engine.py):
1. Warmup 7 → 12 bars + first entry must match dominant slope direction
2. min_reversal_minutes=5 to prevent rapid whipsaws
3. Hard session end at 10:30 + one-and-done mode (no re-entry after first exit)
4. Enhanced logging: tracks blocked signals and reasons

Goal: Replicate Scott's discipline — patient first entry, hold through noise,
exit once and stop trading.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, List, Dict


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class BeliefConfig2:
    """Parameters for the experimental belief engine v2."""
    partial_tp_pts: float = 50.0
    spike_profit_pts: float = 100.0
    spike_profit_bars: int = 9
    warmup_bars: int = 12                    # CHANGED: 7 → 12
    min_reversal_minutes: float = 5.0        # NEW: cooldown between reversals
    session_end_time: str = "10:30"          # NEW: hard session end
    one_and_done: bool = True                # NEW: no re-entry after first exit
    first_entry_trend_filter: bool = True    # NEW: first entry must match slope
    # Resolve thresholds
    resolve_new_extreme_window: int = 5
    resolve_bounce_shrink_ratio: float = 0.6
    failed_expansion_reversal_bars: int = 3


# ---------------------------------------------------------------------------
# Evidence Types (same as baseline)
# ---------------------------------------------------------------------------

@dataclass
class Evidence:
    """Single piece of evidence collected on a bar."""
    bar_idx: int
    time: object
    event_type: str
    direction: str
    weight: str
    description: str


# ---------------------------------------------------------------------------
# Belief Engine v2
# ---------------------------------------------------------------------------

class BeliefEngineV2:
    """Experimental belief engine with session discipline and trend filtering."""

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
        self.session_done = False          # NEW: once True, no more entries

        # Belief state
        self.thesis_direction = 0
        self.confidence = 0.0
        self.resolve_state = "NO_RESOLVE"

        # Evidence tracking
        self.evidence_log: List[Evidence] = []
        self.failed_expansions = 0
        self.last_extreme_bar = 0
        self.last_extreme_price = 0.0

        # Reversal cooldown
        self.last_reversal_time = None     # NEW: timestamp of last reversal

        # Line values
        self.purple_val = 0.0
        self.blue_val = 0.0
        self.orange_val = 0.0
        self.yellow_val = 0.0

        # History
        self.recent_highs: List[float] = []
        self.recent_lows: List[float] = []

        # P/L tracking
        self.session_pl = 0.0

        # Output log
        self.bar_logs: List[Dict] = []

        # Blocked signal log (for debugging)
        self.blocked_signals: List[Dict] = []

    def process_bar(self, bar_idx: int, bar: dict, lines: dict, mech_signal: str = ""):
        """Process a single bar through the belief engine."""
        close = bar["Close"]
        high = bar["High"]
        low = bar["Low"]
        bar_time = bar["time"]
        prev_close = bar.get("prev_close", close)

        # Update line values
        self.purple_val = lines.get("purple", np.nan)
        self.blue_val = lines.get("blue", np.nan)
        self.orange_val = lines.get("orange", np.nan)
        self.yellow_val = lines.get("yellow", np.nan)

        prev_purple = lines.get("prev_purple", np.nan)
        prev_blue = lines.get("prev_blue", np.nan)
        prev_orange = lines.get("prev_orange", np.nan)
        prev_yellow = lines.get("prev_yellow", np.nan)

        # --- Session end check ---
        session_end_reached = False
        if hasattr(bar_time, 'strftime'):
            bar_hm = bar_time.strftime("%H:%M")
            session_end_reached = bar_hm >= self.cfg.session_end_time

        # Force exit at session end
        if session_end_reached and self.position != 0:
            action = "SESSION_EXIT"
            self._execute_action(action, bar_idx, bar)
            self.session_done = True
            self._log_bar(bar_idx, bar, [], action)
            return

        # If session is done (one-and-done), just log and return
        if self.session_done:
            self._log_bar(bar_idx, bar, [], "SESSION_DONE")
            return

        # --- Collect evidence ---
        bar_evidence = self._collect_evidence(bar_idx, bar, lines, prev_close,
                                               prev_purple, prev_blue, prev_orange, prev_yellow)
        self.evidence_log.extend(bar_evidence)

        # --- Update confidence ---
        self._update_confidence(bar_evidence)

        # --- Update resolve ---
        self._update_resolve(bar_idx, high, low, close)

        # --- Update recent highs/lows ---
        self.recent_highs.append(high)
        self.recent_lows.append(low)
        if len(self.recent_highs) > 20:
            self.recent_highs.pop(0)
        if len(self.recent_lows) > 20:
            self.recent_lows.pop(0)

        # --- Decide action ---
        action = self._decide_action(bar_idx, bar, bar_evidence, mech_signal)

        # --- Execute action ---
        self._execute_action(action, bar_idx, bar)

        # --- Log ---
        self._log_bar(bar_idx, bar, bar_evidence, action)

    def _log_bar(self, bar_idx: int, bar: dict, bar_evidence: list, action: str):
        """Log bar state."""
        close = bar["Close"]
        if self.position == 0 or self.entry_price == 0.0:
            display_pl = self.session_pl
        elif self.position == 1:
            display_pl = self.session_pl + (close - self.entry_price) * self.contracts
        else:
            display_pl = self.session_pl + (self.entry_price - close) * self.contracts

        self.bar_logs.append({
            "bar_idx": bar_idx,
            "time": bar["time"],
            "open": bar["Open"],
            "high": bar["High"],
            "low": bar["Low"],
            "close": close,
            "position": self.position,
            "contracts": self.contracts,
            "entry_price": self.entry_price,
            "confidence": self.confidence,
            "resolve_state": self.resolve_state,
            "failed_expansions": self.failed_expansions,
            "evidence_count": len(bar_evidence),
            "evidence_types": "|".join(e.event_type for e in bar_evidence),
            "action": action,
            "session_pl": display_pl,
            "partial_taken": self.partial_taken,
            "session_done": self.session_done,
        })

    def _collect_evidence(self, bar_idx, bar, lines, prev_close,
                          prev_purple, prev_blue, prev_orange, prev_yellow):
        """Collect evidence from line crosses and structure."""
        close = bar["Close"]
        high = bar["High"]
        low = bar["Low"]
        bar_evidence = []

        # Line crosses
        if not np.isnan(prev_purple) and prev_close <= prev_purple and close > self.purple_val:
            bar_evidence.append(Evidence(bar_idx, bar["time"], "PURPLE_CROSS_ABOVE", "BULLISH", "MEDIUM",
                                         f"Close {close:.0f} > purple {self.purple_val:.0f}"))

        if not np.isnan(prev_blue) and prev_close >= prev_blue and close < self.blue_val:
            bar_evidence.append(Evidence(bar_idx, bar["time"], "BLUE_CROSS_BELOW", "BEARISH", "MEDIUM",
                                         f"Close {close:.0f} < blue {self.blue_val:.0f}"))

        if not np.isnan(prev_orange) and prev_close <= prev_orange and close > self.orange_val:
            bar_evidence.append(Evidence(bar_idx, bar["time"], "ORANGE_CROSS_ABOVE", "BULLISH", "HIGH",
                                         f"Close {close:.0f} > orange {self.orange_val:.0f}"))

        if not np.isnan(prev_yellow) and prev_close >= prev_yellow and close < self.yellow_val:
            bar_evidence.append(Evidence(bar_idx, bar["time"], "YELLOW_CROSS_BELOW", "BEARISH", "HIGH",
                                         f"Close {close:.0f} < yellow {self.yellow_val:.0f}"))

        # Failed expansion
        if self.resolve_state in ("ESTABLISHED", "STRONG"):
            if len(self.recent_highs) >= 2:
                prev_high = max(self.recent_highs[-3:]) if len(self.recent_highs) >= 3 else self.recent_highs[-1]
                if high > prev_high and close < prev_high - 10.0:
                    self.failed_expansions += 1
                    bar_evidence.append(Evidence(bar_idx, bar["time"], "FAILED_EXPANSION_UP", "BEARISH", "MEDIUM",
                                                 f"High {high:.0f} > {prev_high:.0f} but close failed"))

            if len(self.recent_lows) >= 2:
                prev_low = min(self.recent_lows[-3:]) if len(self.recent_lows) >= 3 else self.recent_lows[-1]
                if low < prev_low and close > prev_low + 10.0:
                    self.failed_expansions += 1
                    bar_evidence.append(Evidence(bar_idx, bar["time"], "FAILED_EXPANSION_DOWN", "BULLISH", "MEDIUM",
                                                 f"Low {low:.0f} < {prev_low:.0f} but close recovered"))

        # Structure reclaim
        if self.position == -1 and not np.isnan(prev_purple):
            if prev_close <= prev_purple and close > self.purple_val:
                bar_evidence.append(Evidence(bar_idx, bar["time"], "STRUCTURE_RECLAIM", "BULLISH", "HIGH",
                                             "Price reclaimed purple while short"))

        if self.position == 1 and not np.isnan(prev_blue):
            if prev_close >= prev_blue and close < self.blue_val:
                bar_evidence.append(Evidence(bar_idx, bar["time"], "STRUCTURE_RECLAIM", "BEARISH", "HIGH",
                                             "Price broke blue while long"))

        return bar_evidence

    def _update_confidence(self, bar_evidence: List[Evidence]):
        """Update confidence based on new evidence."""
        weight_map = {"HIGH": 3.0, "MEDIUM": 1.5, "LOW": 0.5}
        for ev in bar_evidence:
            w = weight_map.get(ev.weight, 1.0)
            if self.position == 1:
                self.confidence += w if ev.direction == "BULLISH" else -w
            elif self.position == -1:
                self.confidence += w if ev.direction == "BEARISH" else -w
            else:
                self.confidence += w if ev.direction == "BULLISH" else -w

    def _update_resolve(self, bar_idx: int, high: float, low: float, close: float):
        """Update resolve state."""
        if self.position == 0:
            self.resolve_state = "NO_RESOLVE"
            return

        bars_in_trade = bar_idx - self.entry_bar_idx
        making_new_extremes = False

        if self.position == 1 and len(self.recent_highs) >= 3:
            if high >= max(self.recent_highs[-3:]):
                making_new_extremes = True
                self.last_extreme_bar = bar_idx
        elif self.position == -1 and len(self.recent_lows) >= 3:
            if low <= min(self.recent_lows[-3:]):
                making_new_extremes = True
                self.last_extreme_bar = bar_idx

        bars_since_extreme = bar_idx - self.last_extreme_bar

        if bars_in_trade < 3:
            self.resolve_state = "NO_RESOLVE"
        elif self.failed_expansions >= 2:
            self.resolve_state = "WEAKENING"
        elif bars_since_extreme <= self.cfg.resolve_new_extreme_window and making_new_extremes:
            self.resolve_state = "STRONG" if (bars_in_trade >= 15 and self.confidence >= 5.0) else "ESTABLISHED"
        elif bars_since_extreme <= 10 and self.confidence >= 2.0:
            self.resolve_state = "ESTABLISHED"
        elif self.confidence >= 1.0:
            self.resolve_state = "EMERGING"
        else:
            self.resolve_state = "NO_RESOLVE"

    def _decide_action(self, bar_idx: int, bar: dict, bar_evidence: List[Evidence], mech_signal: str = "") -> str:
        """Decide action with trend filter, cooldown, and session discipline."""
        close = bar["Close"]
        bar_time = bar["time"]

        # --- Warmup: no trading ---
        if bar_idx < self.cfg.warmup_bars:
            return "WAIT"

        # --- Partial TP ---
        if self.position != 0 and not self.partial_taken and self.entry_price != 0.0:
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            if unrealized >= self.cfg.partial_tp_pts:
                return "PARTIAL_TP"

        # --- Spike exit ---
        if self.position != 0 and self.entry_price != 0.0:
            bars_held = bar_idx - self.entry_bar_idx
            if 0 < bars_held <= self.cfg.spike_profit_bars:
                unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
                if unrealized >= self.cfg.spike_profit_pts:
                    return "SPIKE_EXIT"

        # --- Reversal cooldown check ---
        reversal_allowed = True
        if self.cfg.min_reversal_minutes > 0 and self.last_reversal_time is not None:
            if hasattr(bar_time, 'timestamp') and hasattr(self.last_reversal_time, 'timestamp'):
                mins_since = (bar_time - self.last_reversal_time).total_seconds() / 60.0
                if mins_since < self.cfg.min_reversal_minutes:
                    reversal_allowed = False

        # --- Thesis invalidation (immediate, ignores cooldown) ---
        for ev in bar_evidence:
            if ev.event_type == "STRUCTURE_RECLAIM":
                if reversal_allowed:
                    return "REVERSE"
                else:
                    self.blocked_signals.append({"time": bar_time, "action": "REVERSE",
                                                  "reason": "COOLDOWN", "evidence": ev.event_type})
            if ev.event_type in ("ORANGE_CROSS_ABOVE", "YELLOW_CROSS_BELOW"):
                if self.position == -1 and ev.direction == "BULLISH":
                    if reversal_allowed:
                        return "REVERSE"
                    else:
                        self.blocked_signals.append({"time": bar_time, "action": "REVERSE",
                                                      "reason": "COOLDOWN", "evidence": ev.event_type})
                if self.position == 1 and ev.direction == "BEARISH":
                    if reversal_allowed:
                        return "REVERSE"
                    else:
                        self.blocked_signals.append({"time": bar_time, "action": "REVERSE",
                                                      "reason": "COOLDOWN", "evidence": ev.event_type})

        # --- Flat: enter on line cross with trend filter ---
        if self.position == 0:
            for ev in bar_evidence:
                if ev.event_type in ("PURPLE_CROSS_ABOVE", "ORANGE_CROSS_ABOVE"):
                    if self._trend_filter_allows("BUY"):
                        return "BUY"
                    else:
                        self.blocked_signals.append({"time": bar_time, "action": "BUY",
                                                      "reason": "TREND_FILTER", "evidence": ev.event_type})
                if ev.event_type in ("BLUE_CROSS_BELOW", "YELLOW_CROSS_BELOW"):
                    if self._trend_filter_allows("SELL"):
                        return "SELL"
                    else:
                        self.blocked_signals.append({"time": bar_time, "action": "SELL",
                                                      "reason": "TREND_FILTER", "evidence": ev.event_type})
            return "HOLD"

        # --- In position: reversal logic with cooldown ---
        has_opposing_cross = any(
            (ev.event_type in ("PURPLE_CROSS_ABOVE", "ORANGE_CROSS_ABOVE") and self.position == -1) or
            (ev.event_type in ("BLUE_CROSS_BELOW", "YELLOW_CROSS_BELOW") and self.position == 1)
            for ev in bar_evidence
        )

        if has_opposing_cross:
            if not reversal_allowed:
                self.blocked_signals.append({"time": bar_time, "action": "REVERSE",
                                              "reason": "COOLDOWN", "evidence": "opposing_cross"})
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
        """Check if first entry direction matches dominant slope.
        
        For first entry only: BUY requires blue slope positive (uptrend),
        SELL requires purple slope negative (downtrend).
        After first trade, no filter applied.
        """
        if not self.cfg.first_entry_trend_filter:
            return True
        if self.first_trade_done:
            return True

        # Use recent price action: if recent highs are declining, trend is down
        if len(self.recent_highs) < 5:
            return True  # not enough data, allow

        recent_5_highs = self.recent_highs[-5:]
        recent_5_lows = self.recent_lows[-5:]

        # Simple trend: compare first half vs second half
        first_half_avg = np.mean(recent_5_highs[:3])
        second_half_avg = np.mean(recent_5_highs[3:])

        if direction == "BUY":
            # Allow BUY only if highs are rising (uptrend)
            return second_half_avg >= first_half_avg
        else:
            # Allow SELL only if highs are falling (downtrend)
            return second_half_avg <= first_half_avg

    def _execute_action(self, action: str, bar_idx: int, bar: dict):
        """Execute action, update position and P/L."""
        close = bar["Close"]
        bar_time = bar["time"]

        if action == "BUY":
            if self.position == -1:
                contracts_remaining = 1 if self.partial_taken else 2
                self.session_pl += (self.entry_price - close) * contracts_remaining
                self.last_reversal_time = bar_time
            self.position = 1
            self.contracts = 2
            self.entry_price = close
            self.entry_bar_idx = bar_idx
            self.entry_time = bar_time
            self.partial_taken = False
            self.failed_expansions = 0
            self.thesis_direction = 1
            self.confidence = 1.5
            self.first_trade_done = True

        elif action == "SELL":
            if self.position == 1:
                contracts_remaining = 1 if self.partial_taken else 2
                self.session_pl += (close - self.entry_price) * contracts_remaining
                self.last_reversal_time = bar_time
            self.position = -1
            self.contracts = 2
            self.entry_price = close
            self.entry_bar_idx = bar_idx
            self.entry_time = bar_time
            self.partial_taken = False
            self.failed_expansions = 0
            self.thesis_direction = -1
            self.confidence = 1.5
            self.first_trade_done = True

        elif action == "REVERSE":
            if self.position == 1:
                contracts_remaining = 1 if self.partial_taken else 2
                self.session_pl += (close - self.entry_price) * contracts_remaining
                self.position = -1
                self.thesis_direction = -1
            elif self.position == -1:
                contracts_remaining = 1 if self.partial_taken else 2
                self.session_pl += (self.entry_price - close) * contracts_remaining
                self.position = 1
                self.thesis_direction = 1
            self.contracts = 2
            self.entry_price = close
            self.entry_bar_idx = bar_idx
            self.entry_time = bar_time
            self.partial_taken = False
            self.failed_expansions = 0
            self.confidence = 1.5
            self.last_reversal_time = bar_time

        elif action == "PARTIAL_TP":
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            self.session_pl += unrealized
            self.partial_taken = True
            self.contracts = 1

        elif action == "SPIKE_EXIT":
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            contracts_remaining = 1 if self.partial_taken else 2
            self.session_pl += unrealized * contracts_remaining
            self.position = 0
            self.contracts = 0
            self.entry_price = 0.0
            self.partial_taken = False
            self.thesis_direction = 0
            self.confidence = 0.0
            self.failed_expansions = 0
            if self.cfg.one_and_done:
                self.session_done = True

        elif action == "SESSION_EXIT":
            # Force close at session end
            if self.position == 1:
                contracts_remaining = 1 if self.partial_taken else 2
                self.session_pl += (close - self.entry_price) * contracts_remaining
            elif self.position == -1:
                contracts_remaining = 1 if self.partial_taken else 2
                self.session_pl += (self.entry_price - close) * contracts_remaining
            self.position = 0
            self.contracts = 0
            self.entry_price = 0.0
            self.partial_taken = False
            self.session_done = True

    def run_session(self, algo_df: pd.DataFrame) -> pd.DataFrame:
        """Run the belief engine on an algo result DataFrame."""
        n = len(algo_df)
        for i in range(n):
            row = algo_df.iloc[i]
            prev_row = algo_df.iloc[i - 1] if i > 0 else row

            bar = {
                "time": algo_df.index[i],
                "Open": float(row["Open"]),
                "High": float(row["High"]),
                "Low": float(row["Low"]),
                "Close": float(row["Close"]),
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
