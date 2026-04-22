import pandas as pd, pytz, os
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

date    = "2026-04-21"
start_t = "09:30"
end_t   = "17:00"

df = pd.read_csv(os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
ds = pd.Timestamp(f"{date} {start_t}", tz=_EST)
de = pd.Timestamp(f"{date} {end_t}",   tz=_EST)
df = df[(df.index >= ds) & (df.index <= de)]

cfg = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=10,
    min_entry_angle=30.0,
    partial_tp_pts=50.0,
    wm_shield_distance=12.0,
)

result = run_trading_algo_fast(df, date, start_t, end_t, config=cfg)

signals  = result[result["signal"].isin(["BUY","SELL"])]
partials = result[result["partial_tp"] == True]
final_pl = float(result["pl"].iloc[-1])
max_pl   = float(result["pl"].max())
min_pl   = float(result["pl"].min())

print(f"=== {date}  {start_t}-{end_t} ===")
print(f"Bars:       {len(result)}")
print(f"Signals:    {len(signals)}")
print(f"Partial TPs:{len(partials)}")
print(f"Final P/L:  {final_pl:+.0f} pts  /  ${final_pl*5*2:+,.0f}  (2 contracts)")
print(f"Peak P/L:   {max_pl:+.0f} pts")
print(f"Trough P/L: {min_pl:+.0f} pts")
print()

print("Signals:")
for ts, row in signals.iterrows():
    sig   = row["signal"]
    price = row["buy_price"] if sig == "BUY" else row["sell_price"]
    liq   = " [LIQ]" if row["is_liquidation"] else ""
    print(f"  {ts.strftime('%H:%M')}  {sig:4s} @ {int(price)}   P/L: {row['pl']:+.0f} pts{liq}")

if len(partials):
    print()
    print("Partial TPs (1 contract closed at 50pts):")
    for ts, row in partials.iterrows():
        print(f"  {ts.strftime('%H:%M')}  close={int(row['Close'])}  P/L: {row['pl']:+.0f} pts")

print()
print("Hourly P/L:")
for hour in range(9, 18):
    hour_bars = result[result.index.hour == hour]
    if hour_bars.empty: continue
    prev = result[result.index < hour_bars.index[0]]
    start_pl = float(prev["pl"].iloc[-1]) if len(prev) else 0.0
    end_pl   = float(hour_bars["pl"].iloc[-1])
    print(f"  {hour:02d}:00-{hour+1:02d}:00  {end_pl-start_pl:+.0f} pts")
