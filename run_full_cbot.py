"""Run RunFullDataSet on per-day CBOT_MINI_YM1 data (1-min), 09:30-10:00 window."""
from RunFullDataSet import run_from_desktop

if __name__ == "__main__":
    # Folder on Desktop created earlier by split_cbot_mini_ym1_by_date.py
    run_from_desktop(desktop_subfolder="CBOT_MINI_YM1_ByDate", start_time="09:30", end_time="10:00")
