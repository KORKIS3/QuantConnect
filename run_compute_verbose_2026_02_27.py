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
plotter.create_figure()
plotter.update_plot(0)
plotter.detect_all_signals_once()

print('\nSignals:')
print('Buys:')
for t,p in plotter.state.detected_buy_signals.items():
    print(' ', t.strftime('%H:%M:%S'), p)
print('Sells:')
for t,p in plotter.state.detected_sell_signals.items():
    print(' ', t.strftime('%H:%M:%S'), p)

# Reproduce compute logic with verbose prints
buys = {t: p for t, p in plotter.state.detected_buy_signals.items()}
sells = {t: p for t, p in plotter.state.detected_sell_signals.items()}

est = pytz.timezone('US/Eastern')

events = []
for t, p in buys.items():
    events.append((t, 'buy', p))
for t, p in sells.items():
    events.append((t, 'sell', p))
events.sort(key=lambda x: x[0])

print('\nMerged events in order:')
for e in events:
    print(' ', e[0].strftime('%H:%M:%S'), e[1], e[2])

# normalize event times to plotter.data index tz
events_by_time = {}
for t, typ, price in events:
    evt = pd.to_datetime(t)
    if evt.tzinfo is None:
        evt = evt.tz_localize(est)
    else:
        evt = evt.tz_convert(est)
    events_by_time.setdefault(evt, []).append((typ, price))

print('\nProcessing timeline:')
position = 'flat'
entry_price = None
entry_time = None
cumulative_realized_pl = 0.0
max_total_pl = 0.0
captured100 = False
liquidation_p_l = None
trades = []

for ts in plotter.data.index:
    evs = events_by_time.get(ts, [])
    if evs:
        print('\n-- Events at', ts.strftime('%H:%M:%S'))
    for typ, price in evs:
        print('   event', typ, price, 'position before', position)
        if typ == 'buy':
            if position == 'flat':
                position = 'long'
                entry_price = price
                entry_time = ts
                print('    -> enter long', entry_price)
            elif position == 'short':
                pl = entry_price - price
                cumulative_realized_pl += pl
                trades.append({'entry_time': entry_time, 'exit_time': ts, 'pl': pl})
                if abs(pl) >= 100 and liquidation_p_l is None:
                    liquidation_p_l = cumulative_realized_pl
                position = 'long'
                entry_price = price
                entry_time = ts
                print('    -> closed short, pl', pl, 'cum', cumulative_realized_pl, 'enter long', entry_price)
        else:  # sell
            if position == 'flat':
                position = 'short'
                entry_price = price
                entry_time = ts
                print('    -> enter short', entry_price)
            elif position == 'long':
                pl = price - entry_price
                cumulative_realized_pl += pl
                trades.append({'entry_time': entry_time, 'exit_time': ts, 'pl': pl})
                if abs(pl) >= 100 and liquidation_p_l is None:
                    liquidation_p_l = cumulative_realized_pl
                position = 'short'
                entry_price = price
                entry_time = ts
                print('    -> closed long, pl', pl, 'cum', cumulative_realized_pl, 'enter short', entry_price)

    # compute current total P/L (realized + unrealized)
    current_close = float(plotter.data['Close'].loc[ts])
    unrealized = 0.0
    if position == 'long' and entry_price is not None:
        unrealized = current_close - entry_price
    elif position == 'short' and entry_price is not None:
        unrealized = entry_price - current_close
    total_pl = cumulative_realized_pl + unrealized
    if total_pl > max_total_pl:
        max_total_pl = total_pl
    if (not captured100) and total_pl >= 100.0:
        captured100 = True

    print(ts.strftime('%H:%M:%S'), 'pos', position, 'entry', entry_price, 'close', current_close, 'realized', cumulative_realized_pl, 'unrealized', unrealized, 'total', total_pl)

# finalize
if position != 'flat' and entry_price is not None:
    last_price = float(plotter.data['Close'].iloc[-1])
    if position == 'long':
        pl = last_price - entry_price
    else:
        pl = entry_price - last_price
    cumulative_realized_pl += pl
    trades.append({'entry_time': entry_time, 'exit_time': plotter.data.index[-1], 'pl': pl})
    if abs(pl) >= 100 and liquidation_p_l is None:
        liquidation_p_l = cumulative_realized_pl

print('\nFinal cumulative realized pl:', cumulative_realized_pl)
print('Max total pl:', max_total_pl)
print('Captured100:', captured100)
print('Liquidation recorded pl:', liquidation_p_l)
print('\nTrades:')
for tr in trades:
    print(' ', tr)
