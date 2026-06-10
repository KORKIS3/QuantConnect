"""Quick check: compare today's CSV with IB log reality."""
import pandas as pd

csv_path = r'C:\Users\Administrator\Desktop\IB_Live\tracking\YM_tracking_DUO158495_2026-06-04_0930.csv'
df = pd.read_csv(csv_path, index_col=0, parse_dates=True)

print("=== CSV State ===")
print(f"Rows: {len(df)}")
print(f"Last timestamp: {df.index[-1]}")
print(f"Final position (algo): {df['position'].iloc[-1]}")
print(f"Final pl (algo): {df['pl'].iloc[-1]}")
print(f"Final session_pl (algo): {df['session_pl'].iloc[-1]}")

if 'ib_position' in df.columns:
    print(f"Final ib_position: {df['ib_position'].iloc[-1]}")
    print(f"Final ib_pl: {df['ib_pl'].iloc[-1]}")

if 'order_status' in df.columns:
    filled = df[df['order_status'] == 'filled']
    expired = df[df['order_status'] == 'expired']
    pending = df[df['order_status'] == 'pending']
    print(f"\nFilled events: {len(filled)}")
    for ts, row in filled.iterrows():
        print(f"  {ts}  {row['signal']}  fill_price={row.get('fill_price','')}")
    print(f"Expired events: {len(expired)}")
    print(f"Pending events: {len(pending)}")

print("\n=== IB Reality (from logs) ===")
print("BUY 2 @ 51502 (10:13)")
print("SELL 2 @ 51547 (10:24) — bracket TP")
print("Net: +45 pts realized")
print(f"\nCSV ib_pl matches IB? {df['ib_pl'].iloc[-1] == 45.0 if 'ib_pl' in df.columns else 'NO ib_pl column'}")
