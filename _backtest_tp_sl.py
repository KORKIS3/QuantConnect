"""Backtest: Ray Engine + TP/SL (60/50) + Cushion Entry (40pts)

Strategy:
- Entry: Ray engine signals (same as TradingAlgoFast)
- Entry price: signal_price - 40 (BUY) or signal_price + 40 (SELL) — cushion
- Exit: TP at +60 pts total (2 contracts), SL at -50 pts total, or next signal reversal
- 5-bar limit: if cushion entry doesn't fill within 5 bars, skip that entry

Usage: python _backtest_tp_sl.py [--quick] [--max-days N] [--no-cushion]
"""
import argparse, os, time
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

TP_PTS = 60.0    # total TP (both contracts)
SL_PTS = 50.0    # total SL (both contracts)
CUSHION = 40.0   # enter 40 pts better than signal
CUSHION_BARS = 5 # bars to wait for cushion fill


def simulate_tp_sl(algo_df, use_cushion=True):
    """Simulate TP/SL strategy on algo output. Returns session P/L."""
    n = len(algo_df)
    highs = algo_df['High'].values
    lows = algo_df['Low'].values
    closes = algo_df['Close'].values
    sig = algo_df['signal'].values

    pos = 0  # 0=flat, 1=long, -1=short
    entry_price = 0.0
    session_pl = 0.0
    pending_signal = None  # ('BUY'/'SELL', signal_bar_idx, limit_price)

    for i in range(n):
        s = str(sig[i]).strip()

        # Check if pending cushion entry fills
        if pending_signal is not None:
            sig_dir, sig_bar, limit_price = pending_signal
            bars_waiting = i - sig_bar

            if bars_waiting > CUSHION_BARS:
                # Expired — cancel
                pending_signal = None
            else:
                # Check if price reached our limit
                filled = False
                if sig_dir == 'BUY' and lows[i] <= limit_price:
                    filled = True
                    fill_price = limit_price
                elif sig_dir == 'SELL' and highs[i] >= limit_price:
                    filled = True
                    fill_price = limit_price

                if filled:
                    # Close existing position if reversing
                    if pos == 1 and sig_dir == 'SELL':
                        pl = (fill_price - entry_price) * 2
                        session_pl += pl
                        pos = 0
                    elif pos == -1 and sig_dir == 'BUY':
                        pl = (entry_price - fill_price) * 2
                        session_pl += pl
                        pos = 0

                    # Enter new position
                    if sig_dir == 'BUY':
                        pos = 1
                    else:
                        pos = -1
                    entry_price = fill_price
                    pending_signal = None

        # Check TP/SL on open position
        if pos != 0:
            if pos == 1:
                unrealized_best = (highs[i] - entry_price) * 2
                unrealized_worst = (lows[i] - entry_price) * 2
            else:
                unrealized_best = (entry_price - lows[i]) * 2
                unrealized_worst = (entry_price - highs[i]) * 2

            # SL hit? (check first — worst case)
            if unrealized_worst <= -SL_PTS:
                session_pl += -SL_PTS
                pos = 0; entry_price = 0.0
                continue

            # TP hit?
            if unrealized_best >= TP_PTS:
                session_pl += TP_PTS
                pos = 0; entry_price = 0.0
                continue

        # New signal — queue cushion entry (or enter immediately if no cushion)
        if s in ('BUY', 'SELL'):
            if use_cushion:
                if s == 'BUY':
                    limit_price = closes[i] - CUSHION
                else:
                    limit_price = closes[i] + CUSHION

                # If we have an open position in the SAME direction, skip
                if (s == 'BUY' and pos == 1) or (s == 'SELL' and pos == -1):
                    continue

                pending_signal = (s, i, limit_price)
            else:
                # No cushion — enter at close immediately
                if s == 'BUY':
                    if pos == -1:
                        pl = (entry_price - closes[i]) * 2
                        session_pl += pl
                    if pos != 1:
                        pos = 1; entry_price = closes[i]
                elif s == 'SELL':
                    if pos == 1:
                        pl = (closes[i] - entry_price) * 2
                        session_pl += pl
                    if pos != -1:
                        pos = -1; entry_price = closes[i]

    # Close any open position at session end
    if pos != 0:
        if pos == 1:
            pl = (closes[-1] - entry_price) * 2
        else:
            pl = (entry_price - closes[-1]) * 2
        session_pl += pl

    return session_pl


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--max-days", type=int, default=0, dest="max_days")
    parser.add_argument("--no-cushion", action="store_true", dest="no_cushion")
    args = parser.parse_args()

    end_time = "10:30" if args.quick else "17:00"
    use_cushion = not args.no_cushion

    config = AlgoConfig(
        warmup_minutes=7, steep_angle_threshold=90.0, proximity_points=4.0,
        min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=50.0,
        wm_shield_distance=0.0, swing_anchor_threshold=10.0,
    )

    csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                        if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])
    if args.max_days > 0:
        csv_files = csv_files[-args.max_days:]

    total = len(csv_files)
    t_start = time.time()

    print(f"\n{'='*80}")
    print(f"  RAY ENGINE + TP/SL BACKTEST")
    print(f"  TP: +{TP_PTS:.0f} pts | SL: -{SL_PTS:.0f} pts | Cushion: {CUSHION:.0f} pts ({'ON' if use_cushion else 'OFF'})")
    print(f"  Cushion expiry: {CUSHION_BARS} bars")
    print(f"  Session: 09:30 - {end_time} ET | Days: {total}")
    print(f"{'='*80}\n")

    pls = []
    days_processed = 0

    for i, fname in enumerate(csv_files):
        target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        fpath = os.path.join(_DATA_ROOT, fname)

        try:
            df = pd.read_csv(fpath, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
            day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
            day_end = pd.Timestamp(f"{target_date} {end_time}", tz=_EST)
            day_data = df[(df.index >= day_start) & (df.index <= day_end)]

            if len(day_data) < 15: continue
            if (day_data[["Open", "High", "Low", "Close"]] <= 0).any().any(): continue
            if day_data["High"].max() == day_data["Low"].min(): continue
            if day_data["Volume"].sum() < 100: continue

            algo_df = run_trading_algo_fast(day_data, target_date, "09:30", end_time, config=config)
            pl = simulate_tp_sl(algo_df, use_cushion=use_cushion)
            pls.append(pl)
            days_processed += 1

            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{total}] {time.time()-t_start:.0f}s elapsed ...")

        except Exception:
            continue

    elapsed = time.time() - t_start
    total_pl = sum(pls)
    avg_pl = np.mean(pls) if pls else 0
    win_days = sum(1 for p in pls if p > 0)
    lose_days = sum(1 for p in pls if p <= 0)
    win_pct = win_days / days_processed * 100 if days_processed else 0

    print(f"\nProcessed {days_processed} days in {elapsed:.1f}s\n")
    print(f"{'='*80}")
    print(f"  RESULTS: Ray Engine + TP={TP_PTS:.0f} / SL={SL_PTS:.0f} / Cushion={CUSHION:.0f}")
    print(f"{'='*80}")
    print(f"  Total Points:  {total_pl:+,.0f}")
    print(f"  Avg Pts/Day:   {avg_pl:+.1f}")
    print(f"  Win Days:      {win_days} ({win_pct:.1f}%)")
    print(f"  Lose Days:     {lose_days}")
    print(f"  P/L (USD):     ${total_pl * 5:+,.0f}")
    print(f"{'='*80}")

    # Distribution
    if pls:
        pls_arr = np.array(pls)
        print(f"\n  Best day:   {pls_arr.max():+.0f} pts")
        print(f"  Worst day:  {pls_arr.min():+.0f} pts")
        print(f"  Median:     {np.median(pls_arr):+.0f} pts")
        print(f"  Std Dev:    {pls_arr.std():.0f} pts")


if __name__ == "__main__":
    main()
