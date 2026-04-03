"""tests/test_interactive_brokers.py

Unit tests for IBDataBridge and _LiveChartWindow in InteractiveBrokers.py.

All IB Gateway connectivity and matplotlib display are mocked -- no running
TWS/Gateway instance is required.
"""

import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import pytz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from InteractiveBrokers import IBDataBridge, _LiveChartWindow, _build_parser

_EST = pytz.timezone("US/Eastern")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _epoch(date_str: str, time_str: str) -> datetime:
    """Timezone-aware EST datetime for a given date + time (e.g. '2024-01-15', '09:30:05')."""
    dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
    return _EST.localize(dt)


def make_bar(dt: datetime, o=38000.0, h=38010.0, l=37990.0, c=38005.0, vol=100):
    """Minimal BarData-like object with the fields _on_bar reads."""
    return types.SimpleNamespace(date=dt, open=o, high=h, low=l, close=c, volume=vol)


def make_bridge(**kw) -> IBDataBridge:
    """Return an IBDataBridge with the IB socket replaced by a MagicMock."""
    bridge = IBDataBridge(**kw)
    bridge._ib = MagicMock()
    bridge._contract = MagicMock()
    bridge._contract.localSymbol = "YMM6"
    return bridge


def feed_bar(bridge: IBDataBridge, dt: datetime, **bar_kw):
    """Deliver one sealed bar to bridge._on_bar, suppressing _run_algo."""
    bar = make_bar(dt, **bar_kw)
    with patch.object(bridge, "_run_algo"):
        bridge._on_bar([bar], has_new_bar=True)


def _one_bar_df(date: str = "2024-01-15", time: str = "09:30:00") -> pd.DataFrame:
    """Single-row DataFrame with tz-aware EST index, suitable as algo output."""
    ts = pd.Timestamp(f"{date} {time}", tz=_EST)
    return pd.DataFrame(
        [{"High": 38010.0, "Low": 37990.0, "Close": 38005.0}],
        index=[ts],
    )


# ---------------------------------------------------------------------------
# IBDataBridge.__init__
# ---------------------------------------------------------------------------

class TestIBDataBridgeInit:

    def test_defaults(self):
        b = make_bridge()
        assert b.host == "127.0.0.1"
        assert b.port == 4002
        assert b.client_id == 1
        assert b.dry_run is False
        assert b.start_time == "09:30"
        assert b.end_time == "10:00"
        assert b.show_plot is True
        assert b.tracking_root is None
        assert b.image_root is None
        assert b._session_bars == []
        assert b._current_date is None
        assert b._last_minute is None
        assert b._live_chart is None

    def test_custom_params(self):
        b = make_bridge(
            port=4002, dry_run=True,
            start_time="08:00", end_time="09:00",
            show_plot=False, tracking_root="/t", image_root="/i",
        )
        assert b.port == 4002
        assert b.dry_run is True
        assert b.start_time == "08:00"
        assert b.end_time == "09:00"
        assert b.show_plot is False
        assert b.tracking_root == "/t"
        assert b.image_root == "/i"


# ---------------------------------------------------------------------------
# _resample_to_minutes
# ---------------------------------------------------------------------------

class TestResampleToMinutes:

    def _add_bars(self, bridge, date, rows):
        """Directly populate _session_bars (list of dicts with tz-aware timestamps)."""
        for t, o, h, l, c, v in rows:
            ts = pd.Timestamp(f"{date} {t}", tz=_EST)
            bridge._session_bars.append(
                {"Open": o, "High": h, "Low": l, "Close": c, "Volume": v, "time": ts}
            )

    def test_single_minute_yields_one_row(self):
        b = make_bridge()
        self._add_bars(b, "2024-01-15", [
            ("09:30:00", 100, 110, 90, 105, 200),
            ("09:30:30", 105, 112, 92, 108, 150),
            ("09:30:55", 108, 115, 95, 110, 180),
        ])
        assert len(b._resample_to_minutes()) == 1

    def test_two_minutes_yield_two_rows(self):
        b = make_bridge()
        self._add_bars(b, "2024-01-15", [
            ("09:30:00", 100, 110, 90, 105, 200),
            ("09:30:55", 105, 112, 92, 108, 150),
            ("09:31:00", 108, 115, 95, 110, 180),
            ("09:31:55", 110, 120, 100, 115, 220),
        ])
        assert len(b._resample_to_minutes()) == 2

    def test_ohlcv_aggregation_is_correct(self):
        b = make_bridge()
        self._add_bars(b, "2024-01-15", [
            ("09:30:00", 100, 120, 90,  105, 200),   # open  = 100
            ("09:30:30", 105, 130, 85,  110, 300),   # high  = max(120,130,125) = 130
            ("09:30:55", 110, 125, 92,  115, 100),   # low   = min(90,85,92)    = 85
        ])                                            # close = last = 115
        row = b._resample_to_minutes().iloc[0]        # volume= 200+300+100      = 600
        assert row["Open"]   == 100
        assert row["High"]   == 130
        assert row["Low"]    == 85
        assert row["Close"]  == 115
        assert row["Volume"] == 600

    def test_empty_returns_empty_dataframe(self):
        b = make_bridge()
        assert b._resample_to_minutes().empty

    def test_index_is_tz_aware(self):
        b = make_bridge()
        self._add_bars(b, "2024-01-15", [("09:30:00", 100, 110, 90, 105, 200)])
        result = b._resample_to_minutes()
        assert result.index.tz is not None


# ---------------------------------------------------------------------------
# _on_bar: accumulation and minute / day rollover
# ---------------------------------------------------------------------------

class TestOnBar:

    def test_first_bar_sets_current_date_and_last_minute(self):
        b = make_bridge(show_plot=False)
        feed_bar(b, _epoch("2024-01-15", "09:30:05"))
        assert b._current_date == "2024-01-15"
        assert b._last_minute == "2024-01-15 09:30"

    def test_bars_accumulate_in_session_bars(self):
        b = make_bridge(show_plot=False)
        for i in range(3):
            feed_bar(b, _epoch("2024-01-15", f"09:30:0{i}"))
        assert len(b._session_bars) == 3

    def test_has_new_bar_false_skips_processing(self):
        b = make_bridge(show_plot=False)
        b._on_bar([make_bar(_epoch("2024-01-15", "09:30:00"))], has_new_bar=False)
        assert b._session_bars == []

    def test_empty_bars_list_skips_processing(self):
        b = make_bridge(show_plot=False)
        b._on_bar([], has_new_bar=True)
        assert b._session_bars == []

    def test_minute_rollover_triggers_update_live_chart(self):
        b = make_bridge(show_plot=True)
        with patch.object(b, "_update_live_chart") as mock_upd:
            feed_bar(b, _epoch("2024-01-15", "09:30:05"))   # first bar — no update
            mock_upd.assert_not_called()
            feed_bar(b, _epoch("2024-01-15", "09:30:50"))   # same minute — no update
            mock_upd.assert_not_called()
            feed_bar(b, _epoch("2024-01-15", "09:31:05"))   # new minute — update fires
            mock_upd.assert_called_once()

    def test_no_update_within_same_minute(self):
        b = make_bridge(show_plot=True)
        with patch.object(b, "_update_live_chart") as mock_upd:
            for sec in range(0, 60, 5):
                feed_bar(b, _epoch("2024-01-15", f"09:30:{sec:02d}"))
            mock_upd.assert_not_called()

    def test_multiple_minute_rollovers_each_trigger_update(self):
        b = make_bridge(show_plot=True)
        with patch.object(b, "_update_live_chart") as mock_upd:
            feed_bar(b, _epoch("2024-01-15", "09:30:05"))
            feed_bar(b, _epoch("2024-01-15", "09:31:05"))
            feed_bar(b, _epoch("2024-01-15", "09:32:05"))
        assert mock_upd.call_count == 2

    def test_last_minute_updated_on_rollover(self):
        b = make_bridge(show_plot=False)
        feed_bar(b, _epoch("2024-01-15", "09:30:05"))
        feed_bar(b, _epoch("2024-01-15", "09:31:05"))
        assert b._last_minute == "2024-01-15 09:31"

    def test_day_rollover_triggers_session_end(self):
        b = make_bridge(show_plot=False)
        b._current_date = "2024-01-15"
        b._last_minute = "2024-01-15 09:30"
        with patch.object(b, "_on_session_end") as mock_end:
            feed_bar(b, _epoch("2024-01-16", "09:30:05"))
        mock_end.assert_called_once()

    def test_no_session_end_within_same_day(self):
        b = make_bridge(show_plot=False)
        b._current_date = "2024-01-15"
        with patch.object(b, "_on_session_end") as mock_end:
            feed_bar(b, _epoch("2024-01-15", "09:31:00"))
        mock_end.assert_not_called()


# ---------------------------------------------------------------------------
# _on_session_end
# ---------------------------------------------------------------------------

class TestOnSessionEnd:

    def test_empty_bars_resets_state_without_calling_run_live_session(self):
        b = make_bridge()
        b._current_date = "2024-01-15"
        b._last_minute = "2024-01-15 09:30"
        with patch("InteractiveBrokers.run_live_session") as mock_rls:
            b._on_session_end()
        mock_rls.assert_not_called()
        assert b._session_bars == []
        assert b._last_result is None
        assert b._last_minute is None

    def test_closes_live_chart_first(self):
        b = make_bridge()
        mock_chart = MagicMock()
        b._live_chart = mock_chart
        with patch("InteractiveBrokers.run_live_session"):
            b._on_session_end()
        mock_chart.close.assert_called_once()
        assert b._live_chart is None

    def test_calls_run_live_session_with_correct_kwargs(self):
        b = make_bridge(
            start_time="09:30", end_time="10:00",
            show_plot=False, tracking_root="/t", image_root="/i",
        )
        b._current_date = "2024-01-15"
        ts = pd.Timestamp("2024-01-15 09:30:05", tz=_EST)
        b._session_bars = [
            {"Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": 200, "time": ts}
        ]
        with patch("InteractiveBrokers.run_live_session") as mock_rls, \
             patch.object(b, "_save_tracking_csv"):
            b._on_session_end()
        mock_rls.assert_called_once()
        _, kw = mock_rls.call_args
        assert kw["target_date"] == "2024-01-15"
        assert kw["start_time"] == "09:30"
        assert kw["end_time"] == "10:00"
        assert kw["show_plot"] is False
        assert kw["tracking_root"] == "/t"
        assert kw["image_root"] == "/i"

    def test_resets_all_state_after_run(self):
        b = make_bridge(show_plot=False)
        b._current_date = "2024-01-15"
        ts = pd.Timestamp("2024-01-15 09:30:05", tz=_EST)
        b._session_bars = [
            {"Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": 200, "time": ts}
        ]
        b._last_minute = "2024-01-15 09:30"
        with patch("InteractiveBrokers.run_live_session"):
            b._on_session_end()
        assert b._session_bars == []
        assert b._last_result is None
        assert b._last_minute is None

    def test_run_live_session_error_does_not_propagate(self):
        b = make_bridge(show_plot=False)
        b._current_date = "2024-01-15"
        ts = pd.Timestamp("2024-01-15 09:30:05", tz=_EST)
        b._session_bars = [
            {"Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": 200, "time": ts}
        ]
        with patch("InteractiveBrokers.run_live_session", side_effect=RuntimeError("boom")), \
             patch.object(b, "_save_tracking_csv"):
            b._on_session_end()   # must not raise

    def test_save_tracking_csv_called_at_session_end(self, tmp_path):
        b = make_bridge(tracking_root=str(tmp_path), show_plot=False)
        b._current_date = "2024-01-15"
        ts = pd.Timestamp("2024-01-15 09:30:05", tz=_EST)
        b._session_bars = [
            {"Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": 200, "time": ts}
        ]
        with patch("InteractiveBrokers.run_live_session"), \
             patch("InteractiveBrokers.run_trading_algo", return_value=_one_bar_df()):
            b._on_session_end()
        assert (tmp_path / "YM_tracking_2024-01-15.csv").exists()


# ---------------------------------------------------------------------------
# _update_live_chart
# ---------------------------------------------------------------------------

class TestUpdateLiveChart:

    def test_skipped_when_show_plot_false(self):
        b = make_bridge(show_plot=False)
        b._current_date = "2024-01-15"
        with patch("InteractiveBrokers.run_trading_algo") as mock_rta:
            b._update_live_chart()
        mock_rta.assert_not_called()

    def test_skipped_when_no_bars(self):
        b = make_bridge(show_plot=True)
        b._current_date = "2024-01-15"
        with patch("InteractiveBrokers.run_trading_algo") as mock_rta:
            b._update_live_chart()
        mock_rta.assert_not_called()

    def test_creates_live_chart_window_on_first_call(self):
        b = make_bridge(show_plot=True, start_time="09:30", end_time="10:00")
        b._current_date = "2024-01-15"
        ts = pd.Timestamp("2024-01-15 09:30:05", tz=_EST)
        b._session_bars = [
            {"Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": 200, "time": ts}
        ]
        fake_df = _one_bar_df()
        with patch("InteractiveBrokers.run_trading_algo", return_value=fake_df), \
             patch.object(_LiveChartWindow, "update") as mock_update:
            b._update_live_chart()
        assert b._live_chart is not None
        mock_update.assert_called_once_with(fake_df)

    def test_reuses_existing_live_chart_window(self):
        b = make_bridge(show_plot=True)
        b._current_date = "2024-01-15"
        ts = pd.Timestamp("2024-01-15 09:30:05", tz=_EST)
        b._session_bars = [
            {"Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": 200, "time": ts}
        ]
        fake_df = _one_bar_df()
        mock_chart = MagicMock()
        b._live_chart = mock_chart
        with patch("InteractiveBrokers.run_trading_algo", return_value=fake_df):
            b._update_live_chart()
        mock_chart.update.assert_called_once_with(fake_df)

    def test_trading_algo_error_does_not_propagate(self):
        b = make_bridge(show_plot=True)
        b._current_date = "2024-01-15"
        ts = pd.Timestamp("2024-01-15 09:30:05", tz=_EST)
        b._session_bars = [
            {"Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": 200, "time": ts}
        ]
        with patch("InteractiveBrokers.run_trading_algo", side_effect=ValueError("bad")):
            b._update_live_chart()   # must not raise

    def test_chart_update_error_does_not_propagate(self):
        b = make_bridge(show_plot=True)
        b._current_date = "2024-01-15"
        ts = pd.Timestamp("2024-01-15 09:30:05", tz=_EST)
        b._session_bars = [
            {"Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": 200, "time": ts}
        ]
        fake_df = _one_bar_df()
        mock_chart = MagicMock()
        mock_chart.update.side_effect = RuntimeError("render fail")
        b._live_chart = mock_chart
        with patch("InteractiveBrokers.run_trading_algo", return_value=fake_df):
            b._update_live_chart()   # must not raise


# ---------------------------------------------------------------------------
# _place_order
# ---------------------------------------------------------------------------

class TestPlaceOrder:

    def test_dry_run_does_not_call_place_order(self):
        b = make_bridge(dry_run=True)
        b._place_order("BUY")
        b._ib.placeOrder.assert_not_called()

    def test_dry_run_liquidate_does_not_call_place_order(self):
        b = make_bridge(dry_run=True)
        b._place_order("SELL", liquidate=True)
        b._ib.placeOrder.assert_not_called()

    def test_live_mode_buy_calls_place_order(self):
        b = make_bridge(dry_run=False)
        b._place_order("BUY")
        b._ib.placeOrder.assert_called_once()

    def test_live_mode_sell_calls_place_order(self):
        b = make_bridge(dry_run=False)
        b._place_order("SELL")
        b._ib.placeOrder.assert_called_once()


# ---------------------------------------------------------------------------
# _LiveChartWindow
# ---------------------------------------------------------------------------

class TestLiveChartWindow:

    def test_init_has_no_plotter(self):
        w = _LiveChartWindow("2024-01-15", "09:30", "10:00")
        assert w._plotter is None

    def test_first_update_creates_plotter_and_draws(self):
        w = _LiveChartWindow("2024-01-15", "09:30", "10:00")
        df = _one_bar_df()
        mock_plotter = MagicMock()
        mock_plotter.ax_top = None
        with patch("InteractiveBrokers.ChartPlotter", return_value=mock_plotter), \
             patch("matplotlib.pyplot.ion"):
            w.update(df)
        mock_plotter.create_figure.assert_called_once()
        mock_plotter.update_plot.assert_called_once_with(0)
        mock_plotter.fig.canvas.draw.assert_called_once()
        mock_plotter.fig.canvas.start_event_loop.assert_called_once_with(0.5)

    def test_second_update_replaces_data_and_expands_xlim(self):
        w = _LiveChartWindow("2024-01-15", "09:30", "10:00")
        ts1 = pd.Timestamp("2024-01-15 09:30:00", tz=_EST)
        ts2 = pd.Timestamp("2024-01-15 09:31:00", tz=_EST)
        df1 = pd.DataFrame([{"High": 110.0}], index=[ts1])
        df2 = pd.DataFrame([{"High": 110.0}, {"High": 115.0}], index=[ts1, ts2])

        mock_plotter = MagicMock()
        mock_plotter.ax_top = MagicMock()
        with patch("InteractiveBrokers.ChartPlotter", return_value=mock_plotter), \
             patch("matplotlib.pyplot.ion"):
            w.update(df1)
            w.update(df2)

        assert mock_plotter.data is df2
        assert mock_plotter.update_plot.call_count == 2
        mock_plotter.update_plot.assert_called_with(1)   # len(df2)-1

    def test_second_update_does_not_recreate_figure(self):
        w = _LiveChartWindow("2024-01-15", "09:30", "10:00")
        df = _one_bar_df()
        mock_plotter = MagicMock()
        mock_plotter.ax_top = None
        with patch("InteractiveBrokers.ChartPlotter", return_value=mock_plotter) as mock_cls, \
             patch("matplotlib.pyplot.ion"):
            w.update(df)
            w.update(df)
        mock_cls.assert_called_once()            # constructor called only once
        mock_plotter.create_figure.assert_called_once()  # figure created only once

    def test_close_calls_plt_close_and_clears_plotter(self):
        w = _LiveChartWindow("2024-01-15", "09:30", "10:00")
        mock_plotter = MagicMock()
        mock_plotter.fig = MagicMock()
        w._plotter = mock_plotter
        with patch("matplotlib.pyplot.close") as mock_close:
            w.close()
        mock_close.assert_called_once_with(mock_plotter.fig)
        assert w._plotter is None

    def test_close_is_safe_when_plotter_is_none(self):
        w = _LiveChartWindow("2024-01-15", "09:30", "10:00")
        with patch("matplotlib.pyplot.close") as mock_close:
            w.close()   # must not raise
        mock_close.assert_not_called()


# ---------------------------------------------------------------------------
# _build_parser
# ---------------------------------------------------------------------------

class TestBuildParser:

    def test_defaults(self):
        args = _build_parser().parse_args([])
        assert args.host == "127.0.0.1"
        assert args.port == 4002
        assert args.client_id == 1
        assert args.test is False
        assert args.dry_run is False
        assert args.start_time == "09:30"
        assert args.end_time == "10:00"
        assert args.show_plot is True
        assert args.tracking_root == os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "tracking")
        assert args.image_root == os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "charts")

    def test_all_live_flags(self):
        args = _build_parser().parse_args([
            "--port", "4002",
            "--dry-run",
            "--start-time", "08:30",
            "--end-time", "09:30",
            "--no-plot",
            "--tracking-root", "/tmp/tracking",
            "--image-root", "/tmp/images",
        ])
        assert args.port == 4002
        assert args.dry_run is True
        assert args.start_time == "08:30"
        assert args.end_time == "09:30"
        assert args.show_plot is False
        assert args.tracking_root == "/tmp/tracking"
        assert args.image_root == "/tmp/images"

    def test_test_flag(self):
        args = _build_parser().parse_args(["--test"])
        assert args.test is True

    def test_client_id_flag(self):
        args = _build_parser().parse_args(["--client-id", "5"])
        assert args.client_id == 5


# ---------------------------------------------------------------------------
# _append_bar_to_excel
# ---------------------------------------------------------------------------

class TestAppendBarToExcel:

    def test_no_file_when_tracking_root_is_none(self, tmp_path):
        b = make_bridge(tracking_root=None)
        dt = _epoch("2024-01-15", "09:30:05")
        feed_bar(b, dt)
        assert b._raw_wb is None

    def test_creates_workbook_on_first_bar(self, tmp_path):
        b = make_bridge(tracking_root=str(tmp_path))
        dt = _epoch("2024-01-15", "09:30:05")
        feed_bar(b, dt)
        assert b._raw_wb is not None
        assert b._raw_path == str(tmp_path / "YM_raw_2024-01-15.xlsx")

    def test_file_exists_after_first_bar(self, tmp_path):
        b = make_bridge(tracking_root=str(tmp_path))
        feed_bar(b, _epoch("2024-01-15", "09:30:05"))
        assert (tmp_path / "YM_raw_2024-01-15.xlsx").exists()

    def test_headers_are_correct(self, tmp_path):
        from openpyxl import load_workbook
        b = make_bridge(tracking_root=str(tmp_path))
        feed_bar(b, _epoch("2024-01-15", "09:30:05"))
        wb = load_workbook(tmp_path / "YM_raw_2024-01-15.xlsx")
        headers = [c.value for c in wb.active[1]]
        assert headers == ["Time", "Open", "High", "Low", "Close", "Volume"]

    def test_row_values_are_correct(self, tmp_path):
        from openpyxl import load_workbook
        b = make_bridge(tracking_root=str(tmp_path))
        feed_bar(b, _epoch("2024-01-15", "09:30:05"), o=38000.0, h=38010.0, l=37990.0, c=38005.0, vol=50)
        wb = load_workbook(tmp_path / "YM_raw_2024-01-15.xlsx")
        row = [c.value for c in wb.active[2]]
        assert row[0] == "2024-01-15 09:30:05"
        assert row[1] == 38000.0
        assert row[2] == 38010.0
        assert row[3] == 37990.0
        assert row[4] == 38005.0
        assert row[5] == 50

    def test_each_bar_appends_a_row(self, tmp_path):
        from openpyxl import load_workbook
        b = make_bridge(tracking_root=str(tmp_path))
        for sec in range(5, 20, 5):
            feed_bar(b, _epoch("2024-01-15", f"09:30:{sec:02d}"))
        wb = load_workbook(tmp_path / "YM_raw_2024-01-15.xlsx")
        assert wb.active.max_row == 4  # 1 header + 3 data rows


# ---------------------------------------------------------------------------
# _save_tracking_csv
# ---------------------------------------------------------------------------

class TestLiveTrackingCSV:

    def test_no_csv_when_tracking_root_is_none(self, tmp_path):
        b = make_bridge(tracking_root=None)
        b._current_date = "2024-01-15"
        ts = pd.Timestamp("2024-01-15 09:30:05", tz=_EST)
        b._session_bars = [
            {"Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": 200, "time": ts}
        ]
        with patch("InteractiveBrokers.run_trading_algo") as mock_rta:
            b._save_tracking_csv()
        mock_rta.assert_not_called()

    def test_no_csv_when_session_bars_empty(self, tmp_path):
        b = make_bridge(tracking_root=str(tmp_path))
        b._current_date = "2024-01-15"
        b._save_tracking_csv()
        assert not (tmp_path / "YM_tracking_2024-01-15.csv").exists()

    def test_csv_written_at_minute_boundary(self, tmp_path):
        b = make_bridge(tracking_root=str(tmp_path), show_plot=False)
        with patch("InteractiveBrokers.run_trading_algo", return_value=_one_bar_df()):
            feed_bar(b, _epoch("2024-01-15", "09:30:05"))   # first bar — no boundary
            assert not (tmp_path / "YM_tracking_2024-01-15.csv").exists()
            feed_bar(b, _epoch("2024-01-15", "09:31:05"))   # rollover → CSV written
        assert (tmp_path / "YM_tracking_2024-01-15.csv").exists()

    def test_no_csv_within_same_minute(self, tmp_path):
        b = make_bridge(tracking_root=str(tmp_path), show_plot=False)
        with patch("InteractiveBrokers.run_trading_algo", return_value=_one_bar_df()):
            for sec in range(0, 60, 5):
                feed_bar(b, _epoch("2024-01-15", f"09:30:{sec:02d}"))
        assert not (tmp_path / "YM_tracking_2024-01-15.csv").exists()

    def test_csv_updated_on_each_minute_boundary(self, tmp_path):
        b = make_bridge(tracking_root=str(tmp_path), show_plot=False)
        with patch("InteractiveBrokers.run_trading_algo", return_value=_one_bar_df()) as mock_rta:
            feed_bar(b, _epoch("2024-01-15", "09:30:05"))
            feed_bar(b, _epoch("2024-01-15", "09:31:05"))   # first boundary
            feed_bar(b, _epoch("2024-01-15", "09:32:05"))   # second boundary
        # show_plot=False so _update_live_chart skips algo; only _save_tracking_csv calls it
        assert mock_rta.call_count == 2
        assert (tmp_path / "YM_tracking_2024-01-15.csv").exists()

    def test_algo_error_does_not_propagate(self, tmp_path):
        b = make_bridge(tracking_root=str(tmp_path), show_plot=False)
        b._current_date = "2024-01-15"
        ts = pd.Timestamp("2024-01-15 09:30:05", tz=_EST)
        b._session_bars = [
            {"Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": 200, "time": ts}
        ]
        with patch("InteractiveBrokers.run_trading_algo", side_effect=ValueError("boom")):
            b._save_tracking_csv()   # must not raise
        assert not (tmp_path / "YM_tracking_2024-01-15.csv").exists()
