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
    """All tunable parameters."""
    # Session
    warmup_bars: int = 12
    session_end_time: str = "10:30"
    one_and_done: bool = False             # Pinball takes multiple CHOP trades
    first_entry_trend_filter: bool = True
    # CHOP parameters
    chop_tp_pts: float = 30.0              # fixed TP for CHOP bounces
    chop_stop_pts: float = 40.0            # stop loss for CHOP trades
    chop_proximity_pts: float = 15.0       # how close to line to trigger entry
    chop_cooldown_bars: int = 2            # bars between CHOP trades
    chop_max_trades: int = 6              # max trades per CHOP session
    chop_rejection_bars: int = 1           # bars of rejection confirmation
    # TREND parameters
    partial_tp_pts: float = 50.0
    spike_profit_pts_trend: float = 200.0
    spike_profit_bars: int = 9
    profit_run_threshold: float = 50.0
    first_trade_min_hold: int = 10
    # Trend detection (relaxed)
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

        if session_end_reached and self.position != 0:
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            if self.trend_override and unrealized > self.cfg.profit_run_threshold:
                pass  # profit-run in TREND
            else:
                self._do_exit("SESSION_EXIT", bar_idx, bar)
                self.session_done = True
                self._log(bar_idx, bar, "SESSION_EXIT")
                return

        if session_end_reached and self.position == 0:
            if self.cfg.one_and_done:
                self.session_done = True
        if self.session_done and self.position == 0:
            self._log(bar_idx, bar, "SESSION_DONE")
            return

        # Warmup
        if bar_idx < self.cfg.warmup_bars:
            self._log(bar_idx, bar, "WAIT")
            return

        # --- Compute protection state ---
        _unreal = 0.0
        if self.position != 0 and self.entry_price != 0.0:
            _unreal = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)

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
                                         bar_time, first_trade_protected, _unreal, session_end_reached)
        else:
            action = self._decide_chop(bar_idx, bar, close, low, high, bar_time,
                                        first_trade_protected, _unreal)

        # Execute
        if action not in ("HOLD", "WAIT"):
            self._execute(action, bar_idx, bar)
        self._log(bar_idx, bar, action)

    # ------------------------------------------------------------------
    # CHOP decision: pinball between support/resistance
    # ------------------------------------------------------------------
    def _decide_chop(self, bar_idx, bar, close, low, high, bar_time,
                     first_trade_protected, _unreal):
        # --- Exit existing position ---
        if self.position != 0 and self.entry_price != 0.0:
            unrealized = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            # Fixed TP
            if unrealized >= self.cfg.chop_tp_pts:
                return "CHOP_TP"
            # Fixed stop
            if unrealized <= -self.cfg.chop_stop_pts:
                return "CHOP_STOP"
            # Midpoint exit
            if self.session_high > self.session_low:
                midpoint = (self.session_high + self.session_low) / 2
                if self.position == 1 and close >= midpoint and unrealized > 10:
                    return "CHOP_TP"
                if self.position == -1 and close <= midpoint and unrealized > 10:
                    return "CHOP_TP"
            # Line cross against position (reversal)
            if self.position == 1 and not np.isnan(self.blue_val) and close < self.blue_val:
                if first_trade_protected:
                    self._block("REVERSE", bar_time, "FIRST_TRADE_HOLD", "blue_cross_below", _unreal)
                    return "HOLD"
                return "CHOP_STOP"
            if self.position == -1 and not np.isnan(self.purple_val) and close > self.purple_val:
                if first_trade_protected:
                    self._block("REVERSE", bar_time, "FIRST_TRADE_HOLD", "purple_cross_above", _unreal)
                    return "HOLD"
                return "CHOP_STOP"

        # --- Cooldown ---
        if bar_idx - self.last_trade_bar < self.cfg.chop_cooldown_bars:
            return "HOLD"

        # --- Max trades ---
        if self.trade_count >= self.cfg.chop_max_trades:
            return "HOLD"

        # --- Entry: buy near support with rejection ---
        if self.position == 0:
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
                      bar_time, first_trade_protected, _unreal, session_end_reached):
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

        # Line cross detection
        buy_cross = False; sell_cross = False
        if not np.isnan(self.prev_purple) and self.recent_closes[-2] <= self.prev_purple and close > self.purple_val:
            buy_cross = True
        if not np.isnan(self.prev_orange) and self.recent_closes[-2] <= self.prev_orange and close > self.orange_val:
            buy_cross = True
        if not np.isnan(self.prev_blue) and self.recent_closes[-2] >= self.prev_blue and close < self.blue_val:
            sell_cross = True
        if not np.isnan(self.prev_yellow) and self.recent_closes[-2] >= self.prev_yellow and close < self.yellow_val:
            sell_cross = True

        # Flat: enter
        if self.position == 0:
            if buy_cross and self._trend_filter_allows("BUY"):
                return "BUY"
            if sell_cross and self._trend_filter_allows("SELL"):
                return "SELL"
            return "HOLD"

        # In position: reversal
        opposing = (buy_cross and self.position == -1) or (sell_cross and self.position == 1)
        if opposing:
            if first_trade_protected:
                self._block("REVERSE", bar_time, "FIRST_TRADE_HOLD", "trend_cross", _unreal)
                return "HOLD"
            return "REVERSE"

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
