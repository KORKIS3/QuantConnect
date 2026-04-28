"""_ib_log_monitor.py -- Fred's performance only (clientId=1 fills)."""
import os, re, time
import pandas as pd
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from datetime import date
import pytz

_EST_LOG_DIR  = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "logs")
_REFRESH_SECS = 60
_EST          = pytz.timezone("US/Eastern")
_MYM_MULT     = 0.5   # $0.50/pt per contract


def _today():
    return date.today().strftime("%Y%m%d")


def _parse_fred_fills(log_path):
    """Only Fred's fills (clientId=1), deduplicated by execId."""
    if not os.path.exists(log_path):
        return pd.DataFrame()
    text = open(log_path, encoding="utf-8", errors="ignore").read()
    pattern = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?execDetails Execution\(execId='([^']+)'.*?side='(BOT|SLD)', shares=([\d.]+), price=([\d.]+).*?clientId=1,"
    rows = {}
    for m in re.finditer(pattern, text):
        eid = m.group(2)
        if eid in rows:
            continue
        side = "BUY" if m.group(3) == "BOT" else "SELL"
        try:
            ts = pd.Timestamp(m.group(1), tz=_EST)
        except:
            continue
        rows[eid] = {"ts": ts, "time": ts.strftime("%I:%M %p"),
                     "side": side, "qty": float(m.group(4)), "price": float(m.group(5))}
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows.values()).sort_values("ts").reset_index(drop=True)


def _calc_pl(fills):
    """Replay fills -> realized pts, open_pos, avg_entry."""
    pos, ep, realized = 0.0, 0.0, 0.0
    for _, r in fills.iterrows():
        qty, price = r["qty"], r["price"]
        if r["side"] == "BUY":
            if pos < 0:
                cq = min(qty, abs(pos))
                realized += (ep - price) * cq
                pos += cq; qty -= cq
            if qty > 0:
                ep = (ep * pos + price * qty) / (pos + qty) if pos + qty > 0 else price
                pos += qty
        else:
            if pos > 0:
                cq = min(qty, pos)
                realized += (price - ep) * cq
                pos -= cq; qty -= cq
            if qty > 0:
                ep = (ep * abs(pos) + price * qty) / (abs(pos) + qty) if abs(pos) + qty > 0 else price
                pos -= qty
    return realized, pos, ep


def _latest_mym_price(log_path):
    if not os.path.exists(log_path):
        return 0.0
    text = open(log_path, encoding="utf-8", errors="ignore").read()
    matches = re.findall(r"symbol='MYM'.*?marketPrice=([\d.]+)", text, re.DOTALL)
    return float(matches[-1]) if matches else 0.0


def _build():
    today_str = date.today().strftime("%Y-%m-%d")
    log_path  = os.path.join(_EST_LOG_DIR, f"fred_ib_{_today()}.log")

    fills = _parse_fred_fills(log_path)
    last_px = _latest_mym_price(log_path)

    realized_pts, open_pos, open_ep = (0.0, 0.0, 0.0)
    if not fills.empty:
        realized_pts, open_pos, open_ep = _calc_pl(fills)

    # Unrealized on open position
    if open_pos > 0 and open_ep > 0 and last_px > 0:
        unreal_pts = (last_px - open_ep) * abs(open_pos)
    elif open_pos < 0 and open_ep > 0 and last_px > 0:
        unreal_pts = (open_ep - last_px) * abs(open_pos)
    else:
        unreal_pts = 0.0

    total_pts  = realized_pts + unreal_pts
    # 2 contracts × $0.50/pt = $1/pt → pts == dollars
    real_cash   = realized_pts
    unreal_cash = unreal_pts
    total_cash  = total_pts

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7),
                                   gridspec_kw={"height_ratios": [3, 1]})
    fig.subplots_adjust(left=0.08, right=0.97, top=0.92, bottom=0.28)
    fig.suptitle(f"Fred IB Monitor — {today_str}  (refreshes every {_REFRESH_SECS}s)",
                 fontsize=13, fontweight="bold")

    ax1.set_title("MYM Price  |  ▲ BUY  ▼ SELL  (Fred's orders only)", fontsize=11)
    ax1.set_ylabel("Price")

    if not fills.empty:
        times  = list(fills["ts"])
        prices = list(fills["price"])
        if open_pos != 0 and last_px > 0:
            times.append(pd.Timestamp.now(tz=_EST))
            prices.append(last_px)
        ax1.plot(times, prices, color="steelblue", linewidth=1.5, alpha=0.5)
        for _, row in fills.iterrows():
            color  = "green" if row["side"] == "BUY" else "red"
            marker = "^"     if row["side"] == "BUY" else "v"
            ax1.scatter(row["ts"], row["price"], marker=marker, color=color,
                        s=200, zorder=5, edgecolors="black", linewidths=0.8)
            ax1.annotate(f"{row['side']} {int(row['qty'])}@{row['price']:.0f}",
                         xy=(row["ts"], row["price"]),
                         xytext=(0, 14 if row["side"] == "BUY" else -18),
                         textcoords="offset points",
                         fontsize=9, ha="center", color=color, fontweight="bold")
        if open_pos != 0 and last_px > 0:
            ax1.axhline(last_px, color="gray", linewidth=0.8, linestyle="--", alpha=0.7)
            ax1.annotate(f"Now: {last_px:.0f}", xy=(times[-1], last_px),
                         xytext=(-60, 6), textcoords="offset points", fontsize=8, color="gray")
    else:
        ax1.text(0.5, 0.5, "No fills yet", ha="center", va="center",
                 fontsize=14, color="gray", transform=ax1.transAxes)

    ax1.tick_params(axis="x", rotation=20, labelsize=8)
    ax1.grid(axis="y", alpha=0.3)

    ax2.axis("off")
    pos_str = f"{open_pos:+.0f} MYM @ {open_ep:.0f}" if open_pos != 0 else "FLAT"
    color   = "green" if total_cash >= 0 else "red"
    summary = (
        f"  Position: {pos_str}     "
        f"Realized: {realized_pts:+.1f} pts (${real_cash:+.2f})     "
        f"Unrealized: {unreal_pts:+.1f} pts (${unreal_cash:+.2f})     "
        f"TOTAL: {total_pts:+.1f} pts  /  ${total_cash:+.2f}"
    )
    ax2.text(0.5, 0.7, summary, ha="center", va="center", fontsize=11,
             fontfamily="monospace", color=color, fontweight="bold",
             transform=ax2.transAxes,
             bbox=dict(boxstyle="round,pad=0.4", facecolor="#f0f0f0",
                       edgecolor=color, linewidth=2))

    if not fills.empty:
        tbl_data = [[r["time"], r["side"], int(r["qty"]), f"{r['price']:.0f}"]
                    for _, r in fills.iterrows()]
        tbl = ax2.table(cellText=tbl_data,
                        colLabels=["Time ET", "Side", "Qty", "Price"],
                        loc="bottom", cellLoc="center", bbox=[0.1, -1.3, 0.8, 1.0])
        tbl.auto_set_font_size(False); tbl.set_fontsize(9); tbl.scale(1, 1.3)
        for (r, c), cell in tbl.get_celld().items():
            if r == 0:
                cell.set_facecolor("#4472C4")
                cell.set_text_props(color="white", fontweight="bold")
            elif tbl_data[r-1][1] == "BUY":
                cell.set_facecolor("#E2EFDA")
            else:
                cell.set_facecolor("#FCE4D6")

    return fig


def main():
    plt.ion()
    fig = None
    print(f"Fred IB Monitor — refreshing every {_REFRESH_SECS}s. Ctrl+C to stop.")
    while True:
        try:
            if fig is not None:
                plt.close(fig)
            fig = _build()
            plt.pause(0.1)
            time.sleep(_REFRESH_SECS)
        except KeyboardInterrupt:
            print("Stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(_REFRESH_SECS)


if __name__ == "__main__":
    main()
