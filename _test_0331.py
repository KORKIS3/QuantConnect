import pandas as pd, pytz, os
from execution_engine import ExecutionEngine
_EST = pytz.timezone('US/Eastern')
fpath = os.path.expanduser('~/Desktop/2YearsData/full_day/CBOT_MINI_YM1_2026-03-31.csv')
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
day = df[(df.index >= pd.Timestamp('2026-03-31 09:30', tz=_EST)) & (df.index <= pd.Timestamp('2026-03-31 16:59', tz=_EST))]
engine = ExecutionEngine()
result = engine.run_session(day)
print(f"03/31 P/L: {result['session_pl']:+.0f} pts ({len(result['trades'])} trades)")
for t in result['trades']:
    print(f"  {t['direction']:<6} bar {t['entry_bar']}->{t['exit_bar']} "
          f"entry={t['entry_price']:.0f} exit={t['exit_price']:.0f} "
          f"P/L={t['pl']:+.0f} held={t['bars_held']} reason={t['exit_reason']}")
