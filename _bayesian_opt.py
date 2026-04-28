"""Bayesian optimization of AlgoConfig parameters using Optuna."""
import os, pytz, pandas as pd, optuna
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

optuna.logging.set_verbosity(optuna.logging.WARNING)

LOG_FILE = "_bayesian_results.txt"
CSV_FILE = "_bayesian_trials.csv"
HOURS    = ["10:00","11:00","12:00","13:00","14:00","15:00","16:00","17:00"]

def log(msg):
    print(msg, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
_CSV_FILES = sorted([f for f in os.listdir(_DATA_ROOT)
                     if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])

log("Loading data...")
_DAYS = []
for fname in _CSV_FILES:
    date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    df = pd.read_csv(os.path.join(_DATA_ROOT, fname), index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    day = df[(df.index >= pd.Timestamp(date + " 09:30", tz=_EST)) &
             (df.index <= pd.Timestamp(date + " 16:59", tz=_EST))]
    if len(day) >= 15:
        _DAYS.append((date, day))
log(f"Loaded {len(_DAYS)} days.")


def objective(trial):
    cfg = AlgoConfig(
        warmup_minutes        = trial.suggest_int("warmup_minutes", 5, 12),
        steep_angle_threshold = trial.suggest_float("steep_angle_threshold", 60.0, 90.0, step=2.5),
        proximity_points      = trial.suggest_float("proximity_points", 2.0, 15.0, step=1.0),
        min_reversal_minutes  = 0,
        min_entry_angle       = trial.suggest_float("min_entry_angle", 0.0, 40.0, step=5.0),
        partial_tp_pts        = trial.suggest_float("partial_tp_pts", 25.0, 150.0, step=25.0),
        wm_shield_distance    = trial.suggest_float("wm_shield_distance", 0.0, 20.0, step=2.0),
        swing_anchor_threshold= trial.suggest_float("swing_anchor_threshold", 5.0, 50.0, step=5.0),
        spike_profit_pts      = trial.suggest_float("spike_profit_pts", 50.0, 200.0, step=25.0),
        spike_profit_bars     = trial.suggest_int("spike_profit_bars", 2, 10),
    )

    total_pl = 0.0; wins = 0; loses = 0; days = 0
    hour_pl   = {h: 0.0 for h in HOURS}
    hour_days = {h: 0   for h in HOURS}

    for date, day in _DAYS:
        try:
            result = run_trading_algo_fast(day, date, "09:30", "17:00", config=cfg)
            pl = float(result["session_pl"].iloc[-1])
            total_pl += pl; days += 1
            if pl > 0: wins += 1
            else: loses += 1
            # Sample P/L at each hour cutoff
            for h in HOURS:
                end_ts = pd.Timestamp(f"{date} {h}", tz=_EST)
                sliced = result[result.index <= end_ts]
                if len(sliced) > 0:
                    hour_pl[h]   += float(sliced["session_pl"].iloc[-1])
                    hour_days[h] += 1
        except:
            pass

    avg     = total_pl / days if days else 0.0
    win_pct = wins / days * 100 if days else 0.0
    avg_by_hour = {h: round(hour_pl[h] / hour_days[h], 1) if hour_days[h] else 0.0
                   for h in HOURS}

    trial.set_user_attr("win_pct",    round(win_pct, 1))
    trial.set_user_attr("win_days",   wins)
    trial.set_user_attr("lose_days",  loses)
    trial.set_user_attr("total_pts",  round(total_pl, 0))
    trial.set_user_attr("avg_by_hour", avg_by_hour)

    return avg


N_TRIALS = 300
log(f"Running {N_TRIALS} Bayesian trials...")
study = optuna.create_study(
    study_name="fred_algo_opt",
    storage="sqlite:///fred_optuna.db",
    load_if_exists=True,          # resumes from previous runs
    direction="maximize",
    sampler=optuna.samplers.TPESampler(seed=42),
)

existing = len(study.trials)
log(f"Study loaded — {existing} existing trials, running {N_TRIALS} more.")

# Only seed if this is a fresh study
if existing == 0:
    study.enqueue_trial({
        "warmup_minutes": 7, "steep_angle_threshold": 90.0, "proximity_points": 4.0,
        "min_entry_angle": 0.0, "partial_tp_pts": 50.0, "wm_shield_distance": 0.0,
        "swing_anchor_threshold": 10.0, "spike_profit_pts": 100.0, "spike_profit_bars": 5,
    })

_trial_rows = []

def callback(study, trial):
    p  = trial.params
    ua = trial.user_attrs
    n  = len(study.trials)

    row = {
        "trial": n, "value": round(trial.value, 1),
        "best": round(study.best_value, 1),
        "win_pct": ua.get("win_pct", 0),
        "win_days": ua.get("win_days", 0),
        "lose_days": ua.get("lose_days", 0),
        "total_pts": ua.get("total_pts", 0),
        **p,
    }
    # Add hourly columns
    abh = ua.get("avg_by_hour", {})
    for h in HOURS:
        row[f"avg_{h.replace(':','')}"] = abh.get(h, 0)

    _trial_rows.append(row)
    pd.DataFrame(_trial_rows).to_csv(CSV_FILE, index=False)

    log(f"Trial {n:3d}  val={trial.value:+.1f}  best={study.best_value:+.1f}  "
        f"win={ua.get('win_pct',0):.1f}%  "
        f"warmup={p['warmup_minutes']} steep={p['steep_angle_threshold']} "
        f"prox={p['proximity_points']} ptp={p['partial_tp_pts']} "
        f"wm={p['wm_shield_distance']} swing={p['swing_anchor_threshold']} "
        f"spike_pts={p['spike_profit_pts']} spike_bars={p['spike_profit_bars']}")

study.optimize(objective, n_trials=N_TRIALS, callbacks=[callback])

log("\n=== BEST RESULT ===")
best = study.best_trial
log(f"Avg/day: {best.value:+.1f} pts  win={best.user_attrs.get('win_pct')}%  "
    f"wins={best.user_attrs.get('win_days')}  loses={best.user_attrs.get('lose_days')}")
log(f"Hourly: {best.user_attrs.get('avg_by_hour')}")
for k, v in best.params.items():
    log(f"  {k} = {v}")
