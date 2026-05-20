"""
conviction_engine.py — Phase 3: Conviction Layer for FRED Is Alive

Translates belief score into conviction STATES.
Scott trades states, not numbers.

Key design:
- Hysteresis: crossing a threshold does NOT instantly change state
- Persistence required: must hold beyond threshold for N bars
- States are what Scott experiences, not raw scores
- Avoids "smart chop" from oscillating near boundaries

No trades. No execution. State labeling only.
"""

from dataclasses import dataclass
from typing import List, Tuple


# Conviction states (ordered from bullish to bearish)
STATES = [
    "STRONG_BULLISH_RESOLVE",
    "BULLISH_CONVICTION",
    "LEANING_BULLISH",
    "OBSERVING",
    "LEANING_BEARISH",
    "BEARISH_CONVICTION",
    "STRONG_BEARISH_RESOLVE",
    "THESIS_CHALLENGED",
    "TRANSITION",
]


@dataclass
class ConvictionState:
    """Current conviction state with metadata."""
    state: str
    bars_in_state: int
    belief_score: float
    previous_state: str
    transition_bar: int  # bar when current state began


class ConvictionEngine:
    """Phase 3: Converts belief score into conviction states with hysteresis.
    
    Thresholds (entry):
        Strong resolve: |score| >= 8
        Conviction: |score| >= 5
        Leaning: |score| >= 2
        Observing: |score| < 2
    
    Hysteresis (exit — must drop FURTHER to leave state):
        Strong resolve → conviction: requires |score| < 6 (not 8)
        Conviction → leaning: requires |score| < 3 (not 5)
        Leaning → observing: requires |score| < 1 (not 2)
    
    Persistence: state change requires 3+ bars beyond threshold.
    """

    def __init__(self, persistence_bars: int = 3):
        self.persistence_bars = persistence_bars
        self.current_state = "OBSERVING"
        self.bars_in_state = 0
        self.previous_state = "OBSERVING"
        self.transition_bar = 0

        # Pending state change (requires persistence)
        self._pending_state: str = ""
        self._pending_bars: int = 0

        # History
        self.state_history: List[Tuple[int, str, float]] = []  # (bar, state, score)

    def _determine_raw_state(self, score: float) -> str:
        """Determine what state the score WOULD map to (without hysteresis).
        
        States include transitional/warning states:
        - WARNING states: "still convicted but watching carefully"
        - TRANSITION: actively shifting between directions
        - THESIS_CHALLENGED: strong conviction being undermined
        """
        if score >= 8:
            return "STRONG_BULLISH_RESOLVE"
        elif score >= 5:
            return "BULLISH_CONVICTION"
        elif score >= 2:
            return "LEANING_BULLISH"
        elif score <= -8:
            return "STRONG_BEARISH_RESOLVE"
        elif score <= -5:
            return "BEARISH_CONVICTION"
        elif score <= -2:
            return "LEANING_BEARISH"
        else:
            return "OBSERVING"

    def _determine_transitional_state(self, score: float) -> str:
        """Determine if a WARNING or TRANSITION state applies.
        
        Warning states occur when:
        - Was strongly convicted, now score is weakening toward threshold
        - Still on the same side but conviction is eroding
        
        Transition occurs when:
        - Score crosses zero from one side to the other
        """
        if not self.state_history:
            return ""

        # Check if we're in a warning zone (conviction eroding but same side)
        was_strong_bearish = self.current_state in ("STRONG_BEARISH_RESOLVE", "BEARISH_CONVICTION")
        was_strong_bullish = self.current_state in ("STRONG_BULLISH_RESOLVE", "BULLISH_CONVICTION")

        if was_strong_bearish and -5 < score <= -2:
            return "BEARISH_WARNING"
        if was_strong_bullish and 2 <= score < 5:
            return "BULLISH_WARNING"

        # Check for transition (crossing zero from convicted state)
        if was_strong_bearish and score > 0:
            return "TRANSITION"
        if was_strong_bullish and score < 0:
            return "TRANSITION"

        return ""

    def _should_exit_current(self, score: float) -> bool:
        """Check if score has moved far enough to EXIT current state (hysteresis)."""
        s = self.current_state

        if s == "STRONG_BULLISH_RESOLVE":
            return score < 6  # must drop below 6 to leave (entered at 8)
        elif s == "BULLISH_CONVICTION":
            return score < 3 or score >= 8  # drop below 3 OR upgrade to strong
        elif s == "BULLISH_WARNING":
            return score >= 5 or score < 1  # recover to conviction OR drop further
        elif s == "LEANING_BULLISH":
            return score < 1 or score >= 5  # drop below 1 OR upgrade
        elif s == "OBSERVING":
            return abs(score) >= 2  # any direction exceeds threshold
        elif s == "LEANING_BEARISH":
            return score > -1 or score <= -5
        elif s == "BEARISH_WARNING":
            return score <= -5 or score > -1  # recover to conviction OR drop further
        elif s == "BEARISH_CONVICTION":
            return score > -3 or score <= -8
        elif s == "STRONG_BEARISH_RESOLVE":
            return score > -6
        elif s == "THESIS_CHALLENGED":
            return abs(score) >= 3 or abs(score) < 0.5  # resolves to direction or neutral
        elif s == "TRANSITION":
            return abs(score) >= 2 or abs(score) < 0.5

        return False

    def _detect_thesis_challenge(self, score: float) -> bool:
        """Detect if belief is being challenged (rapid reversal toward zero)."""
        if len(self.state_history) < 5:
            return False

        # Was strongly convicted, now rapidly approaching zero
        recent_scores = [s[2] for s in self.state_history[-5:]]
        was_strong = any(abs(s) >= 6 for s in recent_scores[:3])
        now_weak = abs(score) < 3

        if was_strong and now_weak:
            return True
        return False

    def process_bar(self, bar_idx: int, belief_score: float):
        """Update conviction state based on current belief score."""
        self.bars_in_state += 1

        # Check for thesis challenge (special state)
        if self._detect_thesis_challenge(belief_score):
            if self.current_state not in ("THESIS_CHALLENGED", "TRANSITION", "OBSERVING",
                                          "BEARISH_WARNING", "BULLISH_WARNING"):
                self._pending_state = "THESIS_CHALLENGED"
                self._pending_bars = self.persistence_bars  # instant for challenges

        # Check if we should exit current state
        should_exit = self._should_exit_current(belief_score)

        if should_exit:
            # First check for transitional/warning states
            transitional = self._determine_transitional_state(belief_score)
            if transitional:
                target = transitional
            else:
                target = self._determine_raw_state(belief_score)

            # Is this the same pending state we've been tracking?
            if target == self._pending_state:
                self._pending_bars += 1
            else:
                # New target — reset persistence counter
                self._pending_state = target
                self._pending_bars = 1

            # Persistence requirement (warning/transition states need less persistence)
            required_persistence = self.persistence_bars
            if target in ("BEARISH_WARNING", "BULLISH_WARNING", "THESIS_CHALLENGED"):
                required_persistence = 2  # warnings activate faster
            elif target == "TRANSITION":
                required_persistence = 2

            # Check persistence requirement
            if self._pending_bars >= required_persistence:
                # State change confirmed
                self.previous_state = self.current_state
                self.current_state = self._pending_state
                self.bars_in_state = 0
                self.transition_bar = bar_idx
                self._pending_state = ""
                self._pending_bars = 0
        else:
            # Staying in current state — reset pending
            self._pending_state = ""
            self._pending_bars = 0

        # Record history
        self.state_history.append((bar_idx, self.current_state, belief_score))

    def get_state(self) -> ConvictionState:
        """Return current conviction state."""
        score = self.state_history[-1][2] if self.state_history else 0.0
        return ConvictionState(
            state=self.current_state,
            bars_in_state=self.bars_in_state,
            belief_score=score,
            previous_state=self.previous_state,
            transition_bar=self.transition_bar,
        )

    def print_evolution(self, max_entries: int = 30):
        """Print state transitions (not every bar — only changes)."""
        print(f"\nCONVICTION STATE EVOLUTION:")
        print(f"{'Bar':<5} {'State':<25} {'Score':>7} {'Bars':>5}")
        print(f"{'-'*50}")

        prev_state = ""
        for bar, state, score in self.state_history:
            if state != prev_state:
                print(f"{bar:<5} {state:<25} {score:>+7.1f}")
                prev_state = state

        print(f"\nFinal: {self.current_state} (held {self.bars_in_state} bars)")
