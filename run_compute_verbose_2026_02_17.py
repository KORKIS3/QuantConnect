import os
import pandas as pd
from RunFullDataSet import _load_csv_as_df
from plotFigure import ChartPlotter


def pretty_print_trades(trades):
    for i, t in enumerate(trades, 1):
        print(f"Trade {i}: entry={t['entry_time']} exit={t['exit_time']} pl={t['pl']}")


if __name__ == '__main__':
    desktop = os.path.join(os.path.expanduser('~'), 'Desktop', 'FebData')
    fname = 'feb 17 - now I want 30 minutes of data 9_30 to 10_00 am by....csv'
    fp = os.path.join(desktop, fname)
    print('Loading', fp)

    df = _load_csv_as_df(fp)
    print('Dataframe shape:', df.shape)
    print('Columns:', df.columns.tolist())
    print(df.head(10))

    # build plotter and detect signals
    target_date = '2026-02-17'
    plotter = ChartPlotter(df, target_date, '09:30', '10:00', os.path.join(os.path.expanduser('~'), 'Desktop', 'Trading', 'Temp'))
    try:
        plotter.create_figure()
    except Exception:
        pass
    plotter.detect_all_signals_once()

    # Re-run the trade computation with verbose output (copied logic from RunFullDataSet._compute_trade_stats)
    buys = {t: p for t, p in plotter.state.detected_buy_signals.items()}
    sells = {t: p for t, p in plotter.state.detected_sell_signals.items()}

    events = []
    for t, p in buys.items():
        events.append((t, 'buy', p))
    for t, p in sells.items():
        events.append((t, 'sell', p))
    events.sort(key=lambda x: x[0])

    print('\nDetected events:')
    for e in events:
        print(e)

    import pytz
    est = pytz.timezone('US/Eastern')

    events_by_time = {}
    for t, typ, price in events:
        try:
            evt = pd.to_datetime(t)
            if evt.tzinfo is None:
                evt = evt.tz_localize(est)
            else:
                evt = evt.tz_convert(est)
        except Exception:
            evt = pd.to_datetime(t)
        events_by_time.setdefault(evt, []).append((typ, price))

    trades = []
    position = 'flat'
    entry_price = None
    entry_time = None

    cumulative_realized_pl = 0.0
    max_total_pl = 0.0
    captured100 = False
    liquidation_p_l = None
    liquidation_trade_pl = None

    print('\nIterating timeline:')
    for ts in plotter.data.index:
        evs = events_by_time.get(ts, [])
        if evs:
            print('\nAt', ts, 'events=', evs)
        for typ, price in evs:
            print('  processing', typ, price, 'position was', position)
            if typ == 'buy':
                if position == 'flat':
                    position = 'long'
                    entry_price = price
                    entry_time = ts
                    print('   -> opened long at', price)
                elif position == 'short':
                    pl = entry_price - price
                    cumulative_realized_pl += pl
                    trades.append({'entry_time': entry_time, 'exit_time': ts, 'pl': pl})
                    print('   -> closed short at', price, 'pl=', pl, 'cum_pl=', cumulative_realized_pl)
                    if pl >= 100 and liquidation_p_l is None:
                        liquidation_p_l = cumulative_realized_pl
                        liquidation_trade_pl = float(pl)
                        print('   !! Liquidation recorded: trade pl=', liquidation_trade_pl, 'cumulative at liquidation=', liquidation_p_l)
                    position = 'long'
                    entry_price = price
                    entry_time = ts
            else:  # sell
                if position == 'flat':
                    position = 'short'
                    entry_price = price
                    entry_time = ts
                    print('   -> opened short at', price)
                elif position == 'long':
                    pl = price - entry_price
                    cumulative_realized_pl += pl
                    trades.append({'entry_time': entry_time, 'exit_time': ts, 'pl': pl})
                    print('   -> closed long at', price, 'pl=', pl, 'cum_pl=', cumulative_realized_pl)
                    if pl >= 100 and liquidation_p_l is None:
                        liquidation_p_l = cumulative_realized_pl
                        liquidation_trade_pl = float(pl)
                        print('   !! Liquidation recorded: trade pl=', liquidation_trade_pl, 'cumulative at liquidation=', liquidation_p_l)
                    position = 'short'
                    entry_price = price
                    entry_time = ts

        # compute current total P/L
        try:
            current_close = float(plotter.data['Close'].loc[ts])
        except Exception:
            current_close = float(plotter.data['Close'].iloc[-1])

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

    # close final position
    if position != 'flat' and entry_price is not None:
        last_price = float(plotter.data['Close'].iloc[-1])
        if position == 'long':
            pl = last_price - entry_price
        else:
            pl = entry_price - last_price
        cumulative_realized_pl += pl
        trades.append({'entry_time': entry_time, 'exit_time': plotter.data.index[-1], 'pl': pl})
        print('\nFinal close at', plotter.data.index[-1], 'price=', last_price, 'pl=', pl, 'cum_pl=', cumulative_realized_pl)
        if pl >= 100 and liquidation_p_l is None:
            liquidation_p_l = cumulative_realized_pl
            liquidation_trade_pl = float(pl)
            print('   !! Liquidation recorded at final close: trade pl=', liquidation_trade_pl, 'cumulative=', liquidation_p_l)

    print('\nTrades summary:')
    pretty_print_trades(trades)
    print('\ncumulative_realized_pl=', cumulative_realized_pl)
    print('max_total_pl=', max_total_pl)
    print('captured100 (total-based)=', captured100)
    print('captured_by_trade=', any(t['pl'] >= 100 for t in trades))
    print('captured_flag=', captured100 or any(t['pl'] >= 100 for t in trades))
    print('liquidation_pl (cumulative at first big trade)=', liquidation_p_l)
    print('liquidation_trade_pl (single trade pl)=', liquidation_trade_pl)
