import pandas as pd

df = pd.read_csv(r'C:\Users\Administrator\Desktop\IB_Live\tracking\YM_tracking_2026-05-08.csv')

print(f'Total bars: {len(df)}')
print(f'Final P/L: {df["session_pl"].iloc[-1]:.1f} pts')
print(f'Position: {df["position"].iloc[-1]}')
