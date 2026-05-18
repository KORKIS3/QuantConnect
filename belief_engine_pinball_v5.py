"""
belief_engine_pinball.py — Pinball CHOP-first Engine

Philosophy: Every day is CHOP until proven TREND.
- CHOP: Buy near support (blue/yellow bounce), sell near resistance (purple/orange bounce).
  Exit at midpoint/fixed TP. Minimal reversals. 1-bar rejection confirmation.
- TREND: Override to continuation logic (profit-run, spike exit, first-trade hold).

Features preserved from experiment engine:
- First-trade hold (10 bars, bypass only on 2+ failed expansions)
- Confidence suppression during hold
- Reversal cooldown (2 bars in CHOP)
- Profit-run past session end for TREND trades
- Session discipline (10:30 hard stop for CHOP)
- Full per-trade and per-day logging
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional, List, Dict


@dataclass
class PinballConfig:
    """All tunable parameters — Pinball v5."""
    # Session
    warmup_bars: int = 12
    session_end_time: str = "16:00"        # V4: extended to full day
    earliest_entry_time: str = "09:50"     # V4: no entries before 09:50
    one_and_done: bool = False
    first_entry_trend_filter: bool = True
    # CHOP parameters
    chop_tp_pts: float = 30.0
    chop_stop_pts: float = 60.0            # standard hard stop (after bar 5)
    chop_stop_early_pts: float = 40.0      # V4: tighter stop for first 5 bars
    chop_stop_early_bars: int = 5          # V4: bars during which early stop applies
    chop_stop_breach_pts: float = 10.0
    chop_proximity_pts: float = 15.0
    chop_cooldown_bars: int = 2
    chop_max_trades: int = 12
    chop_rejection_bars: int = 1
    chop_disable_reversal: bool = True
    # Observation trailing stop (Rule B) — V5
    obs_trail_activation_pts: float = 20.0   # activate if +20 within first 3 bars
    obs_trail_activation_bars: int = 3       # window to reach activation threshold
    obs_trail_giveback_pts: float = 15.0     # exit if gives back 15 from peak
    # TREND parameters
    partial_tp_pts: float = 50.0
    spike_profit_pts_trend: float = 200.0
    spike_profit_bars: int = 9
    profit_run_threshold: float = 50.0
    first_trade_min_hold: int = 10
    # Reversal control
    reverse_min_confidence: float = -2.0
    reverse_min_evidence: int = 2
    # Trend detection
    trend_bar_threshold: int = 10
    trend_slope_threshold: float = 0.1
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


class PinballEngine:
    """CHOP-first pinball engine with TREND fallback."""

    def __init__(self, config: Optional[PinballConfig] = None):
        self.cfg = config or PinballConfig()
        # Position
        self.position = 0  # +1 long, -1 short, 0 flat
        self.contracts = 0
        self.entry_price = 0.0
        self.entry_bar_idx = 0
        self.entry_time = None
        self.partial_taken = False
        self.first_trade_done = False
        self.session_done = False
        self.trade_count = 0
        # Mode
        self.mode = "CHOP"
        self.trend_override = False
        # Belief / resolve
        self.confidence = 0.0
        self.resolve_state = "NO_RESOLVE"
        self.failed_expansions = 0
        self.last_extreme_bar = 0
        # Cooldown
        self.last_trade_bar = -99
        self.last_reversal_time = None
        # Observation trailing stop (V5)
        self.obs_trail_active = False
        self.obs_trail_peak = 0.0
        # Lines (current bar)
        self.purple_val = np.nan
        self.blue_val = np.nan
        self.orange_val = np.nan
        self.yellow_val = np.nan
        # Previous bar lines
        self.prev_purple = np.nan
        self.prev_blue = np.nan
        self.prev_orange = np.nan
        self.prev_yellow = np.nan
        # History
        self.recent_highs: List[float] = []
        self.recent_lows: List[float] = []
        self.recent_closes: List[float] = []
        # Range
        self.session_high = -1e30
        self.session_low = 1e30
        # P/L
        self.session_pl = 0.0
        # Logs
        self.bar_logs: List[Dict] = []
        self.blocked_signals: List[Dict] = []
        self.trades: List[Dict] = []

    # ------------------------------------------------------------------
    # Day type detection
    # ------------------------------------------------------------------
    def _detect_mode(self, bar_idx: int) -> str:
        if len(self.recent_highs) < self.cfg.trend_bar_threshold:
            return "CHOP"
        window = self.recent_highs[-self.cfg.trend_bar_threshold:]
        window_lows = self.recent_lows[-self.cfg.trend_bar_threshold:]
        mids = [(h + l) / 2 for h, l in zip(window, window_lows)]
        n = len(mids)
        x_mean = (n - 1) / 2.0
        y_mean = sum(mids) / n
        num = sum((i - x_mean) * (mids[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n))
        slope = num / den if den != 0 else 0.0
        bars_since = bar_idx - self.last_extreme_bar
        if bars_since <= self.cfg.trend_bar_threshold and abs(slope) >= self.cfg.trend_slope_threshold:
            return "TREND"
        return "CHOP"

    # ------------------------------------------------------------------
    # Rejection confirmation: price touched line but closed away from it
    # ------------------------------------------------------------------
    def _has_rejection(self, direction: str, line_val: float, close: float, low: float, high: float) -> bool:
        """Check if price rejected off a line (1-bar confirmation)."""
        if np.isnan(line_val):
            return False
        if direction == "BUY":
            # Low touched/pierced support but close held above
            return low <= line_val + self.cfg.chop_proximity_pts and close > line_val
        else:
            # High touched/pierced resistance but close held below
            return high >= line_val - self.cfg.chop_proximity_pts and close < line_val

    # ------------------------------------------------------------------
    # Main bar processing
    # ------------------------------------------------------------------
    def process_bar(self, bar_idx: int, bar: dict, lines: dict, mech_signal: str = ""):
        close = bar["Close"]; high = bar["High"]; low = bar["Low"]
        bar_time = bar["time"]
        prev_close = bar.get("prev_close", close)

        # Update lines
        self.purple_val = lines.get("purple", np.nan)
        self.blue_val = lines.get("blue", np.nan)
        self.orange_val = lines.get("orange", np.nan)
        self.yellow_val = lines.get("yellow", np.nan)
        self.prev_purple = lines.get("prev_purple", np.nan)
        self.prev_blue = lines.get("prev_blue", np.nan)
        self.prev_orange = lines.get("prev_orange", np.nan)
        self.prev_yellow = lines.get("prev_yellow", np.nan)

        # Track session range
        if high > self.session_high: self.session_high = high
        if low < self.session_low: self.session_low = low

        # History
        self.recent_highs.append(high)
        self.recent_lows.append(low)
        self.recent_closes.append(close)
        if len(self.recent_highs) > 30: self.recent_highs.pop(0)
        if len(self.recent_lows) > 30: self.recent_lows.pop(0)
        if len(self.recent_closes) > 30: self.recent_closes.pop(0)

        # Update extremes
        if len(self.recent_highs) >= 3:
            if high >= max(self.recent_highs[-3:]):
                self.last_extreme_bar = bar_idx
        if len(self.recent_lows) >= 3:
            if low <= min(self.recent_lows[-3:]):
                self.last_extreme_bar = bar_idx

        # Detect mode
        self.mode = self._detect_mode(bar_idx)
        self.trend_override = (self.mode == "TREND")

        # --- Session end ---
        session_end_reached = False
        if hasattr(bar_time, 'strftime'):
            session_end_reached = bar_time.strftime("%H:%M") >= self.cfg.session_end_time

        # V4: Only force exit at end-of-day (16:00), not at 10:30
        if session_end_reached and self.position != 0:
            self._do_exit("SESSION_EXIT", bar_idx, bar)
            self.session_done = True
            self._log(bar_idx, bar, "SESSION_EXIT")
            return

        if session_end_reached and self.position == 0:
            self.session_done = True
        if self.session_done and self.position == 0:
            self._log(bar_idx, bar, "SESSION_DONE")
            return

        # Warmup
        if bar_idx < self.cfg.warmup_bars:
            self._log(bar_idx, bar, "WAIT")
            return

        # V4: No new entries before earliest_entry_time
        entry_allowed = True
        if hasattr(bar_time, 'strftime') and self.position == 0:
            if bar_time.strftime("%H:%M") < self.cfg.earliest_entry_time:
                entry_allowed = False

        # --- Compute protection state ---
        _unreal = 0.0
        if self.position != 0 and self.entry_price != 0.0:
            _unreal = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)

        # --- V4: Fast early stop (first 5 bars = -40, after = -60) ---
        if self.position != 0:
            bars_in_trade = bar_idx - self.entry_bar_idx
            if bars_in_trade <= self.cfg.chop_stop_early_bars:
                stop_threshold = -self.cfg.chop_stop_early_pts
            else:
                stop_threshold = -self.cfg.chop_stop_pts
            if _unreal <= stop_threshold:
                exit_type = "EARLY_HARD_STOP" if bars_in_trade <= self.cfg.chop_stop_early_bars else "EXIT_FLAT"
                self._execute(exit_type, bar_idx, bar)
                self._log(bar_idx, bar, exit_type)
                return

        # --- V5.1: Observation Trailing Stop (subordinate to protected components) ---
        if self.position != 0 and self.entry_price != 0.0:
            bars_in_trade = bar_idx - self.entry_bar_idx
            # Always track peak unrealized
            if _unreal > self.obs_trail_peak:
                self.obs_trail_peak = _unreal

            # Arm condition: trade reached +20 within first 3 bars
            obs_trail_armed = (self.obs_trail_peak >= self.cfg.obs_trail_activation_pts and
                               bars_in_trade >= 1)

            # Activation gate: ONLY activate if protected components have ALREADY FIRED
            # Trail is SUBORDINATE — only protects profit AFTER TP has been taken
            protected_resolved = self.partial_taken  # ONLY after partial/CHOP TP has fired

            if obs_trail_armed and not self.obs_trail_active:
                if protected_resolved:
                    self.obs_trail_active = True
                    self._log_trade_note(bar, "OBS_TRAIL_ARMED", _unreal)
                else:
                    # Log that trail would activate but is blocked
                    if not hasattr(self, '_trail_blocked_logged'):
                        self._trail_blocked_logged = True
                        self._log_trade_note(bar, "OBS_TRAIL_BLOCKED", _unreal)

            # Exit: if trailing stop active and giveback exceeds threshold
            if self.obs_trail_active and self.obs_trail_peak > 0:
                giveback = self.obs_trail_peak - _unreal
                if giveback >= self.cfg.obs_trail_giveback_pts:
                    self._execute("OBS_TRAIL_EXIT", bar_idx, bar)
                    self._log(bar_idx, bar, "OBS_TRAIL_EXIT")
                    return

        first_trade_protected = False
        if self.position != 0 and self.cfg.first_trade_min_hold > 0:
            bars_held = bar_idx - self.entry_bar_idx
            is_first = (self.last_reversal_time is None or self.last_reversal_time == self.entry_time)
            if is_first and bars_held < self.cfg.first_trade_min_hold:
                if self.failed_expansions < 2:
                    first_trade_protected = True

        # --- Route to mode logic ---
        if self.trend_override:
            action = self._decide_trend(bar_idx, bar, close, prev_close, high, low,
                                         bar_time, first_trade_protected, _unreal, session_end_reached, entry_allowed)
        else:
            action = self._decide_chop(bar_idx, bar, close, low, high, bar_time,
                                        first_trade_protected, _unreal, entry_allowed)

        # Execute
        if action not in ("HOLD", "WAIT"):
            self._execute(action, bar_idx, bar)
        self._log(bar_idx, bar, action)

    # ------------------------------------------------------------------
    # CHOP decision: pinball between support/resistance
    # ------------------------------------------------------------------
    def _decide_chop(self, bar_idx, bar, close, low, high, bar_time,
                     first_trade_protected, _unreal, entry_allowed):
        # --- Exit existing position ---
        if self.position != 0 and self.entry_price != 0.0:
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            # Fixed TP
            if unrealized >= self.cfg.chop_tp_pts:
                return "CHOP_TP"
            # Fixed stop — only if loss exceeds threshold AND not in profit-run
            if unrealized <= -self.cfg.chop_stop_pts and unrealized < -self.cfg.profit_run_threshold:
                return "CHOP_STOP"
            # Midpoint exit
            if self.session_high > self.session_low:
                midpoint = (self.session_high + self.session_low) / 2
                if self.position == 1 and close >= midpoint and unrealized > 10:
                    return "CHOP_TP"
                if self.position == -1 and close <= midpoint and unrealized > 10:
                    return "CHOP_TP"
            # Line breach against position — require breach by >X pts
            if self.position == 1 and not np.isnan(self.blue_val):
                breach = self.blue_val - close  # positive = price below blue
                if breach > self.cfg.chop_stop_breach_pts:
                    if first_trade_protected:
                        self._block("CHOP_STOP", bar_time, "FIRST_TRADE_HOLD", "blue_breach", _unreal)
                        return "HOLD"
                    return "CHOP_STOP"
            if self.position == -1 and not np.isnan(self.purple_val):
                breach = close - self.purple_val  # positive = price above purple
                if breach > self.cfg.chop_stop_breach_pts:
                    if first_trade_protected:
                        self._block("CHOP_STOP", bar_time, "FIRST_TRADE_HOLD", "purple_breach", _unreal)
                        return "HOLD"
                    # On CHOP days: exit to flat, do NOT reverse
                    if self.cfg.chop_disable_reversal:
                        return "CHOP_STOP"
                    return "CHOP_STOP"

        # --- Cooldown ---
        if bar_idx - self.last_trade_bar < self.cfg.chop_cooldown_bars:
            return "HOLD"

        # --- Max trades ---
        if self.trade_count >= self.cfg.chop_max_trades:
            return "HOLD"

        # --- Entry: buy near support with rejection ---
        if self.position == 0 and entry_allowed:
            # Buy near blue (support)
            if self._has_rejection("BUY", self.blue_val, close, low, high):
                if self._trend_filter_allows("BUY"):
                    return "BUY"
                else:
                    self._block("BUY", bar_time, "TREND_FILTER", "blue_rejection", 0.0)
            # Buy near yellow (deeper support)
            if self._has_rejection("BUY", self.yellow_val, close, low, high):
                if self._trend_filter_allows("BUY"):
                    return "BUY"
                else:
                    self._block("BUY", bar_time, "TREND_FILTER", "yellow_rejection", 0.0)
            # Sell near purple (resistance)
            if self._has_rejection("SELL", self.purple_val, close, low, high):
                if self._trend_filter_allows("SELL"):
                    return "SELL"
                else:
                    self._block("SELL", bar_time, "TREND_FILTER", "purple_rejection", 0.0)
            # Sell near orange (deeper resistance)
            if self._has_rejection("SELL", self.orange_val, close, low, high):
                if self._trend_filter_allows("SELL"):
                    return "SELL"
                else:
                    self._block("SELL", bar_time, "TREND_FILTER", "orange_rejection", 0.0)

        return "HOLD"

    # ------------------------------------------------------------------
    # TREND decision: continuation with first-trade hold
    # ------------------------------------------------------------------
    def _decide_trend(self, bar_idx, bar, close, prev_close, high, low,
                      bar_time, first_trade_protected, _unreal, session_end_reached, entry_allowed):
        # Partial TP
        if self.position != 0 and not self.partial_taken and self.entry_price != 0.0:
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            if unrealized >= self.cfg.partial_tp_pts:
                return "PARTIAL_TP"

        # Spike exit (suppressed during profit-run)
        if self.position != 0 and self.entry_price != 0.0:
            bars_held = bar_idx - self.entry_bar_idx
            if 0 < bars_held <= self.cfg.spike_profit_bars:
                unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
                if unrealized >= self.cfg.spike_profit_pts_trend:
                    if session_end_reached and unrealized > self.cfg.profit_run_threshold:
                        pass  # suppress during profit-run
                    else:
                        return "SPIKE_EXIT"

        # Line cross detection — count opposing evidences
        buy_crosses = 0; sell_crosses = 0
        if not np.isnan(self.prev_purple) and self.recent_closes[-2] <= self.prev_purple and close > self.purple_val:
            buy_crosses += 1
        if not np.isnan(self.prev_orange) and self.recent_closes[-2] <= self.prev_orange and close > self.orange_val:
            buy_crosses += 1
        if not np.isnan(self.prev_blue) and self.recent_closes[-2] >= self.prev_blue and close < self.blue_val:
            sell_crosses += 1
        if not np.isnan(self.prev_yellow) and self.recent_closes[-2] >= self.prev_yellow and close < self.yellow_val:
            sell_crosses += 1

        buy_cross = buy_crosses > 0
        sell_cross = sell_crosses > 0

        # Flat: enter
        if self.position == 0 and entry_allowed:
            if buy_cross and self._trend_filter_allows("BUY"):
                return "BUY"
            if sell_cross and self._trend_filter_allows("SELL"):
                return "SELL"
            return "HOLD"

        # In position: opposing signal — EXIT TO FLAT (no reversal)
        # Reversals were the #1 loss source (-24k over 84 trades at -286 avg).
        # Strategy: close position and wait for next clean entry instead of flipping.
        opposing = (buy_cross and self.position == -1) or (sell_cross and self.position == 1)
        if opposing:
            if first_trade_protected:
                self._block("EXIT_FLAT", bar_time, "FIRST_TRADE_HOLD", "trend_cross", _unreal)
                return "HOLD"
            # Emergency exit if losing significantly
            if _unreal <= -self.cfg.chop_stop_pts:
                return "EXIT_FLAT"
            # Exit to flat if: enough evidence OR confidence deeply negative OR failed expansions
            opposing_count = buy_crosses if self.position == -1 else sell_crosses
            if opposing_count >= self.cfg.reverse_min_evidence:
                return "EXIT_FLAT"
            elif self.confidence <= self.cfg.reverse_min_confidence:
                return "EXIT_FLAT"
            elif self.failed_expansions >= 2:
                return "EXIT_FLAT"
            else:
                # Weak evidence but losing: exit if loss > 30 pts
                if _unreal <= -30.0:
                    return "EXIT_FLAT"
                self._block("EXIT_FLAT", bar_time, "WEAK_EVIDENCE",
                           f"crosses={opposing_count}<{self.cfg.reverse_min_evidence}", _unreal)
                return "HOLD"

        return "HOLD"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
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

    def _block(self, action, bar_time, reason, evidence, unrealized_pl):
        self.blocked_signals.append({
            "time": bar_time, "action": action, "reason": reason,
            "evidence": evidence, "unrealized_pl": unrealized_pl, "day_type": self.mode
        })

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def _execute(self, action, bar_idx, bar):
        close = bar["Close"]; bar_time = bar["time"]

        if action == "BUY":
            if self.position == -1:
                c = 1 if self.partial_taken else 2
                self.session_pl += (self.entry_price - close) * c
            self.position = 1; self.contracts = 2; self.entry_price = close
            self.entry_bar_idx = bar_idx; self.entry_time = bar_time
            self.partial_taken = False; self.first_trade_done = True
            self.last_trade_bar = bar_idx; self.trade_count += 1
            self.failed_expansions = 0; self.confidence = 1.5
            self.obs_trail_active = False; self.obs_trail_peak = 0.0
            self._trail_blocked_logged = False
            self._log_trade(bar_time, "CHOP_BUY" if self.mode == "CHOP" else "TREND_LONG",
                           close, "long", 2, 0.0, 0)

        elif action == "SELL":
            if self.position == 1:
                c = 1 if self.partial_taken else 2
                self.session_pl += (close - self.entry_price) * c
            self.position = -1; self.contracts = 2; self.entry_price = close
            self.entry_bar_idx = bar_idx; self.entry_time = bar_time
            self.partial_taken = False; self.first_trade_done = True
            self.last_trade_bar = bar_idx; self.trade_count += 1
            self.failed_expansions = 0; self.confidence = 1.5
            self.obs_trail_active = False; self.obs_trail_peak = 0.0
            self._trail_blocked_logged = False
            self._log_trade(bar_time, "CHOP_SELL" if self.mode == "CHOP" else "TREND_SHORT",
                           close, "short", 2, 0.0, 0)

        elif action == "REVERSE":
            pl = 0.0
            if self.position == 1:
                c = 1 if self.partial_taken else 2
                pl = (close - self.entry_price) * c
                self.session_pl += pl
                self.position = -1
            elif self.position == -1:
                c = 1 if self.partial_taken else 2
                pl = (self.entry_price - close) * c
                self.session_pl += pl
                self.position = 1
            bars_held = bar_idx - self.entry_bar_idx
            self.contracts = 2; self.entry_price = close
            self.entry_bar_idx = bar_idx; self.entry_time = bar_time
            self.partial_taken = False; self.failed_expansions = 0
            self.confidence = 1.5; self.last_reversal_time = bar_time
            self.last_trade_bar = bar_idx; self.trade_count += 1
            self._log_trade(bar_time, "REVERSE", close,
                           "long" if self.position == 1 else "short", 2, pl, bars_held)

        elif action == "EXIT_FLAT":
            pl = 0.0
            if self.position == 1:
                c = 1 if self.partial_taken else 2
                pl = (close - self.entry_price) * c
                self.session_pl += pl
            elif self.position == -1:
                c = 1 if self.partial_taken else 2
                pl = (self.entry_price - close) * c
                self.session_pl += pl
            bars_held = bar_idx - self.entry_bar_idx
            direction = "long" if self.position == 1 else "short"
            self.position = 0; self.contracts = 0; self.entry_price = 0.0
            self.partial_taken = False; self.last_trade_bar = bar_idx
            self.obs_trail_active = False; self.obs_trail_peak = 0.0
            self._log_trade(bar_time, "EXIT_FLAT", close, direction, 0, pl, bars_held)

        elif action == "EARLY_HARD_STOP":
            pl = 0.0
            if self.position == 1:
                c = 1 if self.partial_taken else 2
                pl = (close - self.entry_price) * c
                self.session_pl += pl
            elif self.position == -1:
                c = 1 if self.partial_taken else 2
                pl = (self.entry_price - close) * c
                self.session_pl += pl
            bars_held = bar_idx - self.entry_bar_idx
            direction = "long" if self.position == 1 else "short"
            self.position = 0; self.contracts = 0; self.entry_price = 0.0
            self.partial_taken = False; self.last_trade_bar = bar_idx
            self.obs_trail_active = False; self.obs_trail_peak = 0.0
            self._log_trade(bar_time, "EARLY_HARD_STOP", close, direction, 0, pl, bars_held)

        elif action == "OBS_TRAIL_EXIT":
            pl = 0.0
            if self.position == 1:
                c = 1 if self.partial_taken else 2
                pl = (close - self.entry_price) * c
                self.session_pl += pl
            elif self.position == -1:
                c = 1 if self.partial_taken else 2
                pl = (self.entry_price - close) * c
                self.session_pl += pl
            bars_held = bar_idx - self.entry_bar_idx
            direction = "long" if self.position == 1 else "short"
            self.position = 0; self.contracts = 0; self.entry_price = 0.0
            self.partial_taken = False; self.last_trade_bar = bar_idx
            self.obs_trail_active = False; self.obs_trail_peak = 0.0
            self._log_trade(bar_time, "OBS_TRAIL_EXIT", close, direction, 0, pl, bars_held)

        elif action == "PARTIAL_TP":
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            self.session_pl += unrealized
            self.partial_taken = True; self.contracts = 1
            self._log_trade(bar_time, "PARTIAL_TP", close,
                           "long" if self.position == 1 else "short", 1, unrealized,
                           bar_idx - self.entry_bar_idx)

        elif action in ("CHOP_TP", "CHOP_STOP"):
            pl = 0.0
            if self.position == 1:
                c = 1 if self.partial_taken else 2
                pl = (close - self.entry_price) * c
                self.session_pl += pl
            elif self.position == -1:
                c = 1 if self.partial_taken else 2
                pl = (self.entry_price - close) * c
                self.session_pl += pl
            bars_held = bar_idx - self.entry_bar_idx
            direction = "long" if self.position == 1 else "short"
            self.position = 0; self.contracts = 0; self.entry_price = 0.0
            self.partial_taken = False; self.last_trade_bar = bar_idx
            self._log_trade(bar_time, action, close, direction, 0, pl, bars_held)

        elif action == "SPIKE_EXIT":
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            c = 1 if self.partial_taken else 2
            pl = unrealized * c
            self.session_pl += pl
            bars_held = bar_idx - self.entry_bar_idx
            direction = "long" if self.position == 1 else "short"
            self.position = 0; self.contracts = 0; self.entry_price = 0.0
            self.partial_taken = False
            self._log_trade(bar_time, "SPIKE_EXIT", close, direction, 0, pl, bars_held)

        elif action == "SESSION_EXIT":
            self._do_exit("SESSION_EXIT", bar_idx, bar)

    def _do_exit(self, reason, bar_idx, bar):
        close = bar["Close"]; bar_time = bar["time"]
        pl = 0.0
        if self.position == 1:
            c = 1 if self.partial_taken else 2
            pl = (close - self.entry_price) * c
            self.session_pl += pl
        elif self.position == -1:
            c = 1 if self.partial_taken else 2
            pl = (self.entry_price - close) * c
            self.session_pl += pl
        bars_held = bar_idx - self.entry_bar_idx
        direction = "long" if self.position == 1 else "short"
        self.position = 0; self.contracts = 0; self.entry_price = 0.0
        self.partial_taken = False; self.session_done = True
        self._log_trade(bar_time, reason, close, direction, 0, pl, bars_held)

    # ------------------------------------------------------------------
    # Trade logging (per-trade CSV row)
    # ------------------------------------------------------------------
    def _log_trade(self, bar_time, trade_type, price, direction, contracts, realized_pl, bars_held,
                   line_hit="", blocked=False):
        self.trades.append({
            "date": bar_time.strftime("%Y-%m-%d") if hasattr(bar_time, 'strftime') else "",
            "time": bar_time.strftime("%H:%M:%S") if hasattr(bar_time, 'strftime') else str(bar_time),
            "trade_type": trade_type,
            "entry_price": self.entry_price if trade_type in ("CHOP_BUY","CHOP_SELL","TREND_LONG","TREND_SHORT") else price,
            "exit_price": price,
            "direction": direction,
            "contracts": contracts,
            "realized_pl": realized_pl,
            "bars_held": bars_held,
            "line_hit": line_hit,
            "blocked": blocked,
            "day_type": self.mode,
        })

    def _log_trade_note(self, bar, note, unrealized):
        """Log a non-trade event (e.g., trailing stop activation)."""
        bar_time = bar["time"]
        self.trades.append({
            "date": bar_time.strftime("%Y-%m-%d") if hasattr(bar_time, 'strftime') else "",
            "time": bar_time.strftime("%H:%M:%S") if hasattr(bar_time, 'strftime') else str(bar_time),
            "trade_type": note,
            "entry_price": self.entry_price,
            "exit_price": bar["Close"],
            "direction": "long" if self.position == 1 else "short",
            "contracts": self.contracts,
            "realized_pl": 0.0,
            "bars_held": 0,
            "line_hit": f"peak={self.obs_trail_peak:.0f}",
            "blocked": False,
            "day_type": self.mode,
        })

    # ------------------------------------------------------------------
    # Bar logging
    # ------------------------------------------------------------------
    def _log(self, bar_idx, bar, action):
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
            "entry_price": self.entry_price, "mode": self.mode,
            "trade_count": self.trade_count, "action": action,
            "session_pl": display_pl, "partial_taken": self.partial_taken,
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
            self.process_bar(i, bar, lines, "")
        return pd.DataFrame(self.bar_logs)
