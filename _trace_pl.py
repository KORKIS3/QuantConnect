import pandas as pd, pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from Backtest2Year import _calc_pl_from_engine

_EST = pytz.timezone("US/Eastern")
DATE = "2026-04-24"
fpath = r"C:\Users\Administrator\Desktop\2YearsData\full_day\CBOT_MINI_YM1_2026-04-24.csv"
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
day = df[(df.index >= pd.Timestamp("2026-04-24 09:30", tz=_EST)) & (df.index <= pd.Timestamp("2026-04-24 16:59", tz=_EST))]

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0,
                    min_reversal_minutes=0, min_entry_angle=30.0)
result = run_trading_algo_fast(day, DATE, "09:30", "17:00", config=config)

print("--- Signals from algo ---")
sigs = result[result["signal"].isin(["BUY","SELL"])]
for ts, row in sigs.iterrows():
    print(f"  {ts.strftime('%H:%M')}  {row['signal']}  price={row['buy_price'] if row['signal']=='BUY' else row['sell_price']:.0f}  partial_tp={result.loc[ts,'partial_tp']}")

print("\n--- partial_tp bars (algo booked 1 contract internally) ---")
pt = result[result["partial_tp"] == True]
for ts, row in pt.iterrows():
    print(f"  {ts.strftime('%H:%M')}  close={row['Close']:.0f}")

print("\n--- _calc_pl_from_engine result (what backtest counts) ---")
start_ts = pd.Timestamp("2026-04-24 09:30", tz=_EST)
end_ts   = pd.Timestamp("2026-04-24 17:00", tz=_EST)
tpls = _calc_pl_from_engine(result, start_ts, end_ts)
print(f"  tpls: {[round(x,1) for x in tpls] if tpls else None}")
print(f"  total pts: {sum(tpls):.1f}" if tpls else "  total pts: 0")

print("\n--- algo internal pl column ---")
print(f"  final pl: {result['pl'].iloc[-1]:.1f} pts")
