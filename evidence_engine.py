"""
evidence_engine.py — Phase 2: Evidence Layer for FRED Is Alive

Observes structure and collects evidence. No trades. No execution.
Teaches Fred how to observe before teaching Fred how to act.

For every active line tracks:
- Touch count, rejection count
- Confirmed breaks, failed breaks, reclaims
- Time since last interaction
- Direction of interaction
- Strength score
- Current question being asked
- Belief impact if interaction succeeds/fails

Produces an Evidence Timeline per session.
"""

import numpy as np
import pandas as pd
import pytz
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from frozen_ray_engine import FrozenRayEngine, FrozenRay


@dataclass
class EvidenceEvent:
    """A single piece of observed evidence."""
    bar: int
    time: str
    event_type: str       # TOUCH, REJECTION, BREAK, FAILED_BREAK, RECLAIM, STRUCTURE_CREATED
    line_id: int
    line_type: str
    direction: str        # BULLISH or BEARISH
    strength: float       # magnitude of evidence (1=weak, 2=moderate, 3=strong)
    question: str         # what question was this line asking?
    belief_impact: float  # how much this changes conviction (+/- pts)
    description: str


@dataclass
class LineEvidence:
    """Evidence state for a single line."""
    line_id: int
    line_type: str
    touches: int = 0
    rejections: int = 0
    confirmed_breaks: int = 0
    failed_breaks: int = 0
    reclaims: int = 0
    last_interaction_bar: int = -1
    last_interaction_type: str = ""
    strength_score: float = 0.0
    current_question: str = ""
    current_role: str = ""  # evolves with context


class EvidenceEngine:
    """Phase 2: Observes structure, collects evidence, tracks belief evolution."""

    def __init__(self):
        self.structure = FrozenRayEngine(swing_threshold=10.0)
        self.line_evidence: Dict[int, LineEvidence] = {}
        self.timeline: List[EvidenceEvent] = []
        self.belief_score = 0.0  # positive = bullish, negative = bearish
        self.belief_history: List[tuple] = []  # (bar, score, state)

        # Significance filter for continuation structure
        self.min_pts_from_prev = 15.0
        self.min_bars_between = 3
        self.min_bounce_pts = 10.0

        # Track significant lows/highs for continuation
        self.sig_lows: List[tuple] = []   # (bar, price)
        self.sig_highs: List[tuple] = []  # (bar, price)
        self.last_sig_low_bar = -99
        self.last_sig_low_price = 1e30
        self.last_sig_high_bar = -99
        self.last_sig_high_price = -1e30

    def _belief_state(self) -> str:
        """Convert belief score to named state."""
        if self.belief_score >= 6:
            return "STRONG_BULLISH"
        elif self.belief_score >= 3:
            return "BULLISH"
        elif self.belief_score >= 1:
            return "EMERGING_BULLISH"
        elif self.belief_score <= -6:
            return "STRONG_BEARISH"
        elif self.belief_score <= -3:
            return "BEARISH"
        elif self.belief_score <= -1:
            return "EMERGING_BEARISH"
        else:
            return "NEUTRAL"

    def _apply_belief_decay(self, bar_idx: int):
        """Belief drifts toward zero if no fresh evidence arrives.
        
        Half-life ~15 bars: decay_rate = 0.95 per bar (loses 5% per bar).
        After 15 bars without evidence: conviction halved.
        After 30 bars: quartered.
        
        This prevents permanent conviction from old information.
        Belief must be continuously reinforced to persist.
        """
        # Find most recent evidence event
        if not self.timeline:
            return

        last_event_bar = self.timeline[-1].bar
        bars_since_evidence = bar_idx - last_event_bar

        # Only decay if no evidence for 2+ bars (allow brief gaps)
        if bars_since_evidence >= 2:
            # Decay rate: 0.95 per bar of silence
            decay = 0.95
            self.belief_score *= decay

    def _get_question(self, line: FrozenRay) -> str:
        """Determine what question this line is currently asking based on context."""
        if line.line_type == "ORANGE":
            if self.belief_score > 0:
                return "Can bullish momentum break the ceiling?"
            return "Is bearish resolve still contained below?"

        elif line.line_type == "YELLOW":
            if self.belief_score < 0:
                return "Can bearish momentum break the floor?"
            return "Is bullish resolve still contained above?"

        elif line.line_type == "BLUE_ORIGINAL":
            if self.belief_score < -2:
                return "Has bearish resolve broken primary support?"
            return "Is primary support still holding?"

        elif line.line_type == "PURPLE_ORIGINAL":
            if self.belief_score > 2:
                return "Has bullish resolve broken primary resistance?"
            return "Is primary resistance still holding?"

        elif line.line_type == "PURPLE_PROFIT":
            return "Should profits be protected? (close above = exit)"

        return "Observing structure"

    def _dynamic_weight(self, direction: str, base_impact: float, line: FrozenRay = None) -> float:
        """Adjust evidence weight based on:
        1. Whether it confirms or challenges current belief (surprise factor)
        2. Line authority (higher authority = larger impact)
        3. Timeframe authority (strategic > tactical > continuation)
        
        Formula: weighted = base × surprise_multiplier × authority_multiplier
        
        Scott weights: Original > Tactical, Strategic > Continuation
        Higher authority reclaims/breaks have outsized impact.
        """
        # Authority multiplier from line rank
        # rank 1 (orange/yellow) = 1.5x, rank 2 (original) = 1.2x, rank 3 (tactical/continuation) = 0.8x
        if line and hasattr(line, 'authority_rank'):
            authority_map = {1: 1.5, 2: 1.2, 3: 0.8}
            authority_mult = authority_map.get(line.authority_rank, 1.0)
            # Continuation/evidence lines have even less weight
            if line.line_type in ("CONTINUATION_LOW", "CONTINUATION_HIGH"):
                authority_mult = 0.6
        else:
            authority_mult = 1.0

        # Surprise multiplier from belief contradiction
        is_bullish_evidence = (direction == "BULLISH")
        current_is_bullish = (self.belief_score > 0)
        current_is_bearish = (self.belief_score < 0)
        current_is_neutral = (abs(self.belief_score) <= 1)

        if current_is_neutral:
            surprise_mult = 1.0  # neutral: all evidence normal weight
        else:
            conviction_strength = min(abs(self.belief_score) / 10.0, 1.0)

            confirms_thesis = ((current_is_bullish and is_bullish_evidence) or
                              (current_is_bearish and not is_bullish_evidence))

            if confirms_thesis:
                # Expected — dampen (more conviction = more dampening)
                surprise_mult = 1.0 - (conviction_strength * 0.6)  # min 0.4x
            else:
                # Surprising — amplify (more conviction = more surprise)
                surprise_mult = 1.0 + (conviction_strength * 0.8)  # max 1.8x

        return base_impact * surprise_mult * authority_mult

    def _record_event(self, bar: int, time_str: str, event_type: str,
                      line: FrozenRay, direction: str, strength: float,
                      belief_impact: float, description: str):
        """Record an evidence event and update belief with dynamic weighting."""
        question = self._get_question(line)

        # Apply dynamic weighting: surprise × authority × timeframe
        weighted_impact = self._dynamic_weight(direction, belief_impact, line)

        event = EvidenceEvent(
            bar=bar, time=time_str, event_type=event_type,
            line_id=line.line_id, line_type=line.line_type,
            direction=direction, strength=strength,
            question=question, belief_impact=weighted_impact,
            description=description,
        )
        self.timeline.append(event)
        self.belief_score += weighted_impact

        # Update line evidence
        if line.line_id not in self.line_evidence:
            self.line_evidence[line.line_id] = LineEvidence(
                line_id=line.line_id, line_type=line.line_type)
        le = self.line_evidence[line.line_id]
        le.last_interaction_bar = bar
        le.last_interaction_type = event_type
        le.current_question = question

        if event_type == "TOUCH":
            le.touches += 1
        elif event_type == "REJECTION":
            le.rejections += 1
            le.strength_score += 1.0
        elif event_type == "BREAK":
            le.confirmed_breaks += 1
        elif event_type == "FAILED_BREAK":
            le.failed_breaks += 1
            le.strength_score += 0.5
        elif event_type == "RECLAIM":
            le.reclaims += 1

    def process_bar(self, bar_idx: int, open_p: float, high: float, low: float,
                    close: float, time_str: str):
        """Process one closed bar through structure + evidence layers."""

        # Remember state before structure update
        prev_lines = {l.line_id: (l.status, l.touch_count) for l in self.structure.lines}

        # Run structure engine
        self.structure.process_bar(open_p, high, low, close)

        # --- Detect evidence events by comparing before/after ---
        for line in self.structure.lines:
            line_val = line.value_at(bar_idx)
            prev_state = prev_lines.get(line.line_id)

            if prev_state is None:
                # New line created
                if line.status == "FROZEN" and line.line_type not in ("PURPLE_ORIGINAL", "BLUE_ORIGINAL"):
                    direction = "BEARISH" if line.direction == "SUPPORT" else "BULLISH"
                    self._record_event(bar_idx, time_str, "STRUCTURE_CREATED", line,
                                      direction, 1.0, 0.0,
                                      f"New {line.line_type} at {line.anchor_price:.0f}")
                continue

            prev_status, prev_touches = prev_state

            # Line was FROZEN and is now RETIRED → confirmed break
            if prev_status == "FROZEN" and line.status == "RETIRED":
                if line.direction == "SUPPORT":
                    # Support broken → bearish evidence
                    strength = 2.0 if line.authority_rank <= 2 else 1.0
                    impact = -strength
                    self._record_event(bar_idx, time_str, "BREAK", line,
                                      "BEARISH", strength, impact,
                                      f"{line.line_type} broken at {close:.0f} (was {line_val:.0f})")
                else:
                    # Resistance broken → bullish evidence
                    strength = 2.0 if line.authority_rank <= 2 else 1.0
                    impact = +strength
                    self._record_event(bar_idx, time_str, "BREAK", line,
                                      "BULLISH", strength, impact,
                                      f"{line.line_type} broken at {close:.0f} (was {line_val:.0f})")

            # Touch count increased → rejection event
            elif line.touch_count > prev_touches and line.status == "FROZEN":
                if line.direction == "RESISTANCE":
                    # Price touched resistance and was rejected → bearish evidence
                    self._record_event(bar_idx, time_str, "REJECTION", line,
                                      "BEARISH", 1.0, -0.5,
                                      f"Rejected at {line.line_type} ({line_val:.0f})")
                else:
                    # Price touched support and bounced → bullish evidence
                    self._record_event(bar_idx, time_str, "REJECTION", line,
                                      "BULLISH", 1.0, +0.5,
                                      f"Bounced off {line.line_type} ({line_val:.0f})")

        # --- Check for significant continuation structure ---
        self._check_continuation_structure(bar_idx, high, low, close, time_str)

        # --- Belief decay: drift toward zero if no fresh evidence ---
        # Half-life of ~15 bars: conviction decays 5% per bar without reinforcement
        # This prevents permanent conviction from old evidence
        self._apply_belief_decay(bar_idx)

        # --- Record belief state ---
        self.belief_history.append((bar_idx, self.belief_score, self._belief_state()))

    def _check_continuation_structure(self, bar_idx, high, low, close, time_str):
        """Check if a significant new low/high qualifies as continuation evidence."""
        n = self.structure.n_bars

        # Significant new low (bearish continuation)
        if low < self.last_sig_low_price:
            pts_below = self.last_sig_low_price - low
            bars_since = bar_idx - self.last_sig_low_bar

            if (pts_below >= self.min_pts_from_prev and
                bars_since >= self.min_bars_between):
                # Check bounce requirement
                bounce_found = False
                for j in range(self.last_sig_low_bar + 1, bar_idx):
                    if j < len(self.structure.highs):
                        if self.structure.highs[j] - self.last_sig_low_price >= self.min_bounce_pts:
                            bounce_found = True
                            break

                if bounce_found:
                    self.sig_lows.append((bar_idx, low))
                    self.last_sig_low_bar = bar_idx
                    self.last_sig_low_price = low

                    # This is bearish continuation evidence
                    # Create a synthetic evidence event (no specific line, structural)
                    dummy_line = FrozenRay(
                        line_id=-1, line_type="CONTINUATION_LOW", authority_rank=3,
                        anchor_price=low, anchor_bar=bar_idx, slope=1.83,
                        status="EVIDENCE", direction="SUPPORT", created_at_bar=bar_idx)
                    self._record_event(bar_idx, time_str, "STRUCTURE_CREATED", dummy_line,
                                      "BEARISH", 2.0, -2.0,
                                      f"Significant new low {low:.0f} (prev was {self.last_sig_low_price + pts_below:.0f}, -{pts_below:.0f}pts)")

        # Significant new high (bullish continuation)
        if high > self.last_sig_high_price:
            pts_above = high - self.last_sig_high_price
            bars_since = bar_idx - self.last_sig_high_bar

            if (pts_above >= self.min_pts_from_prev and
                bars_since >= self.min_bars_between):
                bounce_found = False
                for j in range(self.last_sig_high_bar + 1, bar_idx):
                    if j < len(self.structure.lows):
                        if self.last_sig_high_price - self.structure.lows[j] >= self.min_bounce_pts:
                            bounce_found = True
                            break

                if bounce_found:
                    self.sig_highs.append((bar_idx, high))
                    self.last_sig_high_bar = bar_idx
                    self.last_sig_high_price = high

                    dummy_line = FrozenRay(
                        line_id=-1, line_type="CONTINUATION_HIGH", authority_rank=3,
                        anchor_price=high, anchor_bar=bar_idx, slope=-1.83,
                        status="EVIDENCE", direction="RESISTANCE", created_at_bar=bar_idx)
                    self._record_event(bar_idx, time_str, "STRUCTURE_CREATED", dummy_line,
                                      "BULLISH", 2.0, +2.0,
                                      f"Significant new high {high:.0f} (prev was {self.last_sig_high_price - pts_above:.0f}, +{pts_above:.0f}pts)")

    def run_session(self, day_data: pd.DataFrame) -> pd.DataFrame:
        """Run evidence engine on a full session. Returns timeline DataFrame."""
        # Initialize continuation tracking from first bar
        self.last_sig_low_price = float(day_data.iloc[0]['Low'])
        self.last_sig_low_bar = 0
        self.last_sig_high_price = float(day_data.iloc[0]['High'])
        self.last_sig_high_bar = 0

        for i in range(len(day_data)):
            row = day_data.iloc[i]
            time_str = day_data.index[i].strftime('%H:%M') if hasattr(day_data.index[i], 'strftime') else str(i)
            self.process_bar(i, float(row['Open']), float(row['High']),
                           float(row['Low']), float(row['Close']), time_str)

        return pd.DataFrame([{
            'bar': e.bar, 'time': e.time, 'event': e.event_type,
            'line_type': e.line_type, 'direction': e.direction,
            'strength': e.strength, 'belief_impact': e.belief_impact,
            'belief_after': sum(ev.belief_impact for ev in self.timeline[:idx+1]),
            'question': e.question, 'description': e.description,
        } for idx, e in enumerate(self.timeline)])

    def print_timeline(self, max_events: int = 50):
        """Print human-readable evidence timeline."""
        print(f"\n{'='*80}")
        print(f"EVIDENCE TIMELINE — {len(self.timeline)} events")
        print(f"Final belief: {self.belief_score:+.1f} ({self._belief_state()})")
        print(f"{'='*80}")
        print(f"{'Bar':<5} {'Time':<6} {'Event':<12} {'Line':<18} {'Dir':<8} {'Impact':>7} {'Belief':>7} {'Description'}")
        print(f"{'-'*100}")

        running_belief = 0.0
        for e in self.timeline[:max_events]:
            running_belief += e.belief_impact
            print(f"{e.bar:<5} {e.time:<6} {e.event_type:<12} {e.line_type:<18} "
                  f"{e.direction:<8} {e.belief_impact:>+6.1f} {running_belief:>+7.1f}  {e.description}")

        if len(self.timeline) > max_events:
            print(f"  ... ({len(self.timeline) - max_events} more events)")

        print(f"\nFinal state: {self._belief_state()} (score: {self.belief_score:+.1f})")
