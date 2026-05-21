"""
execution_engine.py — Phase 4: Execution from conviction states

Entry: BEARISH_CONVICTION or STRONG_BEARISH_RESOLVE (SHORT)
       BULLISH_CONVICTION or STRONG_BULLISH_RESOLVE (LONG)
Exit:  TRANSITION, THESIS_CHALLENGED, or session end

Filters (data-driven, robust across both Pinball and FRED):
- Late session: no new entries after bar 330 (~15:00) unless STRONG conviction
- Quick kill: exit immediately-wrong trades by bar 8 if losing >= 50 pts
"""

import pandas as pd
import pytz
from typing import List, Dict
from evidence_engine import EvidenceEngine
from conviction_engine import ConvictionEngine

# Late session filter: ~330 bars into session = 15:00 (session starts 09:30)
_LATE_SESSION_BAR = 330
# Quick kill: if losing >= 50 pts by bar 8, trade is immediately wrong
_QUICK_KILL_BARS = 8
_QUICK_KILL_THRESHOLD = 50  # pts adverse (on 2 contracts)


class ExecutionEngine:
    """Phase 4: Execution from conviction states with research-backed filters."""

    def __init__(self):
        self.position = 0  # +1 long, -1 short, 0 flat
        self.entry_price = 0.0
        self.entry_bar = -1
        self.trades: List[Dict] = []
        self.session_pl = 0.0
        self._daily_killed = False

    def run_session(self, day_data: pd.DataFrame) -> Dict:
        """Run full pipeline: structure → evidence → conviction → execution."""
        n = len(day_data)
        closes = day_data['Close'].values

        # Run evidence engine
        evidence = EvidenceEngine()
        evidence.run_session(day_data)

        # Run conviction engine
        conviction = ConvictionEngine(persistence_bars=3)
        for bar, score, _ in evidence.belief_history:
            conviction.process_bar(bar, score)

        # Execute based on conviction states
        for bar, state, score in conviction.state_history:
            close = closes[bar]

            # --- ENTRY ---
            if self.position == 0:
                # Daily kill active — no more trading today
                if self._daily_killed:
                    continue

                # Late session filter: no entries after ~15:00 unless STRONG
                if bar >= _LATE_SESSION_BAR:
                    if state not in ("STRONG_BEARISH_RESOLVE", "STRONG_BULLISH_RESOLVE"):
                        continue

                if state in ("BEARISH_CONVICTION", "STRONG_BEARISH_RESOLVE"):
                    self.position = -1
                    self.entry_price = close
                    self.entry_bar = bar
                elif state in ("BULLISH_CONVICTION", "STRONG_BULLISH_RESOLVE"):
                    self.position = +1
                    self.entry_price = close
                    self.entry_bar = bar

            # --- EXIT ---
            elif self.position != 0:
                unrealized = (close - self.entry_price) * self.position * 2
                bars_held = bar - self.entry_bar

                should_exit = False
                exit_reason = ""

                # === CAPITAL PRESERVATION LAYER (independent of conviction) ===
                # Parameters tuned via sensitivity sweep (plateau-based, not peak-fitted)

                # Trade kill: maximum adverse excursion (250 pts = 125/contract)
                if unrealized <= -250:
                    should_exit = True
                    exit_reason = "TRADE_KILL"

                # Daily kill: hard daily stop — STOP TRADING for the day (300 pts)
                elif self.session_pl + unrealized <= -300:
                    should_exit = True
                    exit_reason = "DAILY_KILL"
                    self._daily_killed = True

                # Quick kill: immediately-wrong trades (losing >= 50 by bar 8)
                elif (bars_held == _QUICK_KILL_BARS
                      and unrealized <= -_QUICK_KILL_THRESHOLD):
                    should_exit = True
                    exit_reason = "QUICK_KILL"

                # Thesis timeout: no progress after 50 bars → exit
                elif bars_held >= 50 and unrealized <= 0:
                    should_exit = True
                    exit_reason = "THESIS_TIMEOUT"

                # === CONVICTION-BASED EXITS ===

                elif state in ("TRANSITION", "THESIS_CHALLENGED"):
                    should_exit = True
                    exit_reason = state
                elif state == "OBSERVING" and self.position != 0:
                    should_exit = True
                    exit_reason = "CONVICTION_LOST"
                # Opposite conviction = exit
                elif self.position == -1 and state in ("BULLISH_CONVICTION", "STRONG_BULLISH_RESOLVE"):
                    should_exit = True
                    exit_reason = "REVERSED"
                elif self.position == 1 and state in ("BEARISH_CONVICTION", "STRONG_BEARISH_RESOLVE"):
                    should_exit = True
                    exit_reason = "REVERSED"

                if should_exit:
                    pl = (close - self.entry_price) * self.position * 2  # 2 contracts
                    self.session_pl += pl
                    self.trades.append({
                        'entry_bar': self.entry_bar,
                        'exit_bar': bar,
                        'direction': 'SHORT' if self.position == -1 else 'LONG',
                        'entry_price': self.entry_price,
                        'exit_price': close,
                        'pl': pl,
                        'bars_held': bar - self.entry_bar,
                        'exit_reason': exit_reason,
                    })
                    self.position = 0
                    self.entry_price = 0.0

        # Session end: close any open position
        if self.position != 0:
            close = closes[-1]
            pl = (close - self.entry_price) * self.position * 2
            self.session_pl += pl
            self.trades.append({
                'entry_bar': self.entry_bar,
                'exit_bar': n - 1,
                'direction': 'SHORT' if self.position == -1 else 'LONG',
                'entry_price': self.entry_price,
                'exit_price': close,
                'pl': pl,
                'bars_held': (n - 1) - self.entry_bar,
                'exit_reason': 'SESSION_END',
            })
            self.position = 0

        return {
            'session_pl': self.session_pl,
            'trades': self.trades,
            'final_state': conviction.current_state,
            'belief_final': evidence.belief_score,
        }
