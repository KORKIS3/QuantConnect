"""
visualize_beliefs.py — Line Authority & Belief Evolution

Shows how line AUTHORITY (not existence) changes over time.
A line that's been crossed doesn't die — its authority decays.
A line that's been respected multiple times gains authority.

This is the belief layer visualization — not geometry, but meaning.
"""
import os, sys
import pandas as pd, pytz, numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.widgets import Slider

_EST = pytz.timezone('US/Eastern')
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")


def load_day(target_date):
    fpath = os.path.join(_DATA_ROOT, f'CBOT_MINI_YM1_{target_date}.csv')
    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    day_start = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
    day_end = pd.Timestamp(f'{target_date} 16:59', tz=_EST)
    return df[(df.index >= day_start) & (df.index <= day_end)].reset_index()


class BeliefLine:
    """A line as a BELIEF — not just geometry."""
    def __init__(self, line_id, line_type, anchor_price, anchor_bar, slope, direction):
        self.line_id = line_id
        self.line_type = line_type  # ORANGE, YELLOW, PURPLE, BLUE
        self.anchor_price = anchor_price
        self.anchor_bar = anchor_bar
        self.slope = slope
        self.direction = direction  # RESISTANCE or SUPPORT

        # Authority starts at base level, evolves with evidence
        self.base_authority = {'ORANGE': 10, 'YELLOW': 10, 'PURPLE': 7, 'BLUE': 7}[line_type]
        self.authority = float(self.base_authority)

        # Belief state
        self.touches = 0           # respect events (authority +)
        self.violations = 0        # close beyond (authority -)
        self.reclaims = 0          # price returns inside after violation (authority partial restore)
        self.status = "ACTIVE"     # ACTIVE, CHALLENGED, WEAKENED, DEAD

        # History
        self.authority_history = []  # (bar, authority) for plotting

    def value_at(self, bar):
        return self.anchor_price + self.slope * (bar - self.anchor_bar)

    def record_touch(self, bar):
        """Price respected the line — authority increases."""
        self.touches += 1
        self.authority = min(self.authority + 1.5, self.base_authority + 5)
        self._update_status()

    def record_violation(self, bar):
        """Close beyond line — authority decays (does NOT die)."""
        self.violations += 1
        self.authority -= 3.0  # significant decay
        if self.authority < 0:
            self.authority = 0
        self._update_status()

    def record_reclaim(self, bar):
        """Price returned inside after violation — partial authority restore."""
        self.reclaims += 1
        self.authority += 1.0  # partial restore
        self._update_status()

    def _update_status(self):
        if self.authority >= self.base_authority * 0.8:
            self.status = "ACTIVE"
        elif self.authority >= self.base_authority * 0.4:
            self.status = "CHALLENGED"
        elif self.authority > 0:
            self.status = "WEAKENED"
        else:
            self.status = "DEAD"

    def snapshot(self, bar):
        self.authority_history.append((bar, self.authority, self.status))


class BeliefEngine:
    """Tracks line beliefs over time — authority evolution, not binary existence."""

    def __init__(self, swing_threshold=10.0):
        self.swing_threshold = swing_threshold
        self.lines = []
        self._next_id = 1
        self.resolve_direction = 0  # +1 bullish, -1 bearish, 0 neutral
        self.resolve_strength = 0.0
        self.resolve_history = []  # (bar, direction, strength)

        # Bar data
        self.highs = []
        self.lows = []
        self.closes = []
        self.n_bars = 0

    def process_bar(self, open_p, high, low, close):
        bar = self.n_bars
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)
        self.n_bars += 1

        # Create initial structure on first bar
        if bar == 0:
            self._create_line("ORANGE", high, bar, -1.83, "RESISTANCE")
            self._create_line("YELLOW", low, bar, +1.83, "SUPPORT")
            self._create_line("PURPLE", high, bar, -1.83, "RESISTANCE")  # provisional slope
            self._create_line("BLUE", low, bar, +1.83, "SUPPORT")  # provisional slope
            self._snapshot_all(bar)
            return

        # New session extremes — create new lines (don't kill old ones)
        if high > max(self.highs[:-1]):
            self._create_line("ORANGE", high, bar, -1.83, "RESISTANCE")

        if low < min(self.lows[:-1]):
            # Only create new yellow if this is a MEANINGFUL new low (>15 pts below previous)
            prev_session_low = min(self.lows[:-1])
            if prev_session_low - low >= 15:
                self._create_line("YELLOW", low, bar, +1.83, "SUPPORT")

        # Evaluate each line
        for line in self.lines:
            line_val = line.value_at(bar)

            if line.direction == "RESISTANCE":
                # Touch: high approaches but close stays below
                if high >= line_val - 10 and close < line_val:
                    line.record_touch(bar)
                # Violation: close above resistance
                elif close > line_val and line.status != "DEAD":
                    line.record_violation(bar)
                # Reclaim: was violated, now close back below
                elif line.violations > 0 and close < line_val and bar > 0:
                    if self.closes[bar - 1] > line.value_at(bar - 1):
                        line.record_reclaim(bar)

            elif line.direction == "SUPPORT":
                # Touch: low approaches but close stays above
                if low <= line_val + 10 and close > line_val:
                    line.record_touch(bar)
                # Violation: close below support
                elif close < line_val and line.status != "DEAD":
                    line.record_violation(bar)
                # Reclaim: was violated, now close back above
                elif line.violations > 0 and close > line_val and bar > 0:
                    if self.closes[bar - 1] < line.value_at(bar - 1):
                        line.record_reclaim(bar)

        # Update resolve direction
        self._update_resolve(bar)
        self._snapshot_all(bar)

    def _create_line(self, line_type, anchor_price, anchor_bar, slope, direction):
        line = BeliefLine(self._next_id, line_type, anchor_price, anchor_bar, slope, direction)
        self._next_id += 1
        self.lines.append(line)

    def _update_resolve(self, bar):
        """Track overall market resolve based on line violations."""
        # Count recent violations by direction
        bullish_violations = 0  # resistance lines violated (bullish)
        bearish_violations = 0  # support lines violated (bearish)

        for line in self.lines:
            if line.violations > 0 and line.authority < line.base_authority * 0.5:
                if line.direction == "RESISTANCE":
                    bullish_violations += line.violations
                else:
                    bearish_violations += line.violations

        if bearish_violations > bullish_violations + 2:
            self.resolve_direction = -1
            self.resolve_strength = min(10, bearish_violations - bullish_violations)
        elif bullish_violations > bearish_violations + 2:
            self.resolve_direction = +1
            self.resolve_strength = min(10, bullish_violations - bearish_violations)
        else:
            self.resolve_direction = 0
            self.resolve_strength = 0

        self.resolve_history.append((bar, self.resolve_direction, self.resolve_strength))

    def _snapshot_all(self, bar):
        for line in self.lines:
            line.snapshot(bar)


def run_belief_replay(target_date):
    data = load_day(target_date)
    n = len(data)
    highs = data['High'].values
    lows = data['Low'].values
    closes = data['Close'].values
    opens = data['Open'].values
    times = [data.iloc[i]['time'].strftime('%H:%M') for i in range(n)]

    # Run belief engine
    engine = BeliefEngine(swing_threshold=10.0)
    for i in range(n):
        engine.process_bar(opens[i], highs[i], lows[i], closes[i])

    # --- PLOT: 3 panels ---
    fig, (ax_price, ax_auth, ax_resolve) = plt.subplots(3, 1, figsize=(18, 12),
        gridspec_kw={'height_ratios': [3, 1.5, 0.8]}, sharex=True)
    fig.suptitle(f'BELIEF EVOLUTION — {target_date}', fontsize=13, fontweight='bold')

    # Panel 1: Price + lines colored by authority
    for i in range(n):
        color = 'green' if closes[i] >= opens[i] else 'red'
        ax_price.plot([i, i], [lows[i], highs[i]], color='black', linewidth=0.5)
        body_lo = min(opens[i], closes[i]); body_hi = max(opens[i], closes[i])
        rect = Rectangle((i - 0.3, body_lo), 0.6, max(body_hi - body_lo, 1),
                         facecolor=color, edgecolor='black', linewidth=0.5)
        ax_price.add_patch(rect)

    # Draw lines with alpha proportional to authority
    line_colors = {'ORANGE': 'orange', 'YELLOW': 'gold', 'PURPLE': 'purple', 'BLUE': 'deepskyblue'}
    for line in engine.lines:
        color = line_colors.get(line.line_type, 'gray')
        xs = list(range(line.anchor_bar, n))
        ys = [line.value_at(x) for x in xs]
        # Alpha based on final authority
        alpha = max(0.1, line.authority / line.base_authority)
        lw = 2.0 if line.authority > line.base_authority * 0.5 else 0.8
        style = '-' if line.status in ("ACTIVE", "CHALLENGED") else '--'
        ax_price.plot(xs, ys, color=color, linewidth=lw, alpha=alpha, linestyle=style)

    ax_price.set_ylabel('Price')
    ax_price.grid(True, alpha=0.15)

    # Panel 2: Authority over time for key lines
    for line in engine.lines:
        if not line.authority_history:
            continue
        # Only show lines that had meaningful life
        if line.touches + line.violations < 1:
            continue
        color = line_colors.get(line.line_type, 'gray')
        bars = [h[0] for h in line.authority_history]
        auths = [h[1] for h in line.authority_history]
        label = f"{line.line_type}#{line.line_id} ({line.anchor_price:.0f})"
        ax_auth.plot(bars, auths, color=color, linewidth=1.2, alpha=0.7, label=label)

    ax_auth.axhline(0, color='red', linewidth=0.5, linestyle='--', alpha=0.5)
    ax_auth.set_ylabel('Authority')
    ax_auth.set_ylim(-2, 15)
    ax_auth.grid(True, alpha=0.15)
    ax_auth.legend(loc='upper right', fontsize=7, ncol=3)

    # Panel 3: Resolve direction
    resolve_bars = [r[0] for r in engine.resolve_history]
    resolve_dirs = [r[1] * r[2] for r in engine.resolve_history]  # direction * strength
    ax_resolve.fill_between(resolve_bars, resolve_dirs, 0,
                            where=[d < 0 for d in resolve_dirs], color='red', alpha=0.4, label='Bearish')
    ax_resolve.fill_between(resolve_bars, resolve_dirs, 0,
                            where=[d > 0 for d in resolve_dirs], color='green', alpha=0.4, label='Bullish')
    ax_resolve.axhline(0, color='black', linewidth=0.5)
    ax_resolve.set_ylabel('Resolve')
    ax_resolve.set_xlabel('Bar')
    ax_resolve.set_ylim(-10, 10)
    ax_resolve.legend(loc='upper right', fontsize=8)
    ax_resolve.grid(True, alpha=0.15)

    # X ticks
    ticks = list(range(0, n, max(1, n // 15)))
    labels = [times[t] for t in ticks]
    ax_resolve.set_xticks(ticks)
    ax_resolve.set_xticklabels(labels, rotation=45, fontsize=8)

    plt.tight_layout()
    plt.show()

    # Print summary
    print(f"\n{'='*60}")
    print(f"BELIEF SUMMARY — {target_date}")
    print(f"{'='*60}")
    print(f"Final resolve: {'BEARISH' if engine.resolve_direction < 0 else 'BULLISH' if engine.resolve_direction > 0 else 'NEUTRAL'} "
          f"(strength: {engine.resolve_strength:.0f})")
    print(f"\nLines with meaningful activity:")
    print(f"{'ID':<4} {'Type':<8} {'Anchor':>7} {'Auth':>5} {'Status':<10} {'Touch':>5} {'Viol':>5} {'Recl':>5}")
    for line in engine.lines:
        if line.touches + line.violations >= 1:
            print(f"{line.line_id:<4} {line.line_type:<8} {line.anchor_price:>7.0f} "
                  f"{line.authority:>5.1f} {line.status:<10} {line.touches:>5} {line.violations:>5} {line.reclaims:>5}")


if __name__ == "__main__":
    target_date = sys.argv[1] if len(sys.argv) > 1 else '2026-02-11'
    run_belief_replay(target_date)
