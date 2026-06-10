"""Patch InteractiveBrokers.py: replace shift-based P/L guard with recomputation."""

lines = open('InteractiveBrokers.py').readlines()

new_block = [
    '                # Recompute post-guard P/L from scratch (starts at 0, ignores pre-guard entries)\n',
    '                post_guard = ~guard_mask\n',
    '                if post_guard.any():\n',
    '                    _pos = 0  # 0=flat, 1=long, -1=short\n',
    '                    _entry_p = 0.0\n',
    '                    _realized = 0.0\n',
    '                    _new_pl = []\n',
    '                    for _idx in algo_df.loc[post_guard].index:\n',
    '                        _sig = str(algo_df.at[_idx, "signal"]).strip()\n',
    '                        _close = float(algo_df.at[_idx, "Close"])\n',
    '                        if _sig == "BUY":\n',
    '                            if _pos == -1 and _entry_p > 0:\n',
    '                                _realized += (_entry_p - _close) * 2\n',
    '                            _pos = 1\n',
    '                            _entry_p = _close\n',
    '                        elif _sig == "SELL":\n',
    '                            if _pos == 1 and _entry_p > 0:\n',
    '                                _realized += (_close - _entry_p) * 2\n',
    '                            _pos = -1\n',
    '                            _entry_p = _close\n',
    '                        _unrealized = 0.0\n',
    '                        if _pos == 1 and _entry_p > 0:\n',
    '                            _unrealized = (_close - _entry_p) * 2\n',
    '                        elif _pos == -1 and _entry_p > 0:\n',
    '                            _unrealized = (_entry_p - _close) * 2\n',
    '                        _new_pl.append(_realized + _unrealized)\n',
    '                    algo_df.loc[post_guard, "session_pl"] = _new_pl\n',
    '                    algo_df.loc[post_guard, "pl"] = _new_pl\n',
]

# Replace lines 1140-1145 (indices 1139-1144)
result = lines[:1139] + new_block + lines[1145:]
open('InteractiveBrokers.py', 'w').writelines(result)
print(f"Done - replaced 6 lines with {len(new_block)} lines")
