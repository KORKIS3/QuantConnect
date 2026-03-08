import os
import pandas as pd
from RunFullDataSet import _load_csv_as_df
from TradingAlgo import run_trading_algo
csv_path = os.path.join(os.path.expanduser('~'), 'Desktop', 'CBOT_MINI_YM1_ByDate_930_1000', 'CBOT_MINI_YM1_2026-02-04.csv')
data = _load_csv_as_df(csv_path)
result = run_trading_algo(data, '2026-02-04')
signals = result[result['signal'].isin(['BUY', 'SELL'])]
print(signals[['Close', 'signal', 'buy_price', 'sell_price', 'position', 'pl']].to_string())
