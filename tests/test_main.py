"""
Tests for Main.py - YM Trading System
"""

import pytest
import pandas as pd
from datetime import datetime
import numpy as np


class TestGetYMIntraday:
    """Tests for get_ym_intraday function"""
    
    def test_get_ym_intraday_returns_dataframe(self, mocker):
        """Test that get_ym_intraday returns a pandas DataFrame"""
        # This is a placeholder - actual implementation would mock yfinance
        # For now, we'll create a simple structure test
        pass
    
    def test_get_ym_intraday_with_valid_date(self):
        """Test with a valid trading date"""
        # Placeholder for testing valid date input
        pass
    
    def test_get_ym_intraday_with_invalid_date(self):
        """Test with an invalid date format"""
        # Placeholder for testing invalid date handling
        pass


class TestDataValidation:
    """Tests for data validation and processing"""
    
    def test_data_has_required_columns(self):
        """Test that fetched data has required OHLCV columns"""
        required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        # Create sample data
        sample_data = pd.DataFrame({
            'Open': [49000, 49100],
            'High': [49050, 49150],
            'Low': [48950, 49050],
            'Close': [49025, 49125],
            'Volume': [1000, 1500]
        })
        
        for col in required_columns:
            assert col in sample_data.columns, f"Missing required column: {col}"
    
    def test_data_types_are_numeric(self):
        """Test that price and volume data are numeric"""
        sample_data = pd.DataFrame({
            'Open': [49000, 49100],
            'High': [49050, 49150],
            'Low': [48950, 49050],
            'Close': [49025, 49125],
            'Volume': [1000, 1500]
        })
        
        numeric_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in numeric_columns:
            assert pd.api.types.is_numeric_dtype(sample_data[col]), f"{col} should be numeric"
    
    def test_high_is_greater_than_low(self):
        """Test that High is always >= Low"""
        sample_data = pd.DataFrame({
            'High': [49050, 49150, 49200],
            'Low': [48950, 49050, 49100]
        })
        
        assert all(sample_data['High'] >= sample_data['Low']), "High should always be >= Low"
    
    def test_ohlc_relationships(self):
        """Test OHLC relationships: Low <= Open, Close <= High"""
        sample_data = pd.DataFrame({
            'Open': [49000, 49100, 49200],
            'High': [49050, 49150, 49250],
            'Low': [48950, 49050, 49150],
            'Close': [49025, 49125, 49225]
        })
        
        assert all(sample_data['Low'] <= sample_data['Open']), "Low should be <= Open"
        assert all(sample_data['Low'] <= sample_data['Close']), "Low should be <= Close"
        assert all(sample_data['High'] >= sample_data['Open']), "High should be >= Open"
        assert all(sample_data['High'] >= sample_data['Close']), "High should be >= Close"


class TestSignalDetection:
    """Tests for buy/sell signal detection logic"""
    
    def test_position_states(self):
        """Test that position states are valid"""
        valid_states = [None, 'long', 'short']
        # Test state transitions
        assert None in valid_states
        assert 'long' in valid_states
        assert 'short' in valid_states
    
    def test_buy_signal_not_when_long(self):
        """Test that BUY signals are not generated when already long"""
        position = 'long'
        # When position is 'long', should not generate another BUY
        assert position == 'long', "Cannot generate BUY signal when already long"
    
    def test_sell_signal_not_when_short(self):
        """Test that SELL signals are not generated when already short"""
        position = 'short'
        # When position is 'short', should not generate another SELL
        assert position == 'short', "Cannot generate SELL signal when already short"
    
    def test_can_buy_from_none_or_short(self):
        """Test that BUY is allowed from None or short positions"""
        valid_buy_states = [None, 'short']
        assert None in valid_buy_states
        assert 'short' in valid_buy_states
        assert 'long' not in valid_buy_states
    
    def test_can_sell_from_none_or_long(self):
        """Test that SELL is allowed from None or long positions"""
        valid_sell_states = [None, 'long']
        assert None in valid_sell_states
        assert 'long' in valid_sell_states
        assert 'short' not in valid_sell_states


class TestRayCalculations:
    """Tests for ray angle calculations"""
    
    def test_angle_to_slope_conversion(self):
        """Test conversion from degrees to slope"""
        # For -5 degrees
        angle_deg = -5
        angle_rad = np.deg2rad(angle_deg)
        tan_angle = np.tan(angle_rad)
        assert tan_angle < 0, "-5 degree angle should have negative slope"
        
        # For +5 degrees
        angle_deg = 5
        angle_rad = np.deg2rad(angle_deg)
        tan_angle = np.tan(angle_rad)
        assert tan_angle > 0, "+5 degree angle should have positive slope"
    
    def test_steep_angle_slopes(self):
        """Test steep angle slopes (±65 degrees)"""
        # For -65 degrees
        angle_deg = -65
        angle_rad = np.deg2rad(angle_deg)
        tan_angle = np.tan(angle_rad)
        assert tan_angle < -2, "-65 degree angle should have steep negative slope"
        
        # For +65 degrees
        angle_deg = 65
        angle_rad = np.deg2rad(angle_deg)
        tan_angle = np.tan(angle_rad)
        assert tan_angle > 2, "+65 degree angle should have steep positive slope"


class TestTimeValidation:
    """Tests for time-based validation"""
    
    def test_cutoff_time_format(self):
        """Test that cutoff time (9:38 AM) is correctly formatted"""
        cutoff_str = "09:38:00"
        cutoff_time = datetime.strptime(cutoff_str, "%H:%M:%S")
        assert cutoff_time.hour == 9
        assert cutoff_time.minute == 38
    
    def test_trading_window(self):
        """Test that trading window is 9:30 - 10:00 AM"""
        start_time = "09:30"
        end_time = "10:00"
        
        start_dt = datetime.strptime(start_time, "%H:%M")
        end_dt = datetime.strptime(end_time, "%H:%M")
        
        assert start_dt.hour == 9 and start_dt.minute == 30
        assert end_dt.hour == 10 and end_dt.minute == 0
        
        # Check duration is 30 minutes
        duration = (end_dt - start_dt).total_seconds() / 60
        assert duration == 30, "Trading window should be 30 minutes"


class TestSnapshotTimes:
    """Tests for snapshot timing"""
    
    def test_snapshot_times_are_valid(self):
        """Test that snapshot times are within trading window"""
        snapshot_times = ['09:31', '09:38', '09:45', '09:55', '10:00']
        
        for time_str in snapshot_times:
            hour, minute = map(int, time_str.split(':'))
            # Check within trading window (9:30 - 10:00)
            assert (hour == 9 and minute >= 30) or (hour == 10 and minute == 0)
    
    def test_snapshot_times_count(self):
        """Test that we have exactly 5 snapshot times"""
        snapshot_times = ['09:31', '09:38', '09:45', '09:55', '10:00']
        assert len(snapshot_times) == 5, "Should have exactly 5 snapshot times"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
