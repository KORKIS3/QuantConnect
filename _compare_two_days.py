"""Compare signal generation on two different days"""
import pandas as pd
import pytz
from pathlib import Path
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

def analyze_day(date_str, data_source="historical"):
    """Analyze one day and return stats"""
    if data_source == "historical":
        csv_path = Path.home() / "Desktop" / "2YearsData" / "full_day" / f"CBOT_MINI_YM1_{date_str}.csv"
    else:  # live
        csv_path = Path.home() / "Desktop" / "IB_Live" / "tracking" / f"YM_tracking_DUO158495_{date_str}_0930.csv"
    
    if not csv_path.exists():
        return None
    
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    est = pytz.timezone('US/Eastern')
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)
    
    day_start = pd.Timestamp(f"{date_str} 09:30", tz=est)
    day_end = pd.Timestamp(f"{date_str} 17:00", tz=est)
    df = df[(df.index >= day_start) & (df.index <= day_end)]
    
    config = AlgoConfig(
        warmup_minutes=5,
        steep_angle_threshold=65.0,
        proximity_points=8.0,
        min_reversal_minutes=0,
        min_entry_angle=15.0,
        partial_tp_pts=50.0,
        spike_profit_pts=50.0,
        spike_profit_bars=9,
        wm_shield_distance=0.0,
        steep_line_reentry=False,
        steep_line_proximity=5.0,
        num_contracts=2,
    )
    
    result = run_trading_algo_fast(df, target_date=date_str, start_time="09:30", end_time="17:00", config=config)
    
    buy_signals = result[result['signal'] == 'BUY']
    sell_signals = result[result['signal'] == 'SELL']
    final_pl = result.iloc[-1]['session_pl']
    
    return {
        'date': date_str,
        'source': data_source,
        'bars': len(df),
        'buy_signals': len(buy_signals),
        'sell_signals': len(sell_signals),
        'total_trades': len(buy_signals) + len(sell_signals),
        'final_pl': final_pl,
        'first_signal_time': buy_signals.index[0] if len(buy_signals) > 0 else (sell_signals.index[0] if len(sell_signals) > 0 else None),
        'first_signal_type': buy_signals.iloc[0]['signal'] if len(buy_signals) > 0 else (sell_signals.iloc[0]['signal'] if len(sell_signals) > 0 else None),
    }

print("="*80)
print("COMPARING SIGNAL GENERATION ACROSS DAYS")
print("="*80)

# Test multiple days
days_to_test = [
    ("2024-01-02", "historical"),
    ("2024-01-03", "historical"),
    ("2024-01-04", "historical"),
    ("2026-05-14", "live"),
]

results = []
for date_str, source in days_to_test:
    stats = analyze_day(date_str, source)
    if stats:
        results.append(stats)
        print(f"\n{date_str} ({source}):")
        print(f"  Bars: {stats['bars']}")
        print(f"  BUY signals: {stats['buy_signals']}")
        print(f"  SELL signals: {stats['sell_signals']}")
        print(f"  Total trades: {stats['total_trades']}")
        print(f"  Final P/L: {stats['final_pl']:.1f} pts")
        if stats['first_signal_time']:
            print(f"  First signal: {stats['first_signal_type']} at {stats['first_signal_time']}")
    else:
        print(f"\n{date_str}: DATA NOT FOUND")

print("\n" + "="*80)
print("SUMMARY")
print("="*80)

if results:
    avg_trades = sum(r['total_trades'] for r in results) / len(results)
    avg_pl = sum(r['final_pl'] for r in results) / len(results)
    print(f"Average trades per day: {avg_trades:.1f}")
    print(f"Average P/L per day: {avg_pl:.1f} pts")
    
    print(f"\nTrade count range: {min(r['total_trades'] for r in results)} to {max(r['total_trades'] for r in results)}")
    print(f"P/L range: {min(r['final_pl'] for r in results):.1f} to {max(r['final_pl'] for r in results):.1f} pts")
