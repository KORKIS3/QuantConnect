"""
belief_engine_experiment.py — A/B Test: Noon Hard Stop + Afternoon Re-Engagement

Changes vs baseline:
1. Hard stop at 12:00 ET — exit all positions, no new entries 12:00–13:45.
2. Afternoon re-engagement 13:45–16:00 — standard belief engine logic resumes.
3. Enhanced logging for per-hour P/L and comparison metrics.

All other logic (evidence, confidence, resolve, failed expansions, partial TP,
spike exit) is identical to baseline_belief_engine.py.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, List, Dict


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class BeliefConfig:
    """Parameters for the belief engine."""
    partial_tp_pts: float = 50.0
    spike_profit_pts: float = 100.0
    spike_profit_bars: int = 9
    warmup_bars: int = 7
    steep_line_spawn_distance: float = 50.0
    resolve_new_extreme_window: int = 5
    resolve_bounce_shrink_ratio: float = 0.6
    failed_expansion_reversal_bars: int = 3
    # Experiment-specific
    noon_hard_stop: str = "12:00"          # exit all at this time
    afternoon_reentry: str = "13:45"       # resume entries at this time
    afternoon_close: str = "16:00"         # stop entries after this time


# ---------------------------------------------------------------------------
# Evidence Types
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
# Experimental Belief Engine
# ---------------------------------------------------------------------------

class BeliefEngineExperiment:
    """Belief engine with noon hard stop and afternoon re-engagement window."""

    def __init__(self, config: Optional[BeliefConfig] = None):
        self.cfg = config or BeliefConfig()

        # Position state
        self.position = 0
        self.contracts = 0
        self.entry_price = 0.0
        self.entry_bar_idx = 0
        self.partial_taken = False
        self.first_trade_done = False

        # Belief state
        self.thesis_direction = 0
        self.confidence = 0.0
        self.resolve_state = "NO_RESOLVE"

        # Evidence tracking
        self.evidence_log: List[Evidence] = []
        self.failed_expansions = 0
        self.last_extreme_bar = 0
        self.last_extreme_price = 0.0
        self.prev_bounce_distance = 0.0

        # Dynamic structure
        self.invalidation_level = 0.0
        self.invalidation_type = "NONE"
        self.channel_high = 0.0
        self.channel_low = 0.0
        self.channel_bars = 0

        # Line values
        self.purple_val = 0.0
        self.blue_val = 0.0
        self.orange_val = 0.0
        self.yellow_val = 0.0
        self.steep_purple_val = np.nan
        self.steep_blue_val = np.nan

        # History for resolve detection
        self.recent_highs: List[float] = []
        self.recent_lows: List[float] = []
        self.recent_bounces: List[float] = []

        # P/L tracking
        self.session_pl = 0.0

        # Experiment state
        self.noon_stopped = False       # True after noon hard stop fires
        self.afternoon_active = False   # True once 13:45 reached

        # Trade log (enhanced for A/B)
        self.trades: List[Dict] = []

        # Output log
        self.bar_logs: List[Dict] = []

    # -------------------------------------------------------------------
    # Time-window checks
    # -------------------------------------------------------------------

    def _is_in_dead_zone(self, bar_time) -> bool:
        """Return True if bar is in the 12:00–13:45 no-trade window."""
        t = bar_time
        if hasattr(t, 'hour'):
            if t.hour == 12:
                return True
            if t.hour == 13 and t.minute < 45:
                return True
        return False

    def _is_noon_stop(self, bar_time) -> bool:
        """Return True if this bar is exactly at or past 12:00 and we haven't stopped yet."""
        if self.noon_stopped:
            return False
        t = bar_time
        if hasattr(t, 'hour'):
            if t.hour > 12 or (t.hour == 12 and t.minute >= 0):
                return True
        return False

    def _is_after_afternoon_close(self, bar_time) -> bool:
        """Return True if past 16:00 — no new entries."""
        t = bar_time
        if hasattr(t, 'hour'):
            if t.hour >= 16:
                return True
        return False

    # -------------------------------------------------------------------
    # Core per-bar processing
    # -------------------------------------------------------------------

    def process_bar(self, bar_idx: int, bar: dict, lines: dict, mech_signal: str = ""):
        """Process a single bar through the experimental belief engine."""
        close = bar["Close"]
        high = bar["High"]
        low = bar["Low"]
        prev_close = bar.get("prev_close", close)
        bar_time = bar["time"]

        # Update line values
        self.purple_val = lines.get("purple", np.nan)
        self.blue_val = lines.get("blue", np.nan)
        self.orange_val = lines.get("orange", np.nan)
        self.yellow_val = lines.get("yellow", np.nan)
        self.steep_purple_val = lines.get("steep_purple", np.nan)
        self.steep_blue_val = lines.get("steep_blue", np.nan)

        prev_purple = lines.get("prev_purple", np.nan)
        prev_blue = lines.get("prev_blue", np.nan)
        prev_orange = lines.get("prev_orange", np.nan)
        prev_yellow = lines.get("prev_yellow", np.nan)

        # --- EXPERIMENT: Noon hard stop ---
        if self._is_noon_stop(bar_time):
            self.noon_stopped = True
            if self.position != 0:
                # Force exit at noon
                self._force_exit(bar_idx, bar, reason="NOON_HARD_STOP")
            self._log_bar(bar_idx, bar, "NOON_HARD_STOP")
            return

        # --- EXPERIMENT: Dead zone (12:00–13:45) — no entries, just log ---
        if self._is_in_dead_zone(bar_time):
            self._log_bar(bar_idx, bar, "DEAD_ZONE")
            return

        # --- EXPERIMENT: Afternoon re-engagement ---
        if self.noon_stopped and not self.afternoon_active:
            if not self._is_in_dead_zone(bar_time) and not self._is_after_afternoon_close(bar_time):
                # We've exited the dead zone — reset for afternoon session
                self.afternoon_active = True
                self.confidence = 0.0
                self.resolve_state = "NO_RESOLVE"
                self.failed_expansions = 0
                self.recent_highs.clear()
                self.recent_lows.clear()

        # --- EXPERIMENT: No new entries after 16:00 ---
        if self._is_after_afternoon_close(bar_time):
            # If in position, let it ride to session end (no new entries)
            self._log_bar(bar_idx, bar, "AFTER_CLOSE")
            return

        # --- Standard belief engine logic below ---
        bar_evidence = []

        # 1. Line crosses
        if not np.isnan(prev_purple) and prev_close <= prev_purple and close > self.purple_val:
            bar_evidence.append(Evidence(bar_idx, bar_time, "PURPLE_CROSS_ABOVE", "BULLISH", "MEDIUM",
                                         f"Close {close:.0f} crossed above purple {self.purple_val:.0f}"))

        if not np.isnan(prev_blue) and prev_close >= prev_blue and close < self.blue_val:
            bar_evidence.append(Evidence(bar_idx, bar_time, "BLUE_CROSS_BELOW", "BEARISH", "MEDIUM",
                                         f"Close {close:.0f} crossed below blue {self.blue_val:.0f}"))

        if not np.isnan(prev_orange) and prev_close <= prev_orange and close > self.orange_val:
            bar_evidence.append(Evidence(bar_idx, bar_time, "ORANGE_CROSS_ABOVE", "BULLISH", "HIGH",
                                         f"Close {close:.0f} crossed above orange {self.orange_val:.0f}"))

        if not np.isnan(prev_yellow) and prev_close >= prev_yellow and close < self.yellow_val:
            bar_evidence.append(Evidence(bar_idx, bar_time, "YELLOW_CROSS_BELOW", "BEARISH", "HIGH",
                                         f"Close {close:.0f} crossed below yellow {self.yellow_val:.0f}"))

        # 2. Steep line crosses
        if not np.isnan(self.steep_purple_val) and not np.isnan(lines.get("prev_steep_purple", np.nan)):
            if prev_close <= lines["prev_steep_purple"] and close > self.steep_purple_val:
                bar_evidence.append(Evidence(bar_idx, bar_time, "STEEP_PURPLE_CROSS_ABOVE", "BULLISH", "MEDIUM",
                                             f"Close {close:.0f} crossed above steep purple {self.steep_purple_val:.0f}"))

        if not np.isnan(self.steep_blue_val) and not np.isnan(lines.get("prev_steep_blue", np.nan)):
            if prev_close >= lines["prev_steep_blue"] and close < self.steep_blue_val:
                bar_evidence.append(Evidence(bar_idx, bar_time, "STEEP_BLUE_CROSS_BELOW", "BEARISH", "MEDIUM",
                                             f"Close {close:.0f} crossed below steep blue {self.steep_blue_val:.0f}"))

        # 3. Failed expansion detection
        min_fail_pts = 10.0
        if self.resolve_state in ("ESTABLISHED", "STRONG"):
            if len(self.recent_highs) >= 2:
                prev_high = max(self.recent_highs[-3:]) if len(self.recent_highs) >= 3 else self.recent_highs[-1]
                if high > prev_high and close < prev_high - min_fail_pts:
                    self.failed_expansions += 1
                    bar_evidence.append(Evidence(bar_idx, bar_time, "FAILED_EXPANSION_UP", "BEARISH", "MEDIUM",
                                                 f"High {high:.0f} > prev high {prev_high:.0f} but close {close:.0f} failed"))

            if len(self.recent_lows) >= 2:
                prev_low = min(self.recent_lows[-3:]) if len(self.recent_lows) >= 3 else self.recent_lows[-1]
                if low < prev_low and close > prev_low + min_fail_pts:
                    self.failed_expansions += 1
                    bar_evidence.append(Evidence(bar_idx, bar_time, "FAILED_EXPANSION_DOWN", "BULLISH", "MEDIUM",
                                                 f"Low {low:.0f} < prev low {prev_low:.0f} but close {close:.0f} recovered"))

        # 4. Structure reclaim
        if self.position == -1 and not np.isnan(prev_purple):
            if prev_close <= prev_purple and close > self.purple_val:
                bar_evidence.append(Evidence(bar_idx, bar_time, "STRUCTURE_RECLAIM", "BULLISH", "HIGH",
                                             f"Price reclaimed purple while short — thesis invalidated"))

        if self.position == 1 and not np.isnan(prev_blue):
            if prev_close >= prev_blue and close < self.blue_val:
                bar_evidence.append(Evidence(bar_idx, bar_time, "STRUCTURE_RECLAIM", "BEARISH", "HIGH",
                                             f"Price broke blue while long — thesis invalidated"))

        # 5. Orange/yellow breakout confirm
        if self.position == 1 and not np.isnan(prev_orange):
            if prev_close <= prev_orange and close > self.orange_val:
                bar_evidence.append(Evidence(bar_idx, bar_time, "ORANGE_BREAKOUT_CONFIRM", "BULLISH", "HIGH",
                                             f"Close above orange while long — confidence increase"))

        if self.position == -1 and not np.isnan(prev_yellow):
            if prev_close >= prev_yellow and close < self.yellow_val:
                bar_evidence.append(Evidence(bar_idx, bar_time, "YELLOW_BREAKOUT_CONFIRM", "BEARISH", "HIGH",
                                             f"Close below yellow while short — confidence increase"))

        # 6. Bounce from structure
        if self.position == 1 and not np.isnan(self.blue_val):
            if low <= self.blue_val + 5.0 and close > self.blue_val:
                bar_evidence.append(Evidence(bar_idx, bar_time, "BOUNCE_FROM_BLUE", "BULLISH", "LOW",
                                             f"Low {low:.0f} tested blue {self.blue_val:.0f}, close held above"))

        if self.position == -1 and not np.isnan(self.purple_val):
            if high >= self.purple_val - 5.0 and close < self.purple_val:
                bar_evidence.append(Evidence(bar_idx, bar_time, "BOUNCE_FROM_PURPLE", "BEARISH", "LOW",
                                             f"High {high:.0f} tested purple {self.purple_val:.0f}, close held below"))

        # Store evidence
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
        self._log_bar(bar_idx, bar, action)

    # -------------------------------------------------------------------
    # Force exit (noon hard stop)
    # -------------------------------------------------------------------

    def _force_exit(self, bar_idx: int, bar: dict, reason: str = "FORCE_EXIT"):
        """Force close all positions."""
        close = bar["Close"]
        if self.position != 0:
            contracts_remaining = 1 if self.partial_taken else 2
            if self.position == 1:
                self.session_pl += (close - self.entry_price) * contracts_remaining
            else:
                self.session_pl += (self.entry_price - close) * contracts_remaining

            self.trades.append({
                "bar_idx": bar_idx,
                "time": bar["time"],
                "action": reason,
                "price": close,
                "position_before": self.position,
                "pl_realized": (close - self.entry_price) * contracts_remaining if self.position == 1
                               else (self.entry_price - close) * contracts_remaining,
            })

            self.position = 0
            self.contracts = 0
            self.entry_price = 0.0
            self.partial_taken = False
            self.thesis_direction = 0
            self.confidence = 0.0
            self.failed_expansions = 0

    # -------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------

    def _log_bar(self, bar_idx: int, bar: dict, action: str):
        """Append bar log entry."""
        close = bar["Close"]
        if self.position == 0 or self.entry_price == 0.0:
            display_pl = self.session_pl
        elif self.position == 1:
            display_pl = self.session_pl + (close - self.entry_price)
        else:
            display_pl = self.session_pl + (self.entry_price - close)

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
            "action": action,
            "session_pl": display_pl,
            "partial_taken": self.partial_taken,
            "noon_stopped": self.noon_stopped,
            "afternoon_active": self.afternoon_active,
        })

    # -------------------------------------------------------------------
    # Confidence update (identical to baseline)
    # -------------------------------------------------------------------

    def _update_confidence(self, bar_evidence: List[Evidence]):
        weight_map = {"HIGH": 3.0, "MEDIUM": 1.5, "LOW": 0.5}
        for ev in bar_evidence:
            w = weight_map.get(ev.weight, 1.0)
            if self.position == 1:
                self.confidence += w if ev.direction == "BULLISH" else -w
            elif self.position == -1:
                self.confidence += w if ev.direction == "BEARISH" else -w
            else:
                self.confidence += w if ev.direction == "BULLISH" else -w

    # -------------------------------------------------------------------
    # Resolve state machine (identical to baseline)
    # -------------------------------------------------------------------

    def _update_resolve(self, bar_idx: int, high: float, low: float, close: float):
        if self.position == 0:
            self.resolve_state = "NO_RESOLVE"
            return

        bars_in_trade = bar_idx - self.entry_bar_idx
        making_new_extremes = False

        if self.position == 1 and len(self.recent_highs) >= 3:
            if high >= max(self.recent_highs[-3:]):
                making_new_extremes = True
                self.last_extreme_bar = bar_idx
                self.last_extreme_price = high
        elif self.position == -1 and len(self.recent_lows) >= 3:
            if low <= min(self.recent_lows[-3:]):
                making_new_extremes = True
                self.last_extreme_bar = bar_idx
                self.last_extreme_price = low

        bars_since_extreme = bar_idx - self.last_extreme_bar

        if bars_in_trade < 3:
            self.resolve_state = "NO_RESOLVE"
        elif self.failed_expansions >= 2:
            self.resolve_state = "WEAKENING"
        elif bars_since_extreme <= self.cfg.resolve_new_extreme_window and making_new_extremes:
            if bars_in_trade >= 15 and self.confidence >= 5.0:
                self.resolve_state = "STRONG"
            else:
                self.resolve_state = "ESTABLISHED"
        elif bars_since_extreme <= 10 and self.confidence >= 2.0:
            self.resolve_state = "ESTABLISHED"
        elif self.confidence >= 1.0:
            self.resolve_state = "EMERGING"
        else:
            self.resolve_state = "NO_RESOLVE"

    # -------------------------------------------------------------------
    # Decision logic (identical to baseline)
    # -------------------------------------------------------------------

    def _decide_action(self, bar_idx: int, bar: dict, bar_evidence: List[Evidence], mech_signal: str = "") -> str:
        close = bar["Close"]

        if bar_idx < self.cfg.warmup_bars:
            return "WAIT"

        # Partial TP
        if self.position != 0 and not self.partial_taken and self.entry_price != 0.0:
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            if unrealized >= self.cfg.partial_tp_pts:
                return "PARTIAL_TP"

        # Spike exit
        if self.position != 0 and self.entry_price != 0.0:
            bars_held = bar_idx - self.entry_bar_idx
            if bars_held <= self.cfg.spike_profit_bars and bars_held > 0:
                unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
                if unrealized >= self.cfg.spike_profit_pts:
                    return "SPIKE_EXIT"

        # Thesis invalidation
        for ev in bar_evidence:
            if ev.event_type == "STRUCTURE_RECLAIM":
                return "REVERSE"
            if ev.event_type in ("ORANGE_CROSS_ABOVE", "YELLOW_CROSS_BELOW"):
                if self.position == -1 and ev.direction == "BULLISH":
                    return "REVERSE"
                if self.position == 1 and ev.direction == "BEARISH":
                    return "REVERSE"

        # Resolve-dependent reversal
        has_opposing_cross = any(
            (ev.event_type in ("PURPLE_CROSS_ABOVE", "STEEP_PURPLE_CROSS_ABOVE", "ORANGE_CROSS_ABOVE") and self.position == -1) or
            (ev.event_type in ("BLUE_CROSS_BELOW", "STEEP_BLUE_CROSS_BELOW", "YELLOW_CROSS_BELOW") and self.position == 1)
            for ev in bar_evidence
        )

        if self.position == 0:
            for ev in bar_evidence:
                if ev.event_type in ("PURPLE_CROSS_ABOVE", "STEEP_PURPLE_CROSS_ABOVE", "ORANGE_CROSS_ABOVE"):
                    return "BUY"
                if ev.event_type in ("BLUE_CROSS_BELOW", "STEEP_BLUE_CROSS_BELOW", "YELLOW_CROSS_BELOW"):
                    return "SELL"
            return "HOLD"

        if has_opposing_cross:
            if self.resolve_state == "NO_RESOLVE":
                return "REVERSE"
            elif self.resolve_state == "EMERGING":
                return "REVERSE"
            elif self.resolve_state == "ESTABLISHED":
                if self.failed_expansions >= 2:
                    return "REVERSE"
                elif self.confidence <= 0:
                    return "REVERSE"
                else:
                    return "HOLD"
            elif self.resolve_state == "STRONG":
                if self.confidence <= -3.0:
                    return "REVERSE"
                else:
                    return "HOLD"
            elif self.resolve_state == "WEAKENING":
                return "REVERSE"

        return "HOLD"

    # -------------------------------------------------------------------
    # Action execution (identical to baseline)
    # -------------------------------------------------------------------

    def _execute_action(self, action: str, bar_idx: int, bar: dict):
        close = bar["Close"]

        if action == "BUY":
            if self.position == -1:
                contracts_remaining = 1 if self.partial_taken else 2
                self.session_pl += (self.entry_price - close) * contracts_remaining
            self.position = 1
            self.contracts = 2
            self.entry_price = close
            self.entry_bar_idx = bar_idx
            self.partial_taken = False
            self.failed_expansions = 0
            self.thesis_direction = 1
            self.confidence = 1.5
            self.first_trade_done = True
            self.trades.append({"bar_idx": bar_idx, "time": bar["time"], "action": "BUY", "price": close})

        elif action == "SELL":
            if self.position == 1:
                contracts_remaining = 1 if self.partial_taken else 2
                self.session_pl += (close - self.entry_price) * contracts_remaining
            self.position = -1
            self.contracts = 2
            self.entry_price = close
            self.entry_bar_idx = bar_idx
            self.partial_taken = False
            self.failed_expansions = 0
            self.thesis_direction = -1
            self.confidence = 1.5
            self.first_trade_done = True
            self.trades.append({"bar_idx": bar_idx, "time": bar["time"], "action": "SELL", "price": close})

        elif action == "REVERSE":
            if self.position == 1:
                contracts_remaining = 1 if self.partial_taken else 2
                self.session_pl += (close - self.entry_price) * contracts_remaining
                self.position = -1
                self.thesis_direction = -1
                self.trades.append({"bar_idx": bar_idx, "time": bar["time"], "action": "REVERSE_SHORT", "price": close})
            elif self.position == -1:
                contracts_remaining = 1 if self.partial_taken else 2
                self.session_pl += (self.entry_price - close) * contracts_remaining
                self.position = 1
                self.thesis_direction = 1
                self.trades.append({"bar_idx": bar_idx, "time": bar["time"], "action": "REVERSE_LONG", "price": close})
            self.contracts = 2
            self.entry_price = close
            self.entry_bar_idx = bar_idx
            self.partial_taken = False
            self.failed_expansions = 0
            self.confidence = 1.5

        elif action == "PARTIAL_TP":
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            self.session_pl += unrealized
            self.partial_taken = True
            self.contracts = 1
            self.trades.append({"bar_idx": bar_idx, "time": bar["time"], "action": "PARTIAL_TP", "price": close})

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
            self.trades.append({"bar_idx": bar_idx, "time": bar["time"], "action": "SPIKE_EXIT", "price": close})

    # -------------------------------------------------------------------
    # Session runner
    # -------------------------------------------------------------------

    def run_session(self, algo_df: pd.DataFrame) -> pd.DataFrame:
        """Run the experimental belief engine on an algo result DataFrame."""
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
                "steep_purple": np.nan,
                "steep_blue": np.nan,
                "prev_steep_purple": np.nan,
                "prev_steep_blue": np.nan,
            }

            mech_signal = ""
            if "signal" in row.index:
                sig = row["signal"]
                if sig in ("BUY", "SELL"):
                    mech_signal = sig

            self.process_bar(i, bar, lines, mech_signal)

        return pd.DataFrame(self.bar_logs)
