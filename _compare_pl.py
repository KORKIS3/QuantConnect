"""Compare session_pl_arr vs manual replay on a few days to find the 12pt gap."""
import os, pytz, pandas as pd, numpy as np
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0,
                    min_reversal_minutes=0, min_entry_angle=30.0)

diffs = []
for fname in sorted(os.listdir(_DATA_ROOT))[-30:]:
    if not fname.endswith(".csv"): continue
    date = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
    df = pd.read_csv(os.path.join(_DATA_ROOT, fname), index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    day = df[(df.index >= pd.Timestamp(f"{date} 09:30", tz=_EST)) &
             (df.index <= pd.Timestamp(f"{date} 16:59", tz=_EST))]
    if len(day) < 15: continue

    result = run_trading_algo_fast(day, date, "09:30", "17:00", config=config)
    end_ts = pd.Timestamp(f"{date} 17:00", tz=_EST)
    sliced = result[result.index <= end_ts]

    # Engine value
    engine_pl = float(sliced["session_pl"].iloc[-1])

    # Manual replay
    signals = result[result["signal"].isin(["BUY","SELL"])]
    closes = sliced["Close"].values.astype(float)
    times  = sliced.index
    sig_map = {ts: (row["signal"], float(row["buy_price"] if row["signal"]=="BUY" else row["sell_price"]))
               for ts, row in signals.iterrows()}
    tpls = []; pos, ep, partial_taken = "flat", None, False
    for i in range(len(sliced)):
        ts = times[i]; c = closes[i]
        if pos != "flat" and ep is not None and not partial_taken:
            if ((c-ep) if pos=="long" else (ep-c)) >= 50.0:
                tpls.append((c-ep) if pos=="long" else (ep-c))
                partial_taken = True
        if ts in sig_map:
            sig, price = sig_map[ts]
            if pos=="long" and sig=="SELL":
                tpls.append(price-ep); pos,ep,partial_taken = "short",price,False
            elif pos=="short" and sig=="BUY":
                tpls.append(ep-price); pos,ep,partial_taken = "long",price,False
            elif pos=="flat":
                pos,ep,partial_taken = ("long" if sig=="BUY" else "short"),price,False
    if pos != "flat" and ep is not None:
        tpls.append((closes[-1]-ep) if pos=="long" else (ep-closes[-1]))
    manual_pl = sum(tpls) if tpls else 0.0

    diff = engine_pl - manual_pl
    if abs(diff) > 1:
        diffs.append((date, engine_pl, manual_pl, diff))
        print(f"{date}  engine={engine_pl:+.0f}  manual={manual_pl:+.0f}  diff={diff:+.0f}")

print(f"\nTotal days with diff > 1pt: {len(diffs)}")
if diffs:
    avg_diff = np.mean([d[3] for d in diffs])
    print(f"Avg diff on those days: {avg_diff:+.1f}")
