"""
param_sweep.py — Robustness Sensitivity Sweep for Capital Preservation Parameters

Tests: TRADE_KILL, THESIS_TIMEOUT, DAILY_KILL
Goal: Find robust plateaus, not peaks. Reduce tail risk without harming expectancy.
"""

import os, time, itertools
import pandas as pd
import pytz
import numpy as np
from copy import deepcopy
from evidence_engine import EvidenceEngine
from conviction_engine import ConvictionEngine

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")


class SweepExecutionEngine:
    """Execution engine with configurable capital preservation parameters."""

    def __init__(self, trade_kill: float, thesis_timeout: int, daily_kill: float):
        self.trade_kill = trade_kill
        self.thesis_timeout = thesis_timeout
        self.daily_kill = daily_kill
        self.position = 0
        self.entry_price = 0.0
        self.entry_bar = -1
        self.trades = []
        self.session_pl = 0.0
        self._daily_killed = False

    def run_session(self, day_data: pd.DataFrame) -> dict:
        n = len(day_data)
        closes = day_data['Close'].values

        evidence = EvidenceEngine()
        evidence.run_session(day_data)

        conviction = ConvictionEngine(persistence_bars=3)
        for bar, score, _ in evidence.belief_history:
            conviction.process_bar(bar, score)

        for bar, state, score in conviction.state_history:
            close = closes[bar]

            if self.position == 0:
                if self._daily_killed:
                    continue
                if state in ("BEARISH_CONVICTION", "STRONG_BEARISH_RESOLVE"):
                    self.position = -1
                    self.entry_price = close
                    self.entry_bar = bar
                elif state in ("BULLISH_CONVICTION", "STRONG_BULLISH_RESOLVE"):
                    self.position = +1
                    self.entry_price = close
                    self.entry_bar = bar

            elif self.position != 0:
                unrealized = (close - self.entry_price) * self.position * 2
                bars_held = bar - self.entry_bar

                should_exit = False
                exit_reason = ""

                # Capital preservation
                if unrealized <= -self.trade_kill:
                    should_exit = True
                    exit_reason = "TRADE_KILL"
                elif self.session_pl + unrealized <= -self.daily_kill:
                    should_exit = True
                    exit_reason = "DAILY_KILL"
                    self._daily_killed = True
                elif bars_held >= self.thesis_timeout and unrealized <= 0:
                    should_exit = True
                    exit_reason = "THESIS_TIMEOUT"

                # Conviction exits
                elif state in ("TRANSITION", "THESIS_CHALLENGED"):
                    should_exit = True
                    exit_reason = state
                elif state == "OBSERVING":
                    should_exit = True
                    exit_reason = "CONVICTION_LOST"
                elif self.position == -1 and state in ("BULLISH_CONVICTION", "STRONG_BULLISH_RESOLVE"):
                    should_exit = True
                    exit_reason = "REVERSED"
                elif self.position == 1 and state in ("BEARISH_CONVICTION", "STRONG_BEARISH_RESOLVE"):
                    should_exit = True
                    exit_reason = "REVERSED"

                if should_exit:
                    pl = (close - self.entry_price) * self.position * 2
                    self.session_pl += pl
                    self.trades.append({
                        'entry_bar': self.entry_bar, 'exit_bar': bar,
                        'direction': 'SHORT' if self.position == -1 else 'LONG',
                        'entry_price': self.entry_price, 'exit_price': close,
                        'pl': pl, 'bars_held': bars_held, 'exit_reason': exit_reason,
                    })
                    self.position = 0
                    self.entry_price = 0.0

        if self.position != 0:
            close = closes[-1]
            pl = (close - self.entry_price) * self.position * 2
            self.session_pl += pl
            self.trades.append({
                'entry_bar': self.entry_bar, 'exit_bar': n - 1,
                'direction': 'SHORT' if self.position == -1 else 'LONG',
                'entry_price': self.entry_price, 'exit_price': close,
                'pl': pl, 'bars_held': (n - 1) - self.entry_bar, 'exit_reason': 'SESSION_END',
            })
            self.position = 0

        return {'session_pl': self.session_pl, 'trades': self.trades}


def load_all_days():
    """Pre-load all day data to avoid repeated I/O during sweeps."""
    files = sorted([f for f in os.listdir(_DATA_ROOT)
                    if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])
    days = []
    for fname in files:
        fpath = os.path.join(_DATA_ROOT, fname)
        try:
            df = pd.read_csv(fpath, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        except:
            continue
        target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        day_start = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
        day_end = pd.Timestamp(f'{target_date} 16:59', tz=_EST)
        day_data = df[(df.index >= day_start) & (df.index <= day_end)]
        if len(day_data) < 15:
            continue
        if (day_data[["Open", "High", "Low", "Close"]] <= 0).any().any():
            continue
        if day_data["High"].max() == day_data["Low"].min():
            continue
        days.append((target_date, day_data))
    return days


def run_sweep_single(days, trade_kill, thesis_timeout, daily_kill):
    """Run one parameter combination across all days."""
    daily_pls = []
    all_trades = []

    for date, day_data in days:
        engine = SweepExecutionEngine(trade_kill, thesis_timeout, daily_kill)
        result = engine.run_session(day_data)
        daily_pls.append(result['session_pl'])
        all_trades.extend(result['trades'])

    return compute_metrics(daily_pls, all_trades)


def compute_metrics(daily_pls, all_trades):
    """Compute comprehensive metrics from results."""
    n = len(daily_pls)
    total_pl = sum(daily_pls)
    trade_pls = [t['pl'] for t in all_trades]

    # Max drawdown (cumulative)
    cum = np.cumsum(daily_pls)
    peak = np.maximum.accumulate(cum)
    drawdown = peak - cum
    max_dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0

    # Profit factor
    gross_profit = sum(p for p in trade_pls if p > 0)
    gross_loss = abs(sum(p for p in trade_pls if p < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else 999

    # Losing streak
    max_losing_streak = 0
    current_streak = 0
    for pl in daily_pls:
        if pl <= 0:
            current_streak += 1
            max_losing_streak = max(max_losing_streak, current_streak)
        else:
            current_streak = 0

    # Tail risk: days worse than -400
    catastrophic_days = sum(1 for p in daily_pls if p <= -400)

    # Winner/loser distribution
    winners = [p for p in trade_pls if p > 0]
    losers = [p for p in trade_pls if p <= 0]
    avg_win = np.mean(winners) if winners else 0
    avg_loss = np.mean(losers) if losers else 0

    return {
        'avg_day': total_pl / n if n > 0 else 0,
        'total_pl': total_pl,
        'worst_trade': min(trade_pls) if trade_pls else 0,
        'worst_day': min(daily_pls) if daily_pls else 0,
        'best_day': max(daily_pls) if daily_pls else 0,
        'max_drawdown': max_dd,
        'profit_factor': pf,
        'trade_count': len(all_trades),
        'win_rate': sum(1 for p in trade_pls if p > 0) / len(trade_pls) * 100 if trade_pls else 0,
        'losing_streak': max_losing_streak,
        'avg_winner': avg_win,
        'avg_loser': avg_loss,
        'catastrophic_days': catastrophic_days,
        'win_days': sum(1 for p in daily_pls if p > 0),
        'lose_days': sum(1 for p in daily_pls if p <= 0),
    }


def sweep_single_param(days, param_name, values, defaults):
    """Sweep one parameter while holding others at defaults."""
    results = []
    for val in values:
        params = defaults.copy()
        params[param_name] = val
        metrics = run_sweep_single(days, params['trade_kill'], params['thesis_timeout'], params['daily_kill'])
        metrics['param_value'] = val
        results.append(metrics)
    return results


def print_sweep_results(param_name, values, results):
    """Print formatted sweep results."""
    print(f"\n{'='*100}")
    print(f"  SENSITIVITY SWEEP: {param_name}")
    print(f"{'='*100}")
    print(f"{'Value':<8} {'Avg/Day':>8} {'Worst Tr':>9} {'Worst Day':>10} {'MaxDD':>8} "
          f"{'PF':>6} {'Trades':>7} {'WinR%':>6} {'LStreak':>8} "
          f"{'AvgWin':>7} {'AvgLoss':>8} {'Cat Days':>9}")
    print(f"{'-'*100}")

    for val, m in zip(values, results):
        print(f"{val:<8} {m['avg_day']:>+7.1f} {m['worst_trade']:>+9.0f} {m['worst_day']:>+10.0f} "
              f"{m['max_drawdown']:>8.0f} {m['profit_factor']:>6.2f} {m['trade_count']:>7} "
              f"{m['win_rate']:>5.1f}% {m['losing_streak']:>8} "
              f"{m['avg_winner']:>+7.0f} {m['avg_loser']:>+8.0f} {m['catastrophic_days']:>9}")


def main():
    print("Loading all day data...")
    t0 = time.time()
    days = load_all_days()
    print(f"Loaded {len(days)} days in {time.time()-t0:.1f}s\n")

    # Current defaults (baseline)
    defaults = {'trade_kill': 200, 'thesis_timeout': 40, 'daily_kill': 500}

    # === SWEEP 1: TRADE_KILL ===
    trade_kill_values = [100, 125, 150, 175, 200, 250, 300, 400, 500, 750]
    print(f"Sweeping TRADE_KILL: {trade_kill_values}")
    tk_results = sweep_single_param(days, 'trade_kill', trade_kill_values, defaults)
    print_sweep_results("TRADE_KILL (max adverse excursion per trade)", trade_kill_values, tk_results)

    # === SWEEP 2: THESIS_TIMEOUT ===
    thesis_timeout_values = [15, 20, 25, 30, 35, 40, 50, 60, 80, 100]
    print(f"\nSweeping THESIS_TIMEOUT: {thesis_timeout_values}")
    tt_results = sweep_single_param(days, 'thesis_timeout', thesis_timeout_values, defaults)
    print_sweep_results("THESIS_TIMEOUT (bars with no progress → exit)", thesis_timeout_values, tt_results)

    # === SWEEP 3: DAILY_KILL ===
    daily_kill_values = [200, 300, 400, 500, 600, 750, 1000, 1500, 9999]
    print(f"\nSweeping DAILY_KILL: {daily_kill_values}")
    dk_results = sweep_single_param(days, 'daily_kill', daily_kill_values, defaults)
    print_sweep_results("DAILY_KILL (session hard stop)", daily_kill_values, dk_results)

    # === SUMMARY: Identify plateaus ===
    print(f"\n{'='*100}")
    print(f"  PLATEAU ANALYSIS")
    print(f"{'='*100}")

    print(f"\nTRADE_KILL plateau identification:")
    print(f"  Look for ranges where avg/day is stable AND worst_day/max_dd improve.")
    print(f"  A 'plateau' = parameter range where metrics don't change much.")

    print(f"\nTHESIS_TIMEOUT plateau identification:")
    print(f"  Shorter timeout = fewer stuck trades but may cut winners.")
    print(f"  Look for the knee where shortening stops helping.")

    print(f"\nDAILY_KILL plateau identification:")
    print(f"  Tighter daily kill = fewer catastrophic days but may cap recovery.")
    print(f"  Look for where catastrophic_days drops without avg/day collapsing.")

    # === Robustness score (composite) ===
    print(f"\n{'='*100}")
    print(f"  ROBUSTNESS RANKING (composite score)")
    print(f"{'='*100}")
    print(f"  Score = avg_day × profit_factor / (max_drawdown/1000) × (1 - catastrophic_days/645)")
    print(f"  Higher = better risk-adjusted robustness\n")

    # Run a focused grid around promising ranges
    print(f"\n  Top candidates from each sweep (by robustness score):")
    for name, values, results in [("TRADE_KILL", trade_kill_values, tk_results),
                                   ("THESIS_TIMEOUT", thesis_timeout_values, tt_results),
                                   ("DAILY_KILL", daily_kill_values, dk_results)]:
        scored = []
        for val, m in zip(values, results):
            dd_factor = max(m['max_drawdown'] / 1000, 0.1)
            cat_factor = max(1 - m['catastrophic_days'] / 645, 0.1)
            score = m['avg_day'] * m['profit_factor'] / dd_factor * cat_factor
            scored.append((score, val, m))
        scored.sort(reverse=True)
        print(f"\n  {name}:")
        for score, val, m in scored[:3]:
            print(f"    {val:>6} → score={score:.1f}  avg={m['avg_day']:+.1f}/day  "
                  f"worst_day={m['worst_day']:+.0f}  maxDD={m['max_drawdown']:.0f}  "
                  f"cat_days={m['catastrophic_days']}  PF={m['profit_factor']:.2f}")


if __name__ == "__main__":
    main()
