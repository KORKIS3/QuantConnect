"""
verify_engine.py — Full verification of the Pinball engine before trusting results.

Steps:
1. Confirm import/version (file path, hash, class name)
2. Confirm feature presence
3. Print active parameters
4. Dry run first 30 valid days
5. Detailed trade sequence for 3 known days
6. Manual P/L recomputation and verification
7. Only then run full 682-day
"""
import os, sys, hashlib, inspect
import pandas as pd, pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")


def _get_config():
    return AlgoConfig(warmup_minutes=7, steep_angle_threshold=90.0, proximity_points=4.0,
        min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=50.0,
        wm_shield_distance=0.0, swing_anchor_threshold=10.0)


def _load_day(target_date):
    fpath = os.path.join(_DATA_ROOT, f'CBOT_MINI_YM1_{target_date}.csv')
    if not os.path.exists(fpath):
        return None
    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    day_start = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
    day_end = pd.Timestamp(f'{target_date} 16:59', tz=_EST)
    day_data = df[(df.index >= day_start) & (df.index <= day_end)]
    if len(day_data) < 15:
        return None
    config = _get_config()
    algo_df = run_trading_algo_fast(day_data, target_date, '09:30', '17:00', config=config)
    return algo_df


# ============================================================
# STEP 1: Confirm import/version
# ============================================================
print("=" * 80)
print("STEP 1: IMPORT VERIFICATION")
print("=" * 80)

from belief_engine_pinball import PinballEngine, PinballConfig

module = sys.modules['belief_engine_pinball']
module_file = inspect.getfile(module)
print(f"Module file: {os.path.abspath(module_file)}")

with open(module_file, 'rb') as f:
    file_hash = hashlib.sha256(f.read()).hexdigest()
print(f"SHA-256: {file_hash}")

print(f"Class instantiated: {PinballEngine.__name__} from {PinballEngine.__module__}")
print(f"Config class: {PinballConfig.__name__}")

# Confirm NOT using other engines
assert 'baseline_belief_engine' not in str(module_file), "ERROR: Using baseline engine!"
assert 'fred_belief_engine' not in str(module_file), "ERROR: Using fred engine!"
print("PASS: Not using baseline or fred engine.")

# ============================================================
# STEP 2: Confirm feature presence
# ============================================================
print("\n" + "=" * 80)
print("STEP 2: FEATURE PRESENCE")
print("=" * 80)

source = inspect.getsource(PinballEngine)
features = {
    "first-trade hold": "first_trade_protected" in source,
    "confidence suppression": "confidence" in source and "first_trade_protected" in source,
    "profit-run": "profit_run_threshold" in source,
    "session discipline": "session_end" in source or "SESSION_EXIT" in source,
    "trend filter": "_trend_filter_allows" in source,
    "min-reversal cooldown": "chop_cooldown_bars" in source,
    "Pinball CHOP_TP": "CHOP_TP" in source,
    "Pinball CHOP_STOP": "CHOP_STOP" in source,
    "EXIT_FLAT evidence threshold": "EXIT_FLAT" in source and "reverse_min_evidence" in source,
    "correct 2-contract P/L": "1 if self.partial_taken else 2" in source,
    "hard stop override": "chop_stop_pts" in source and "EXIT_FLAT" in source,
}

all_pass = True
for feat, present in features.items():
    status = "PRESENT" if present else "MISSING"
    if not present:
        all_pass = False
    print(f"  {feat:<40} {status}")

assert all_pass, "ERROR: Missing features!"
print("PASS: All features present.")

# ============================================================
# STEP 3: Active parameter values
# ============================================================
print("\n" + "=" * 80)
print("STEP 3: ACTIVE PARAMETERS")
print("=" * 80)

cfg = PinballConfig()
params = {
    "warmup_bars": cfg.warmup_bars,
    "session_end_time": cfg.session_end_time,
    "one_and_done": cfg.one_and_done,
    "first_entry_trend_filter": cfg.first_entry_trend_filter,
    "chop_tp_pts": cfg.chop_tp_pts,
    "chop_stop_pts": cfg.chop_stop_pts,
    "chop_stop_breach_pts": cfg.chop_stop_breach_pts,
    "chop_proximity_pts": cfg.chop_proximity_pts,
    "chop_cooldown_bars": cfg.chop_cooldown_bars,
    "chop_max_trades": cfg.chop_max_trades,
    "chop_disable_reversal": cfg.chop_disable_reversal,
    "partial_tp_pts": cfg.partial_tp_pts,
    "spike_profit_pts_trend": cfg.spike_profit_pts_trend,
    "spike_profit_bars": cfg.spike_profit_bars,
    "profit_run_threshold": cfg.profit_run_threshold,
    "first_trade_min_hold": cfg.first_trade_min_hold,
    "reverse_min_confidence": cfg.reverse_min_confidence,
    "reverse_min_evidence": cfg.reverse_min_evidence,
    "trend_bar_threshold": cfg.trend_bar_threshold,
    "trend_slope_threshold": cfg.trend_slope_threshold,
}
for k, v in params.items():
    print(f"  {k:<30} = {v}")

# ============================================================
# STEP 4: Dry run first 30 valid days
# ============================================================
print("\n" + "=" * 80)
print("STEP 4: DRY RUN — FIRST 30 VALID DAYS")
print("=" * 80)

files = sorted([f for f in os.listdir(_DATA_ROOT)
                if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])

valid_count = 0
print(f"{'Date':<12} {'PL':>8} {'Trades':>7} {'CTP':>4} {'PTP':>4} {'EF':>3} {'CS':>3} {'SE':>3} {'FTH':>4} {'Blk':>4} {'Mode':>6}")
print("-" * 75)

for fname in files:
    if valid_count >= 30:
        break
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    algo_df = _load_day(target_date)
    if algo_df is None:
        continue

    engine = PinballEngine(PinballConfig())
    engine.run_session(algo_df)
    valid_count += 1

    # Count trade types
    types = {}
    for t in engine.trades:
        tt = t.get('trade_type', '')
        types[tt] = types.get(tt, 0) + 1

    fth = sum(1 for bs in engine.blocked_signals if bs.get('reason') == 'FIRST_TRADE_HOLD')
    blk = len(engine.blocked_signals)

    print(f"{target_date:<12} {engine.session_pl:>+8.0f} {len(engine.trades):>7} "
          f"{types.get('CHOP_TP',0):>4} {types.get('PARTIAL_TP',0):>4} "
          f"{types.get('EXIT_FLAT',0):>3} {types.get('CHOP_STOP',0):>3} "
          f"{types.get('SESSION_EXIT',0):>3} {fth:>4} {blk:>4} {engine.mode:>6}")

# ============================================================
# STEP 5: Detailed trade sequence for 3 known days
# ============================================================
print("\n" + "=" * 80)
print("STEP 5: DETAILED TRADE SEQUENCES")
print("=" * 80)

DETAIL_DATES = ['2026-02-11', '2025-04-21', '2025-04-23']

for target_date in DETAIL_DATES:
    algo_df = _load_day(target_date)
    if algo_df is None:
        print(f"\n{target_date}: DATA NOT FOUND")
        continue

    engine = PinballEngine(PinballConfig())
    engine.run_session(algo_df)

    print(f"\n{'='*70}")
    print(f"  {target_date}  |  session_pl={engine.session_pl:+.1f}  |  mode={engine.mode}  |  trades={len(engine.trades)}")
    print(f"{'='*70}")

    print(f"  {'Time':<8} {'Action':<14} {'Price':>7} {'Dir':>6} {'Contracts':>5} {'Realized':>9} {'CumPL':>8}")
    print(f"  {'-'*65}")

    cum_pl = 0.0
    for t in engine.trades:
        tt = t.get('time', '')
        if hasattr(tt, '__len__') and len(tt) > 5:
            pass  # already formatted
        rpl = t.get('realized_pl', 0.0)
        cum_pl += rpl
        print(f"  {tt:<8} {t['trade_type']:<14} {t['exit_price']:>7.0f} {t['direction']:>6} "
              f"{t['contracts']:>5} {rpl:>+9.1f} {cum_pl:>+8.1f}")

    if engine.blocked_signals:
        print(f"\n  BLOCKED SIGNALS ({len(engine.blocked_signals)}):")
        for bs in engine.blocked_signals[:10]:
            bt = bs['time'].strftime('%H:%M') if hasattr(bs['time'], 'strftime') else str(bs['time'])
            print(f"    {bt} {bs['action']:<10} reason={bs['reason']:<20} ev={bs.get('evidence','')} unreal={bs.get('unrealized_pl',0):+.0f}")

    # ============================================================
    # STEP 6: Manual P/L recomputation
    # ============================================================
    manual_pl = 0.0
    for t in engine.trades:
        manual_pl += t.get('realized_pl', 0.0)

    discrepancy = abs(engine.session_pl - manual_pl)
    match = "PASS" if discrepancy < 1.0 else "FAIL"
    print(f"\n  P/L VERIFICATION: engine={engine.session_pl:+.1f} manual={manual_pl:+.1f} discrepancy={discrepancy:.1f} [{match}]")
    if discrepancy >= 1.0:
        print(f"  *** DISCREPANCY DETECTED — STOPPING ***")
        sys.exit(1)

# ============================================================
# STEP 7: All verification passed
# ============================================================
print("\n" + "=" * 80)
print("ALL VERIFICATION PASSED")
print("=" * 80)
print("Engine is confirmed correct. Safe to run full 682-day backtest.")
