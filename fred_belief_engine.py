"""
fred_belief_engine.py — Stateful Belief Engine for FRED

Runs in parallel with the existing mechanical signal loop.
Tracks evidence, confidence, resolve, and failed expansions per bar.
Produces a debug log for validation against Scott's 6 screenshot sessions.
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
    # Resolve thresholds (behavioral, not point-based)
    resolve_new_extreme_window: int = 5      # bars to check for new highs/lows
    resolve_bounce_shrink_ratio: float = 0.6  # if bounce < 60% of previous, decay
    failed_expansion_reversal_bars: int = 3   # bars within which a new high must reverse to count as failed


# ---------------------------------------------------------------------------
# Evidence Types
# ---------------------------------------------------------------------------

@dataclass
class Evidence:
    """Single piece of evidence collected on a bar."""
    bar_idx: int
    time: object
    event_type: str       # e.g. "LINE_BREAK", "FAILED_EXPANSION", "STRUCTURE_RECLAIM", etc.
    direction: str        # "BULLISH" or "BEARISH"
    weight: str           # "HIGH", "MEDIUM", "LOW"
    description: str


# ---------------------------------------------------------------------------
# Belief Engine
# ---------------------------------------------------------------------------

class BeliefEngine:
    """Stateful belief engine that tracks evidence, confidence, and resolve."""

    def __init__(self, config: Optional[BeliefConfig] = None):
        self.cfg = config or BeliefConfig()

        # Position state
        self.position = 0          # +1 = long, -1 = short, 0 = flat
        self.contracts = 0         # number of contracts held
        self.entry_price = 0.0
        self.entry_bar_idx = 0
        self.partial_taken = False
        self.first_trade_done = False

        # Belief state
        self.thesis_direction = 0   # +1 = bullish thesis, -1 = bearish thesis, 0 = none
        self.confidence = 0.0       # accumulated evidence advantage
        self.resolve_state = "NO_RESOLVE"  # NO_RESOLVE, EMERGING, ESTABLISHED, STRONG

        # Evidence tracking
        self.evidence_log: List[Evidence] = []
        self.failed_expansions = 0
        self.last_extreme_bar = 0   # bar index of last new high/low
        self.last_extreme_price = 0.0
        self.prev_bounce_distance = 0.0  # distance of previous bounce from structure

        # Dynamic structure
        self.invalidation_level = 0.0
        self.invalidation_type = "NONE"  # "LINE", "CHANNEL", "ORANGE_YELLOW"
        self.channel_high = 0.0
        self.channel_low = 0.0
        self.channel_bars = 0

        # Line values (populated per bar from algo output)
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

        # Output log
        self.bar_logs: List[Dict] = []

    # -------------------------------------------------------------------
    # Core per-bar processing
    # -------------------------------------------------------------------

    def process_bar(self, bar_idx: int, bar: dict, lines: dict, mech_signal: str = ""):
        """Process a single bar through the belief engine.

        Args:
            bar_idx: integer index of this bar
            bar: dict with keys: time, Open, High, Low, Close, Volume
            lines: dict with keys: purple, blue, orange, yellow,
                   steep_purple (may be NaN), steep_blue (may be NaN),
                   prev_purple, prev_blue, prev_orange, prev_yellow
            mech_signal: mechanical algo signal for this bar ("BUY", "SELL", or "")
        """
        close = bar["Close"]
        high = bar["High"]
        low = bar["Low"]
        prev_close = bar.get("prev_close", close)

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

        # --- Collect evidence ---
        bar_evidence = []

        # 1. Line crosses
        if not np.isnan(prev_purple) and prev_close <= prev_purple and close > self.purple_val:
            bar_evidence.append(Evidence(bar_idx, bar["time"], "PURPLE_CROSS_ABOVE", "BULLISH", "MEDIUM",
                                         f"Close {close:.0f} crossed above purple {self.purple_val:.0f}"))

        if not np.isnan(prev_blue) and prev_close >= prev_blue and close < self.blue_val:
            bar_evidence.append(Evidence(bar_idx, bar["time"], "BLUE_CROSS_BELOW", "BEARISH", "MEDIUM",
                                         f"Close {close:.0f} crossed below blue {self.blue_val:.0f}"))

        if not np.isnan(prev_orange) and prev_close <= prev_orange and close > self.orange_val:
            bar_evidence.append(Evidence(bar_idx, bar["time"], "ORANGE_CROSS_ABOVE", "BULLISH", "HIGH",
                                         f"Close {close:.0f} crossed above orange {self.orange_val:.0f}"))

        if not np.isnan(prev_yellow) and prev_close >= prev_yellow and close < self.yellow_val:
            bar_evidence.append(Evidence(bar_idx, bar["time"], "YELLOW_CROSS_BELOW", "BEARISH", "HIGH",
                                         f"Close {close:.0f} crossed below yellow {self.yellow_val:.0f}"))

        # 2. Steep line crosses
        if not np.isnan(self.steep_purple_val) and not np.isnan(lines.get("prev_steep_purple", np.nan)):
            if prev_close <= lines["prev_steep_purple"] and close > self.steep_purple_val:
                bar_evidence.append(Evidence(bar_idx, bar["time"], "STEEP_PURPLE_CROSS_ABOVE", "BULLISH", "MEDIUM",
                                             f"Close {close:.0f} crossed above steep purple {self.steep_purple_val:.0f}"))

        if not np.isnan(self.steep_blue_val) and not np.isnan(lines.get("prev_steep_blue", np.nan)):
            if prev_close >= lines["prev_steep_blue"] and close < self.steep_blue_val:
                bar_evidence.append(Evidence(bar_idx, bar["time"], "STEEP_BLUE_CROSS_BELOW", "BEARISH", "MEDIUM",
                                             f"Close {close:.0f} crossed below steep blue {self.steep_blue_val:.0f}"))

        # 3. Failed expansion detection
        # Only count if: (a) resolve is ESTABLISHED or STRONG, (b) price exceeds prior extreme,
        # (c) close fails by more than 10 pts below/above that extreme
        min_fail_pts = 10.0
        if self.resolve_state in ("ESTABLISHED", "STRONG"):
            if len(self.recent_highs) >= 2:
                prev_high = max(self.recent_highs[-3:]) if len(self.recent_highs) >= 3 else self.recent_highs[-1]
                if high > prev_high and close < prev_high - min_fail_pts:
                    self.failed_expansions += 1
                    bar_evidence.append(Evidence(bar_idx, bar["time"], "FAILED_EXPANSION_UP", "BEARISH", "MEDIUM",
                                                 f"High {high:.0f} > prev high {prev_high:.0f} but close {close:.0f} failed by {prev_high - close:.0f} pts"))

            if len(self.recent_lows) >= 2:
                prev_low = min(self.recent_lows[-3:]) if len(self.recent_lows) >= 3 else self.recent_lows[-1]
                if low < prev_low and close > prev_low + min_fail_pts:
                    self.failed_expansions += 1
                    bar_evidence.append(Evidence(bar_idx, bar["time"], "FAILED_EXPANSION_DOWN", "BULLISH", "MEDIUM",
                                                 f"Low {low:.0f} < prev low {prev_low:.0f} but close {close:.0f} recovered by {close - prev_low:.0f} pts"))

        # 4. Structure reclaim (thesis invalidation)
        if self.position == -1 and not np.isnan(prev_purple):
            if prev_close <= prev_purple and close > self.purple_val:
                bar_evidence.append(Evidence(bar_idx, bar["time"], "STRUCTURE_RECLAIM", "BULLISH", "HIGH",
                                             f"Price reclaimed purple while short — thesis invalidated"))

        if self.position == 1 and not np.isnan(prev_blue):
            if prev_close >= prev_blue and close < self.blue_val:
                bar_evidence.append(Evidence(bar_idx, bar["time"], "STRUCTURE_RECLAIM", "BEARISH", "HIGH",
                                             f"Price broke blue while long — thesis invalidated"))

        # 5. Orange/yellow breakout (confidence increase for existing position)
        if self.position == 1 and not np.isnan(prev_orange):
            if prev_close <= prev_orange and close > self.orange_val:
                bar_evidence.append(Evidence(bar_idx, bar["time"], "ORANGE_BREAKOUT_CONFIRM", "BULLISH", "HIGH",
                                             f"Close above orange while long — confidence increase"))

        if self.position == -1 and not np.isnan(prev_yellow):
            if prev_close >= prev_yellow and close < self.yellow_val:
                bar_evidence.append(Evidence(bar_idx, bar["time"], "YELLOW_BREAKOUT_CONFIRM", "BEARISH", "HIGH",
                                             f"Close below yellow while short — confidence increase"))

        # 6. Bounce from structure (thesis confirmation)
        if self.position == 1 and not np.isnan(self.blue_val):
            if low <= self.blue_val + 5.0 and close > self.blue_val:
                bar_evidence.append(Evidence(bar_idx, bar["time"], "BOUNCE_FROM_BLUE", "BULLISH", "LOW",
                                             f"Low {low:.0f} tested blue {self.blue_val:.0f}, close held above"))

        if self.position == -1 and not np.isnan(self.purple_val):
            if high >= self.purple_val - 5.0 and close < self.purple_val:
                bar_evidence.append(Evidence(bar_idx, bar["time"], "BOUNCE_FROM_PURPLE", "BEARISH", "LOW",
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

        # --- Compute session P/L (realized + unrealized) ---
        if self.position == 0 or self.entry_price == 0.0:
            display_pl = self.session_pl
        elif self.position == 1:
            display_pl = self.session_pl + (close - self.entry_price)
        else:
            display_pl = self.session_pl + (self.entry_price - close)

        # --- Log ---
        self.bar_logs.append({
            "bar_idx": bar_idx,
            "time": bar["time"],
            "open": bar["Open"],
            "high": high,
            "low": low,
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
            "invalidation_level": self.invalidation_level,
            "invalidation_type": self.invalidation_type,
        })

    # -------------------------------------------------------------------
    # Confidence update
    # -------------------------------------------------------------------

    def _update_confidence(self, bar_evidence: List[Evidence]):
        """Update confidence based on new evidence."""
        weight_map = {"HIGH": 3.0, "MEDIUM": 1.5, "LOW": 0.5}

        for ev in bar_evidence:
            w = weight_map.get(ev.weight, 1.0)

            # Determine if evidence supports or opposes current position
            if self.position == 1:  # long
                if ev.direction == "BULLISH":
                    self.confidence += w
                else:
                    self.confidence -= w
            elif self.position == -1:  # short
                if ev.direction == "BEARISH":
                    self.confidence += w
                else:
                    self.confidence -= w
            else:  # flat — evidence builds toward thesis formation
                if ev.direction == "BULLISH":
                    self.confidence += w
                else:
                    self.confidence -= w

    # -------------------------------------------------------------------
    # Resolve state machine
    # -------------------------------------------------------------------

    def _update_resolve(self, bar_idx: int, high: float, low: float, close: float):
        """Update resolve state based on behavioral indicators."""
        if self.position == 0:
            self.resolve_state = "NO_RESOLVE"
            return

        bars_in_trade = bar_idx - self.entry_bar_idx

        # Check for new extremes
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

        # Bars since last new extreme
        bars_since_extreme = bar_idx - self.last_extreme_bar

        # Determine resolve level
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
    # Decision logic
    # -------------------------------------------------------------------

    def _decide_action(self, bar_idx: int, bar: dict, bar_evidence: List[Evidence], mech_signal: str = "") -> str:
        """Decide action based on mechanical signal + confidence + resolve."""
        close = bar["Close"]

        # --- Warmup: no trading ---
        if bar_idx < self.cfg.warmup_bars:
            return "WAIT"

        # --- Partial TP check (always fires mechanically) ---
        if self.position != 0 and not self.partial_taken and self.entry_price != 0.0:
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            if unrealized >= self.cfg.partial_tp_pts:
                return "PARTIAL_TP"

        # --- Spike exit check (always fires mechanically) ---
        if self.position != 0 and self.entry_price != 0.0:
            bars_held = bar_idx - self.entry_bar_idx
            if bars_held <= self.cfg.spike_profit_bars and bars_held > 0:
                unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
                if unrealized >= self.cfg.spike_profit_pts:
                    return "SPIKE_EXIT"

        # --- No mechanical signal this bar → hold ---
        if mech_signal not in ("BUY", "SELL"):
            return "HOLD"

        # --- Mechanical signal detected — apply belief filter ---

        # If flat, always enter (System A: first entry)
        if self.position == 0:
            return mech_signal  # "BUY" or "SELL"

        # If signal is in SAME direction as position, ignore (already positioned)
        if mech_signal == "BUY" and self.position == 1:
            return "HOLD"
        if mech_signal == "SELL" and self.position == -1:
            return "HOLD"

        # --- Signal is OPPOSING current position — reversal decision ---
        # Check for thesis invalidation (HIGH weight evidence this bar)
        thesis_invalidated = any(
            ev.event_type in ("STRUCTURE_RECLAIM", "ORANGE_CROSS_ABOVE", "YELLOW_CROSS_BELOW",
                              "ORANGE_BREAKOUT_CONFIRM")
            and ((ev.direction == "BULLISH" and self.position == -1) or
                 (ev.direction == "BEARISH" and self.position == 1))
            for ev in bar_evidence
        )

        # Apply resolve-based filtering
        if self.resolve_state == "NO_RESOLVE":
            # Chop mode: reverse on every opposing signal
            return "REVERSE"

        elif self.resolve_state == "EMERGING":
            # Low resolve: reverse on opposing signal
            return "REVERSE"

        elif self.resolve_state == "ESTABLISHED":
            # Moderate resolve: require decay OR invalidation
            if thesis_invalidated:
                return "REVERSE"
            if self.failed_expansions >= 2:
                return "REVERSE"
            if self.confidence <= 0:
                return "REVERSE"
            # Discount single break — hold through it
            return "HOLD"

        elif self.resolve_state == "STRONG":
            # Strong resolve: only reverse on invalidation or deep negative confidence
            if thesis_invalidated:
                return "REVERSE"
            if self.confidence <= -3.0:
                return "REVERSE"
            # Protect strong resolve
            return "HOLD"

        elif self.resolve_state == "WEAKENING":
            # Decay detected: reverse on any opposing signal
            return "REVERSE"

        return "HOLD"

    # -------------------------------------------------------------------
    # Action execution
    # -------------------------------------------------------------------

    def _execute_action(self, action: str, bar_idx: int, bar: dict):
        """Execute the decided action, update position and P/L."""
        close = bar["Close"]

        if action == "BUY":
            if self.position == -1:
                # Close short
                contracts_remaining = 1 if self.partial_taken else 2
                self.session_pl += (self.entry_price - close) * contracts_remaining
            self.position = 1
            self.contracts = 2
            self.entry_price = close
            self.entry_bar_idx = bar_idx
            self.partial_taken = False
            self.failed_expansions = 0
            self.thesis_direction = 1
            self.confidence = 1.5  # initial confidence on entry
            self.first_trade_done = True

        elif action == "SELL":
            if self.position == 1:
                # Close long
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

        elif action == "REVERSE":
            if self.position == 1:
                # Close long, open short
                contracts_remaining = 1 if self.partial_taken else 2
                self.session_pl += (close - self.entry_price) * contracts_remaining
                self.position = -1
                self.thesis_direction = -1
            elif self.position == -1:
                # Close short, open long
                contracts_remaining = 1 if self.partial_taken else 2
                self.session_pl += (self.entry_price - close) * contracts_remaining
                self.position = 1
                self.thesis_direction = 1
            self.contracts = 2
            self.entry_price = close
            self.entry_bar_idx = bar_idx
            self.partial_taken = False
            self.failed_expansions = 0
            self.confidence = 1.5

        elif action == "PARTIAL_TP":
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            self.session_pl += unrealized  # book 1 contract
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

    # -------------------------------------------------------------------
    # Session runner
    # -------------------------------------------------------------------

    def run_session(self, algo_df: pd.DataFrame) -> pd.DataFrame:
        """Run the belief engine on an algo result DataFrame.

        Args:
            algo_df: DataFrame from run_trading_algo_fast() with columns:
                     Close, High, Low, Open, purple_ray, blue_ray, orange_ray, yellow_ray,
                     signal (BUY/SELL/""), and optionally steep line columns.

        Returns:
            DataFrame with per-bar belief engine log.
        """
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

            # Extract mechanical signal from algo output
            mech_signal = ""
            if "signal" in row.index:
                sig = row["signal"]
                if sig in ("BUY", "SELL"):
                    mech_signal = sig

            self.process_bar(i, bar, lines, mech_signal)

        return pd.DataFrame(self.bar_logs)


# ---------------------------------------------------------------------------
# Validation runner — compare belief engine to Scott's trades
# ---------------------------------------------------------------------------

def validate_session(date_str: str, scott_trades: List[Dict], algo_df: pd.DataFrame) -> pd.DataFrame:
    """Run belief engine on a session and compare to Scott's actual trades.

    Args:
        date_str: e.g. "2026-04-21"
        scott_trades: list of dicts with keys: time, action, price, reason
        algo_df: DataFrame from run_trading_algo_fast()

    Returns:
        DataFrame with belief engine log + comparison column
    """
    engine = BeliefEngine()
    result = engine.run_session(algo_df)

    # Add Scott's trades as a comparison column
    scott_times = {t["time"]: t for t in scott_trades}
    result["scott_action"] = ""
    result["scott_price"] = np.nan
    result["scott_reason"] = ""

    for idx, row in result.iterrows():
        bar_time = row["time"]
        # Check if Scott had a trade within 1 minute of this bar
        for st_time, st in scott_times.items():
            if abs((bar_time - st_time).total_seconds()) < 90:
                result.at[idx, "scott_action"] = st["action"]
                result.at[idx, "scott_price"] = st["price"]
                result.at[idx, "scott_reason"] = st.get("reason", "")
                break

    return result


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("BeliefEngine loaded. Use run_session(algo_df) to process a day.")
    print("Use validate_session(date_str, scott_trades, algo_df) to compare against Scott.")
