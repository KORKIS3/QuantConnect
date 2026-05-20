"""
execution_engine.py — Phase 4: Simplest Execution Prototype

Entry: BEARISH_CONVICTION or STRONG_BEARISH_RESOLVE (SHORT)
       BULLISH_CONVICTION or STRONG_BULLISH_RESOLVE (LONG)
Exit:  TRANSITION, THESIS_CHALLENGED, or session end

No additional complexity. Let data tell us what's missing.
"""

import pandas as pd
import pytz
from typing import List, Dict
from evidence_engine import EvidenceEngine
from conviction_engine import ConvictionEngine


class ExecutionEngine:
    """Phase 4: Simplest possible execution from conviction states."""

    def __init__(self):
        self.position = 0  # +1 long, -1 short, 0 flat
        self.entry_price = 0.0
        self.entry_bar = -1
        self.trades: List[Dict] = []
        self.session_pl = 0.0

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
                should_exit = False
                exit_reason = ""

                if state in ("TRANSITION", "THESIS_CHALLENGED"):
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
