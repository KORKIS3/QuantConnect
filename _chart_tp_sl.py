"""Interactive chart showing TP/SL strategy in action.
Shows entries, TP hits (+60), SL hits (-50), and signal exits."""
import sys, os
import pandas as pd, pytz, numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.widgets import Slider
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

TP_TOTAL = 60  # +60 pts to take profit (2 contracts)
SL_TOTAL = 50  # -50 pts to stop loss (2 contracts)


def run_chart(target_date):
    fpath = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{target_date}.csv")
    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    ds = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
    de = pd.Timestamp(f'{target_date} 16:59', tz=_EST)
    day = df[(df.index >= ds) & (df.index <= de)]

    config = AlgoConfig(
        warmup_minutes=7, steep_angle_threshold=90.0, proximity_points=4.0,
        min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=50.0,
        wm_shield_distance=0.0, swing_anchor_threshold=10.0,
    )
    algo_df = run_trading_algo_fast(day, target_date, '09:30', '17:00', config=config)

    n = len(algo_df)
    highs = algo_df['High'].values
    lows = algo_df['Low'].values
    closes = algo_df['Close'].values
    opens = algo_df['Open'].values
    sig = algo_df['signal'].values
    times = algo_df.index

    # Simulate TP/SL trades
    trades = []
    pos = 0
    entry_price = 0.0
    entry_bar = -1

    for i in range(n):
        s = str(sig[i]).strip()

        # Check TP/SL on open position
        if pos != 0:
            if pos == 1:  # long
                unrealized_high = (highs[i] - entry_price) * 2
                unrealized_low = (lows[i] - entry_price) * 2
            else:  # short
                unrealized_high = (entry_price - lows[i]) * 2
                unrealized_low = (entry_price - highs[i]) * 2

            # SL hit?
            if unrealized_low <= -SL_TOTAL:
                exit_price = entry_price - (SL_TOTAL / 2) * (1 if pos == 1 else -1)
                trades.append({'entry_bar': entry_bar, 'exit_bar': i, 'entry_price': entry_price,
                               'exit_price': exit_price, 'pl': -SL_TOTAL, 'direction': pos,
                               'exit_type': 'SL'})
                pos = 0; entry_price = 0.0; entry_bar = -1
                continue

            # TP hit?
            if unrealized_high >= TP_TOTAL:
                exit_price = entry_price + (TP_TOTAL / 2) * (1 if pos == 1 else -1)
                trades.append({'entry_bar': entry_bar, 'exit_bar': i, 'entry_price': entry_price,
                               'exit_price': exit_price, 'pl': TP_TOTAL, 'direction': pos,
                               'exit_type': 'TP'})
                pos = 0; entry_price = 0.0; entry_bar = -1
                continue

        # Signal exit (reversal)
        if s == "BUY" and pos == -1:
            pl = (entry_price - closes[i]) * 2
            trades.append({'entry_bar': entry_bar, 'exit_bar': i, 'entry_price': entry_price,
                           'exit_price': closes[i], 'pl': pl, 'direction': pos,
                           'exit_type': 'SIGNAL'})
            pos = 1; entry_price = closes[i]; entry_bar = i
        elif s == "SELL" and pos == 1:
            pl = (closes[i] - entry_price) * 2
            trades.append({'entry_bar': entry_bar, 'exit_bar': i, 'entry_price': entry_price,
                           'exit_price': closes[i], 'pl': pl, 'direction': pos,
                           'exit_type': 'SIGNAL'})
            pos = -1; entry_price = closes[i]; entry_bar = i
        elif s == "BUY" and pos == 0:
            pos = 1; entry_price = closes[i]; entry_bar = i
        elif s == "SELL" and pos == 0:
            pos = -1; entry_price = closes[i]; entry_bar = i

    # Print summary
    session_pl = sum(t['pl'] for t in trades)
    tp_trades = [t for t in trades if t['exit_type'] == 'TP']
    sl_trades = [t for t in trades if t['exit_type'] == 'SL']
    sig_trades = [t for t in trades if t['exit_type'] == 'SIGNAL']
    print(f"\n{target_date} — TP/SL Strategy (TP=+60, SL=-50)")
    print(f"Session P/L: {session_pl:+.0f} pts ({len(trades)} trades)")
    print(f"  TP exits: {len(tp_trades)} ({sum(t['pl'] for t in tp_trades):+.0f})")
    print(f"  SL exits: {len(sl_trades)} ({sum(t['pl'] for t in sl_trades):+.0f})")
    print(f"  Signal exits: {len(sig_trades)} ({sum(t['pl'] for t in sig_trades):+.0f})")
    for i, t in enumerate(trades):
        d = "LONG" if t['direction'] == 1 else "SHORT"
        print(f"  T{i+1}: {d:<6} bar {t['entry_bar']}->{t['exit_bar']} "
              f"entry={t['entry_price']:.0f} exit={t['exit_price']:.0f} "
              f"P/L={t['pl']:+.0f} [{t['exit_type']}]")

    # Chart
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(18, 11), gridspec_kw={'height_ratios': [4, 1]},
                                   sharex=True)
    plt.subplots_adjust(bottom=0.12)
    ax_slider = plt.axes([0.12, 0.04, 0.7, 0.03])
    slider = Slider(ax_slider, 'Bar', 0, n - 1, valinit=n - 1, valstep=1)

    def draw_frame(frame):
        ax.clear()
        ax2.clear()
        frame = int(frame)
        view_start = max(0, frame - 90)

        # Candles
        for i in range(view_start, frame + 1):
            color = '#26a69a' if closes[i] >= opens[i] else '#ef5350'
            ax.plot([i, i], [lows[i], highs[i]], color='#555', linewidth=0.5)
            body_lo = min(opens[i], closes[i])
            body_hi = max(opens[i], closes[i])
            rect = Rectangle((i - 0.35, body_lo), 0.7, max(body_hi - body_lo, 2),
                             facecolor=color, edgecolor='#333', linewidth=0.4)
            ax.add_patch(rect)

        # Draw trades
        for t in trades:
            if t['entry_bar'] > frame:
                continue
            eb = t['entry_bar']
            xb = t['exit_bar'] if t['exit_bar'] <= frame else frame

            # Entry marker
            if view_start <= eb <= frame:
                if t['direction'] == 1:
                    ax.scatter([eb], [t['entry_price']], color='blue', s=150, marker='^', zorder=10)
                else:
                    ax.scatter([eb], [t['entry_price']], color='darkred', s=150, marker='v', zorder=10)

                # Draw TP and SL levels
                tp_level = t['entry_price'] + (TP_TOTAL / 2) * (1 if t['direction'] == 1 else -1)
                sl_level = t['entry_price'] - (SL_TOTAL / 2) * (1 if t['direction'] == 1 else -1)
                end_bar = min(t['exit_bar'], frame)
                ax.plot([eb, end_bar], [tp_level, tp_level], color='green', linewidth=1.5,
                        linestyle='--', alpha=0.7)
                ax.plot([eb, end_bar], [sl_level, sl_level], color='red', linewidth=1.5,
                        linestyle='--', alpha=0.7)

            # Exit marker
            if t['exit_bar'] <= frame and view_start <= t['exit_bar']:
                if t['exit_type'] == 'TP':
                    ax.scatter([t['exit_bar']], [t['exit_price']], color='green', s=200,
                               marker='*', zorder=10, edgecolors='black', linewidths=0.5)
                    ax.annotate(f"TP +{t['pl']:.0f}", xy=(t['exit_bar'], t['exit_price']),
                               xytext=(t['exit_bar']+1, t['exit_price']+10),
                               fontsize=8, color='green', fontweight='bold')
                elif t['exit_type'] == 'SL':
                    ax.scatter([t['exit_bar']], [t['exit_price']], color='red', s=200,
                               marker='X', zorder=10, edgecolors='black', linewidths=0.5)
                    ax.annotate(f"SL {t['pl']:.0f}", xy=(t['exit_bar'], t['exit_price']),
                               xytext=(t['exit_bar']+1, t['exit_price']-10),
                               fontsize=8, color='red', fontweight='bold')
                else:
                    ax.scatter([t['exit_bar']], [t['exit_price']], color='orange', s=100,
                               marker='x', zorder=10, linewidths=2)
                    ax.annotate(f"SIG {t['pl']:+.0f}", xy=(t['exit_bar'], t['exit_price']),
                               xytext=(t['exit_bar']+1, t['exit_price']),
                               fontsize=7, color='orange')

        # P/L subplot
        running_pl = []
        cum = 0
        for i in range(view_start, frame + 1):
            for t in trades:
                if t['exit_bar'] == i:
                    cum += t['pl']
            running_pl.append(cum)

        ax2.fill_between(range(view_start, frame + 1), running_pl, 0,
                         where=[p >= 0 for p in running_pl], color='green', alpha=0.3)
        ax2.fill_between(range(view_start, frame + 1), running_pl, 0,
                         where=[p < 0 for p in running_pl], color='red', alpha=0.3)
        ax2.plot(range(view_start, frame + 1), running_pl, color='black', linewidth=1.5)
        ax2.axhline(0, color='gray', linewidth=0.5, linestyle='--')
        ax2.set_ylabel('Session P/L')

        # Axis
        vis_h = highs[view_start:frame+1]
        vis_l = lows[view_start:frame+1]
        ax.set_xlim(view_start - 1, frame + 3)
        ax.set_ylim(min(vis_l) - 15, max(vis_h) + 15)
        ax.set_title(f"TP/SL Strategy — {target_date} | Bar {frame} ({times[frame].strftime('%H:%M')}) | "
                     f"P/L: {session_pl:+.0f} ({len(trades)} trades: {len(tp_trades)}TP {len(sl_trades)}SL {len(sig_trades)}SIG)",
                     fontsize=11, fontweight='bold')
        ax.set_ylabel('Price')
        ax.grid(True, alpha=0.15)
        tick_step = max(1, (frame - view_start) // 10)
        ticks = list(range(view_start, frame + 1, tick_step))
        ax.set_xticks(ticks)
        ax.set_xticklabels([times[t].strftime('%H:%M') for t in ticks if t < n], rotation=45, fontsize=8)
        fig.canvas.draw_idle()

    slider.on_changed(draw_frame)
    def on_key(event):
        if event.key == 'right': slider.set_val(min(slider.val + 1, n - 1))
        elif event.key == 'left': slider.set_val(max(slider.val - 1, 0))
        elif event.key == 'up': slider.set_val(min(slider.val + 10, n - 1))
        elif event.key == 'down': slider.set_val(max(slider.val - 10, 0))
        elif event.key == 'home': slider.set_val(0)
        elif event.key == 'end': slider.set_val(n - 1)
    fig.canvas.mpl_connect('key_press_event', on_key)
    draw_frame(n - 1)
    plt.show(block=True)


if __name__ == "__main__":
    target_date = sys.argv[1] if len(sys.argv) > 1 else "2026-05-18"
    run_chart(target_date)
