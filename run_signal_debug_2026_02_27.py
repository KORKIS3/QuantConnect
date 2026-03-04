import pandas as pd
import pytz
from plotFigure import ChartPlotter

fp = 'YM_intraday_2026-02-27_0930-1000.csv'
print('Loading:', fp)
df = pd.read_csv(fp, index_col=0, parse_dates=True)
est = pytz.timezone('US/Eastern')
if df.index.tz is None:
    df.index = df.index.tz_localize(est)
else:
    df.index = df.index.tz_convert(est)

plotter = ChartPlotter(df, '2026-02-27', '09:30', '10:00', '/tmp')
# create figure/axes so get_aspect_ratio can run
plotter.create_figure()
plotter.update_plot(0)
plotter.detect_all_signals_once()
print('\nDetected BUY signals:')
for t, p in plotter.state.detected_buy_signals.items():
    print(t.strftime('%H:%M:%S'), p)
print('\nDetected SELL signals:')
for t, p in plotter.state.detected_sell_signals.items():
    print(t.strftime('%H:%M:%S'), p)
