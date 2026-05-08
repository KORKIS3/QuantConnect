"""_ib_log_monitor.py -- Fred's performance only (clientId=1 fills)."""
import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())

import os, re
import pandas as pd
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from datetime import date
import pytz

_EST_LOG_DIR  = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "logs")
_REFRESH_MS   = 30_000   # 30 seconds — non-blocking timer
_EST          = pytz.timezone("US/Eastern")


def _today():
    return date.today().strftime("%Y%m%d")


def _parse_fred_fills(log_path):
    if not os.path.exists(log_path):
        return pd.DataFrame()
    text = open(log_path, encoding="utf-8", errors="ignore").read()
    # Match execId, actual fill time (UTC inside the Execution object), side, qty, price
    pattern = r"execDetails Execution\(execId='([^']+)'.*?time=datetime\.datetime\((\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+).*?tzinfo=datetime\.timezone\.utc\).*?side='(BOT|SLD)', shares=([\d.]+), price=([\d.]+)"
    rows = {}
    # Only count fills from today's session start (9:30 AM ET) onwards
    today_session_start = pd.Timestamp(date.today().strftime("%Y-%m-%d") + " 09:30:00", tz=_EST)
    for m in re.finditer(pattern, text, re.DOTALL):
        eid = m.group(1)
        if eid in rows:
            continue
        side = "BUY" if m.group(8) == "BOT" else "SELL"
        try:
            # Reconstruct actual fill time from UTC components inside Execution object
            fill_utc = pd.Timestamp(
                year=int(m.group(2)), month=int(m.group(3)), day=int(m.group(4)),
                hour=int(m.group(5)), minute=int(m.group(6)), second=int(m.group(7)),
                tz="UTC"
            )
            ts = fill_utc.tz_convert(_EST)
        except Exception:
            continue
        if ts < today_session_start:
            continue  # skip fills from before today's session
        rows[eid] = {"ts": ts, "time": ts.strftime("%I:%M %p"),
                     "side": side, "qty": float(m.group(9)), "price": float(m.group(10))}
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows.values()).sort_values("ts").reset_index(drop=True)


def _calc_pl(fills):
    pos, ep, realized = 0.0, 0.0, 0.0
    trade_pls = []
    fill_list = list(fills.iterrows())
    exit_prices = [None] * len(fill_list)
    for idx, (_, r) in enumerate(fill_list):
        qty, price = r["qty"], r["price"]
        trade_realized = 0.0
        if r["side"] == "BUY":
            if pos < 0:
                cq = min(qty, abs(pos))
                trade_realized += (ep - price) * cq
                realized += trade_realized
                remaining = cq
                for j in range(idx - 1, -1, -1):
                    if exit_prices[j] is None and fill_list[j][1]["side"] == "SELL":
                        exit_prices[j] = price
                        remaining -= fill_list[j][1]["qty"]
                        if remaining <= 0: break
                pos += cq; qty -= cq
            if qty > 0:
                ep = (ep * pos + price * qty) / (pos + qty) if pos + qty > 0 else price
                pos += qty
        else:
            if pos > 0:
                cq = min(qty, pos)
                trade_realized += (price - ep) * cq
                realized += trade_realized
                remaining = cq
                for j in range(idx - 1, -1, -1):
                    if exit_prices[j] is None and fill_list[j][1]["side"] == "BUY":
                        exit_prices[j] = price
                        remaining -= fill_list[j][1]["qty"]
                        if remaining <= 0: break
                pos -= cq; qty -= cq
            if qty > 0:
                ep = (ep * abs(pos) + price * qty) / (abs(pos) + qty) if abs(pos) + qty > 0 else price
                pos -= qty
        trade_pls.append((trade_realized, realized, exit_prices[idx]))
    return realized, pos, ep, trade_pls


def _latest_mym_price(log_path):
    if not os.path.exists(log_path):
        return 0.0
    text = open(log_path, encoding="utf-8", errors="ignore").read()
    matches = re.findall(r"symbol='MYM'.*?marketPrice=([\d.]+)", text, re.DOTALL)
    return float(matches[-1]) if matches else 0.0


def _latest_ib_position(log_path):
    """Read the most recent confirmed IB position from updatePortfolio entries."""
    if not os.path.exists(log_path):
        return 0.0, 0.0
    text = open(log_path, encoding="utf-8", errors="ignore").read()
    pos_matches = re.findall(
        r"updatePortfolio:.*?symbol='MYM'.*?position=([-\d.]+).*?averageCost=([\d.]+)",
        text, re.DOTALL)
    if pos_matches:
        return float(pos_matches[-1][0]), float(pos_matches[-1][1])
    return 0.0, 0.0


def _draw(fig, day_override=None):
    """Clear and redraw the figure in-place."""
    fig.clf()

    today_key = day_override if day_override else _today()
    today_str = f"{today_key[:4]}-{today_key[4:6]}-{today_key[6:]}"
    # Find the most recent log file for today (handles timestamped filenames)
    import glob as _glob
    # Merge ALL log files for today — Fred restarts create new files, manual orders
    # may appear in different sessions. Reading all of them gives the full picture.
    all_logs = sorted(_glob.glob(os.path.join(_EST_LOG_DIR, f"fred_ib_{today_key}*.log")))
    log_path = all_logs[-1] if all_logs else os.path.join(_EST_LOG_DIR, f"fred_ib_{today_key}.log")

    # Merge text from all today's logs for fills and position parsing
    merged_text_path = log_path  # fallback for single-file functions
    if len(all_logs) > 1:
        merged_text = "\n".join(
            open(p, encoding="utf-8", errors="ignore").read() for p in all_logs
        )
        import tempfile
        _tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, encoding="utf-8")
        _tmp.write(merged_text)
        _tmp.close()
        merged_text_path = _tmp.name

    fills   = _parse_fred_fills(merged_text_path)
    last_px = _latest_mym_price(merged_text_path)
    ib_pos, ib_avg_cost = _latest_ib_position(merged_text_path)

    if len(all_logs) > 1:
        try:
            os.unlink(merged_text_path)
        except Exception:
            pass

    realized_pts, open_pos, open_ep, trade_pls = 0.0, 0.0, 0.0, []
    if not fills.empty:
        realized_pts, open_pos, open_ep, trade_pls = _calc_pl(fills)

    # Use real IB position for unrealized P/L — catches manual trades too
    display_pos = ib_pos if ib_pos != 0 else open_pos
    display_ep  = ib_avg_cost * 2 if ib_pos != 0 else open_ep  # avgCost is per-contract in IB

    if display_pos > 0 and display_ep > 0 and last_px > 0:
        unreal_pts = (last_px - display_ep) * abs(display_pos)
    elif display_pos < 0 and display_ep > 0 and last_px > 0:
        unreal_pts = (display_ep - last_px) * abs(display_pos)
    else:
        unreal_pts = 0.0

    total_pts = realized_pts + unreal_pts

    # --- dynamic figure height based on number of rows ---
    n_rows    = len(fills) if not fills.empty else 0
    tbl_height = max(2.0, n_rows * 0.35 + 1.0)
    fig_h      = 7.0 + tbl_height
    fig.set_size_inches(14, fig_h)

    tbl_ratio = max(1, round(tbl_height * 3))
    gs = fig.add_gridspec(3, 1, height_ratios=[5, 1, tbl_ratio],
                          hspace=0.45, left=0.07, right=0.97, top=0.93, bottom=0.08)
    ax1    = fig.add_subplot(gs[0])   # price chart — pan/zoom enabled
    ax2    = fig.add_subplot(gs[1])   # summary bar
    ax_tbl = fig.add_subplot(gs[2])   # fills table

    # --- title ---
    fig.suptitle(f"Fred IB Monitor — {today_str}  (auto-refresh {_REFRESH_MS//1000}s)",
                 fontsize=13, fontweight="bold", y=0.99)

    # --- price chart ---
    ax1.set_title("MYM  ▲ BUY (green)  ▼ SELL (red)  ◆ TP (orange)  — Fred fills", fontsize=10)
    ax1.set_ylabel("Price")

    if not fills.empty:
        times  = list(fills["ts"])
        prices = list(fills["price"])
        if open_pos != 0 and last_px > 0:
            times.append(pd.Timestamp.now(tz=_EST))
            prices.append(last_px)
        ax1.plot(times, prices, color="steelblue", linewidth=1.5, alpha=0.4)
        for _, row in fills.iterrows():
            is_tp  = (row["side"] == "SELL" and row["qty"] < 2) or (row["side"] == "BUY" and row["qty"] < 2)
            color  = "orange" if is_tp else ("green" if row["side"] == "BUY" else "red")
            marker = "^" if row["side"] == "BUY" else "v"
            label  = f"TP {int(row['qty'])}@{row['price']:.0f}" if is_tp else f"{row['side']} {int(row['qty'])}@{row['price']:.0f}"
            ax1.scatter(row["ts"], row["price"], marker=marker, color=color,
                        s=200, zorder=5, edgecolors="black", linewidths=0.8)
            ax1.annotate(label,
                         xy=(row["ts"], row["price"]),
                         xytext=(0, 14 if row["side"] == "BUY" else -20),
                         textcoords="offset points",
                         fontsize=8, ha="center", color=color, fontweight="bold")
        if open_pos != 0 and last_px > 0:
            ax1.axhline(last_px, color="gray", linewidth=0.8, linestyle="--", alpha=0.6)
            ax1.annotate(f"Now: {last_px:.0f}", xy=(times[-1], last_px),
                         xytext=(-55, 6), textcoords="offset points", fontsize=8, color="gray")
    else:
        ax1.text(0.5, 0.5, "No fills yet", ha="center", va="center",
                 fontsize=14, color="gray", transform=ax1.transAxes)

    ax1.tick_params(axis="x", rotation=25, labelsize=8)
    ax1.grid(axis="y", alpha=0.25)

    # --- summary bar ---
    ax2.axis("off")
    pos_str = f"{open_pos:+.0f} MYM @ {open_ep:.0f}" if open_pos != 0 else "FLAT"
    color   = "green" if total_pts >= 0 else "red"
    summary = (f"Position: {pos_str}     "
               f"Realized: {realized_pts:+.1f} pts (${realized_pts:+.2f})     "
               f"Unrealized: {unreal_pts:+.1f} pts (${unreal_pts:+.2f})     "
               f"TOTAL: {total_pts:+.1f} pts  /  ${total_pts:+.2f}")
    ax2.text(0.5, 0.5, summary, ha="center", va="center", fontsize=10,
             fontfamily="monospace", color=color, fontweight="bold",
             transform=ax2.transAxes,
             bbox=dict(boxstyle="round,pad=0.4", facecolor="#f0f0f0",
                       edgecolor=color, linewidth=2))

    # --- fills table (scrolls with figure) ---
    ax_tbl.axis("off")
    if not fills.empty:
        tbl_data = []
        for i, (_, r) in enumerate(fills.iterrows()):
            chg, cum, exit_px = trade_pls[i] if i < len(trade_pls) else (0.0, 0.0, None)
            chg_str  = f"{chg:+.1f}" if chg != 0.0 else "-"
            cum_str  = f"{cum:+.1f}"
            exit_str = f"{exit_px:.0f}" if exit_px is not None else "open"
            tbl_data.append([r["time"], r["side"], int(r["qty"]), f"{r['price']:.0f}", exit_str, chg_str, cum_str])
        tbl = ax_tbl.table(cellText=tbl_data,
                           colLabels=["Time ET", "Side", "Qty", "Entry", "Exit", "Trade P/L", "Total P/L"],
                           loc="center", cellLoc="center")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(9)
        tbl.scale(1, 1.4)
        for (r, c), cell in tbl.get_celld().items():
            if r == 0:
                cell.set_facecolor("#4472C4")
                cell.set_text_props(color="white", fontweight="bold")
            elif tbl_data[r-1][1] == "BUY":
                cell.set_facecolor("#E2EFDA")
            else:
                cell.set_facecolor("#FCE4D6")

    fig.canvas.draw_idle()


def main(day_override=None):
    fig = plt.figure(figsize=(14, 8))
    _draw(fig, day_override)
    plt.show(block=False)

    # Non-blocking timer — keeps the GUI responsive
    def _refresh(_):
        _draw(fig, day_override)
        fig.canvas.draw_idle()

    timer = fig.canvas.new_timer(interval=_REFRESH_MS)
    timer.add_callback(_refresh, None)
    timer.start()

    print(f"Fred IB Monitor running — refreshes every {_REFRESH_MS//1000}s. Close window to stop.")
    plt.show(block=True)


if __name__ == "__main__":
    import sys
    day_override = sys.argv[1].replace("-", "") if len(sys.argv) > 1 else None
    main(day_override)
