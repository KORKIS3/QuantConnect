"""Patch InteractiveBrokers.py to add signal guard to algo view chart."""
import re

with open('InteractiveBrokers.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '        # Chart 1 shows PURE algo signals/P&L \u2014 no IB override.\n        # Chart 2 (IB View) shows actual IB fills via _build_ib_view_df.\n\n        if self._live_chart is None:'

new = """        # Chart 1: pure algo signals/P&L from connection time forward only.
        # Zero out everything before signal guard so chart starts at 0.
        # Chart 2 (IB View) shows actual IB fills via _build_ib_view_df.
        if self._last_signal_ts is not None and not algo_df.empty:
            guard_mask = algo_df.index < self._last_signal_ts
            if guard_mask.any():
                algo_df.loc[guard_mask, "signal"] = ""
                algo_df.loc[guard_mask, "buy_price"] = pd.NA
                algo_df.loc[guard_mask, "sell_price"] = pd.NA
                algo_df.loc[guard_mask, "position"] = "flat"
                algo_df.loc[guard_mask, "pl"] = 0.0
                algo_df.loc[guard_mask, "session_pl"] = 0.0
                if "partial_tp" in algo_df.columns:
                    algo_df.loc[guard_mask, "partial_tp"] = False
                if "is_spike_exit" in algo_df.columns:
                    algo_df.loc[guard_mask, "is_spike_exit"] = False
                # Shift post-guard P/L so it starts at 0
                post_guard = ~guard_mask
                if post_guard.any():
                    first_post_pl = algo_df.loc[post_guard, "session_pl"].iloc[0]
                    algo_df.loc[post_guard, "session_pl"] -= first_post_pl
                    algo_df.loc[post_guard, "pl"] -= first_post_pl

        if self._live_chart is None:"""

if old in content:
    content = content.replace(old, new)
    with open('InteractiveBrokers.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("PATCHED OK")
else:
    print("OLD STRING NOT FOUND")
    # Debug: show what's around line 1124
    lines = content.split('\n')
    for i in range(1122, 1128):
        print(f"  {i+1}: {repr(lines[i])}")
