"""
Three-way validation: CSV Algo vs IB Live Account vs Mirror Account

This script compares:
1. CSV algo signals and P/L
2. IB live account trades and P/L (from logs/reports)
3. Mirror account trades and P/L (from logs/reports)

Validates that all three match for:
- Number of BUY signals
- Number of SELL signals
- Final P/L
- Signal timing
"""
import pandas as pd
import pytz
from pathlib import Path
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from datetime import datetime

def load_ib_trades(account_name, date_str):
    """
    Load IB trades from tracking/log files.
    
    Expected file format: ~/Desktop/IB_Live/tracking/YM_tracking_{date}_{time}.csv
    or ~/Desktop/IB_Live/tracking/YM_tracking_{account}_{date}_{time}.csv
    
    Returns: DataFrame with tracking data including signals and P/L
    """
    tracking_dir = Path.home() / "Desktop" / "IB_Live" / "tracking"
    
    # Try multiple possible file patterns
    if account_name == "live" or account_name == "main":
        # Main account - no account ID in filename
        patterns = [
            f"YM_tracking_{date_str}_*.csv",
            f"YM_tracking_{date_str}.csv",
        ]
    else:
        # Mirror/DUO account - has account ID in filename
        patterns = [
            f"YM_tracking_*_{date_str}_*.csv",
            f"YM_tracking_{account_name}_{date_str}_*.csv",
        ]
    
    for pattern in patterns:
        matching_files = list(tracking_dir.glob(pattern))
        if matching_files:
            # Use the most recent file (by name, which includes time)
            file_path = sorted(matching_files)[-1]
            print(f"  Found {account_name} log: {file_path.name}")
            df = pd.read_csv(file_path)
            return df
    
    print(f"  WARNING: No {account_name} log found for {date_str}")
    print(f"  Searched in: {tracking_dir}")
    print(f"  Patterns: {patterns}")
    return None


def validate_three_way(date_str="2026-05-12"):
    """
    Validate that CSV algo, IB live account, and mirror account all match.
    """
    
    print("\n" + "="*100)
    print(f"THREE-WAY VALIDATION FOR {date_str}")
    print("="*100)
    
    # ========================================================================
    # 1. Load CSV Algo Results
    # ========================================================================
    print("\n[1/3] Loading CSV Algo Results...")
    
    csv_path = Path.home() / "Desktop" / "2YearsData" / "full_day" / f"CBOT_MINI_YM1_{date_str}.csv"
    
    if not csv_path.exists():
        print(f"ERROR: CSV data not found: {csv_path}")
        return
    
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    est = pytz.timezone("US/Eastern")
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)
    
    # Filter to day session
    day_start = pd.Timestamp(f"{date_str} 09:30", tz=est)
    day_end = pd.Timestamp(f"{date_str} 17:00", tz=est)
    df = df[(df.index >= day_start) & (df.index <= day_end)]
    
    # Config matching live trading
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
        steep_line_exit_only=False,
    )
    
    # Run algo
    result = run_trading_algo_fast(df, target_date=date_str, start_time="09:30", end_time="17:00", config=config)
    
    # Extract CSV algo signals
    csv_signals = result[result['signal'].isin(['BUY', 'SELL'])].copy()
    csv_buys = (csv_signals['signal'] == 'BUY').sum()
    csv_sells = (csv_signals['signal'] == 'SELL').sum()
    csv_final_pl = result.iloc[-1]['session_pl']
    csv_partial_tp = (result['partial_tp'] == True).sum()
    
    print(f"  CSV Algo:")
    print(f"    BUY signals:  {csv_buys}")
    print(f"    SELL signals: {csv_sells}")
    print(f"    Final P/L:    {csv_final_pl:.1f} pts")
    print(f"    Partial TPs:  {csv_partial_tp}")
    
    # ========================================================================
    # 2. Load IB Live Account Trades
    # ========================================================================
    print("\n[2/3] Loading IB Live Account Trades...")
    
    ib_live_trades = load_ib_trades("live", date_str)
    
    if ib_live_trades is not None:
        ib_live_buys = (ib_live_trades['signal'] == 'BUY').sum()
        ib_live_sells = (ib_live_trades['signal'] == 'SELL').sum()
        
        # Calculate P/L if available
        if 'pl' in ib_live_trades.columns or 'session_pl' in ib_live_trades.columns:
            pl_col = 'session_pl' if 'session_pl' in ib_live_trades.columns else 'pl'
            ib_live_pl = ib_live_trades[pl_col].iloc[-1]
        else:
            ib_live_pl = None
        
        print(f"  IB Live Account:")
        print(f"    BUY signals:  {ib_live_buys}")
        print(f"    SELL signals: {ib_live_sells}")
        if ib_live_pl is not None:
            print(f"    Final P/L:    {ib_live_pl:.1f} pts")
        else:
            print(f"    Final P/L:    (not available in log)")
    else:
        ib_live_buys = None
        ib_live_sells = None
        ib_live_pl = None
    
    # ========================================================================
    # 3. Load Mirror Account Trades
    # ========================================================================
    print("\n[3/3] Loading Mirror Account Trades...")
    
    ib_mirror_trades = load_ib_trades("mirror", date_str)
    
    if ib_mirror_trades is not None:
        ib_mirror_buys = (ib_mirror_trades['signal'] == 'BUY').sum()
        ib_mirror_sells = (ib_mirror_trades['signal'] == 'SELL').sum()
        
        # Calculate P/L if available
        if 'pl' in ib_mirror_trades.columns or 'session_pl' in ib_mirror_trades.columns:
            pl_col = 'session_pl' if 'session_pl' in ib_mirror_trades.columns else 'pl'
            ib_mirror_pl = ib_mirror_trades[pl_col].iloc[-1]
        else:
            ib_mirror_pl = None
        
        print(f"  IB Mirror Account:")
        print(f"    BUY signals:  {ib_mirror_buys}")
        print(f"    SELL signals: {ib_mirror_sells}")
        if ib_mirror_pl is not None:
            print(f"    Final P/L:    {ib_mirror_pl:.1f} pts")
        else:
            print(f"    Final P/L:    (not available in log)")
    else:
        ib_mirror_buys = None
        ib_mirror_sells = None
        ib_mirror_pl = None
    
    # ========================================================================
    # 4. Compare All Three
    # ========================================================================
    print("\n" + "="*100)
    print("COMPARISON RESULTS")
    print("="*100)
    
    print(f"\n{'Source':<20} {'BUY Signals':<15} {'SELL Signals':<15} {'Final P/L':<15} {'Status':<10}")
    print("-"*100)
    
    # CSV Algo (baseline)
    print(f"{'CSV Algo':<20} {csv_buys:<15} {csv_sells:<15} {csv_final_pl:<15.1f} {'(baseline)':<10}")
    
    # IB Live Account
    if ib_live_buys is not None:
        buy_match = "✓" if ib_live_buys == csv_buys else "✗"
        sell_match = "✓" if ib_live_sells == csv_sells else "✗"
        if ib_live_pl is not None:
            pl_match = "✓" if abs(ib_live_pl - csv_final_pl) < 1.0 else "✗"
            pl_str = f"{ib_live_pl:.1f}"
        else:
            pl_match = "?"
            pl_str = "N/A"
        
        status = "PASS" if buy_match == "✓" and sell_match == "✓" else "FAIL"
        print(f"{'IB Live':<20} {ib_live_buys:<15} {ib_live_sells:<15} {pl_str:<15} {status:<10}")
        print(f"{'  Match?':<20} {buy_match:<15} {sell_match:<15} {pl_match:<15}")
    else:
        print(f"{'IB Live':<20} {'N/A':<15} {'N/A':<15} {'N/A':<15} {'NO DATA':<10}")
    
    # IB Mirror Account
    if ib_mirror_buys is not None:
        buy_match = "✓" if ib_mirror_buys == csv_buys else "✗"
        sell_match = "✓" if ib_mirror_sells == csv_sells else "✗"
        if ib_mirror_pl is not None:
            pl_match = "✓" if abs(ib_mirror_pl - csv_final_pl) < 1.0 else "✗"
            pl_str = f"{ib_mirror_pl:.1f}"
        else:
            pl_match = "?"
            pl_str = "N/A"
        
        status = "PASS" if buy_match == "✓" and sell_match == "✓" else "FAIL"
        print(f"{'IB Mirror':<20} {ib_mirror_buys:<15} {ib_mirror_sells:<15} {pl_str:<15} {status:<10}")
        print(f"{'  Match?':<20} {buy_match:<15} {sell_match:<15} {pl_match:<15}")
    else:
        print(f"{'IB Mirror':<20} {'N/A':<15} {'N/A':<15} {'N/A':<15} {'NO DATA':<10}")
    
    # ========================================================================
    # 5. Detailed Signal Timing Comparison (if data available)
    # ========================================================================
    if ib_live_trades is not None or ib_mirror_trades is not None:
        print("\n" + "="*100)
        print("SIGNAL TIMING COMPARISON")
        print("="*100)
        
        print(f"\n{'Time':<10} {'CSV':<10} {'IB Live':<10} {'IB Mirror':<10} {'Match':<10}")
        print("-"*100)
        
        # Get all unique signal times
        all_times = set()
        csv_signal_times = {idx.strftime('%H:%M'): row['signal'] for idx, row in csv_signals.iterrows()}
        all_times.update(csv_signal_times.keys())
        
        if ib_live_trades is not None and 'time' in ib_live_trades.columns:
            ib_live_signal_times = {pd.to_datetime(t).strftime('%H:%M'): s for t, s in zip(ib_live_trades['time'], ib_live_trades['signal'])}
            all_times.update(ib_live_signal_times.keys())
        else:
            ib_live_signal_times = {}
        
        if ib_mirror_trades is not None and 'time' in ib_mirror_trades.columns:
            ib_mirror_signal_times = {pd.to_datetime(t).strftime('%H:%M'): s for t, s in zip(ib_mirror_trades['time'], ib_mirror_trades['signal'])}
            all_times.update(ib_mirror_signal_times.keys())
        else:
            ib_mirror_signal_times = {}
        
        for time in sorted(all_times):
            csv_sig = csv_signal_times.get(time, '-')
            live_sig = ib_live_signal_times.get(time, '-')
            mirror_sig = ib_mirror_signal_times.get(time, '-')
            
            # Check if all match
            signals = [s for s in [csv_sig, live_sig, mirror_sig] if s != '-']
            match = "✓" if len(set(signals)) == 1 else "✗"
            
            print(f"{time:<10} {csv_sig:<10} {live_sig:<10} {mirror_sig:<10} {match:<10}")
    
    # ========================================================================
    # 6. Final Summary
    # ========================================================================
    print("\n" + "="*100)
    print("SUMMARY")
    print("="*100)
    
    all_match = True
    
    if ib_live_buys is not None:
        if ib_live_buys != csv_buys or ib_live_sells != csv_sells:
            print("\n✗ IB Live account signals DO NOT match CSV algo")
            all_match = False
        else:
            print("\n✓ IB Live account signals match CSV algo")
    else:
        print("\n? IB Live account data not available")
    
    if ib_mirror_buys is not None:
        if ib_mirror_buys != csv_buys or ib_mirror_sells != csv_sells:
            print("✗ IB Mirror account signals DO NOT match CSV algo")
            all_match = False
        else:
            print("✓ IB Mirror account signals match CSV algo")
    else:
        print("? IB Mirror account data not available")
    
    if all_match and (ib_live_buys is not None or ib_mirror_buys is not None):
        print("\n" + "="*100)
        print("✓✓✓ ALL ACCOUNTS MATCH! ✓✓✓")
        print("="*100)
    elif ib_live_buys is None and ib_mirror_buys is None:
        print("\n" + "="*100)
        print("⚠ NO IB ACCOUNT DATA AVAILABLE FOR COMPARISON")
        print("Please ensure IB trade logs are saved to:")
        print("  ~/Desktop/IB_Live/tracking/")
        print("="*100)
    
    print()


if __name__ == "__main__":
    import sys
    
    # Allow date to be passed as argument
    date_str = sys.argv[1] if len(sys.argv) > 1 else "2026-05-12"
    
    validate_three_way(date_str)
