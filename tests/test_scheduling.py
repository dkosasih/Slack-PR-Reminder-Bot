"""
Unit tests for scheduling logic.
Run with: pytest tests/test_scheduling.py -v
"""
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from scheduling import (
    SchedulingConfig,
    is_within_business_hours,
    next_reminder_in_business_hours,
    next_business_hour_slot_from_epoch,
    calculate_initial_schedule,
    calculate_topup_schedule
)


@pytest.fixture
def default_config():
    """Default scheduling configuration"""
    return SchedulingConfig(
        reminder_interval_hours=3,
        business_hours_start=9,
        business_hours_end=17,
        window_size=2,
        timezone_str="Australia/Melbourne"
    )


@pytest.fixture
def mel_tz():
    """Melbourne timezone"""
    return ZoneInfo("Australia/Melbourne")


class TestIsWithinBusinessHours:
    """Tests for is_within_business_hours function"""
    
    def test_weekday_within_hours(self, default_config, mel_tz):
        """Monday 10am should be within business hours"""
        dt = datetime(2026, 1, 19, 10, 0, tzinfo=mel_tz)  # Monday 10am
        assert is_within_business_hours(dt, default_config) is True
    
    def test_weekday_before_hours(self, default_config, mel_tz):
        """Monday 8am should be outside business hours"""
        dt = datetime(2026, 1, 19, 8, 0, tzinfo=mel_tz)  # Monday 8am
        assert is_within_business_hours(dt, default_config) is False
    
    def test_weekday_after_hours(self, default_config, mel_tz):
        """Monday 6pm should be outside business hours"""
        dt = datetime(2026, 1, 19, 18, 0, tzinfo=mel_tz)  # Monday 6pm
        assert is_within_business_hours(dt, default_config) is False
    
    def test_weekend(self, default_config, mel_tz):
        """Saturday should be outside business hours"""
        dt = datetime(2026, 1, 18, 10, 0, tzinfo=mel_tz)  # Saturday 10am
        assert is_within_business_hours(dt, default_config) is False
    
    @pytest.mark.parametrize("hour,expected", [
        (9, True),   # Start of business hours
        (12, True),  # Midday
        (16, True),  # 4pm
        (17, False), # End of business hours (exclusive)
    ])
    def test_boundary_hours(self, hour, expected, default_config, mel_tz):
        """Test boundary conditions"""
        dt = datetime(2026, 1, 19, hour, 0, tzinfo=mel_tz)  # Monday
        assert is_within_business_hours(dt, default_config) is expected


class TestNextReminderInBusinessHours:
    """Tests for next_reminder_in_business_hours function"""
    
    def test_within_hours_add_interval(self, default_config, mel_tz):
        """10am + 3 hours = 1pm (same day)"""
        dt = datetime(2026, 1, 19, 10, 0, tzinfo=mel_tz)  # Monday 10am
        from_epoch = dt.timestamp()
        
        result = next_reminder_in_business_hours(from_epoch, 3, default_config)
        result_dt = datetime.fromtimestamp(result, tz=mel_tz)
        
        assert result_dt.hour == 13  # 1pm
        assert result_dt.day == 19
    
    def test_rolls_to_next_day(self, default_config, mel_tz):
        """4pm + 3 hours = 9am next business day"""
        dt = datetime(2026, 1, 19, 16, 0, tzinfo=mel_tz)  # Monday 4pm
        from_epoch = dt.timestamp()
        
        result = next_reminder_in_business_hours(from_epoch, 3, default_config)
        result_dt = datetime.fromtimestamp(result, tz=mel_tz)
        
        assert result_dt.hour == 9
        assert result_dt.day == 20  # Tuesday
    
    def test_friday_rolls_to_monday(self, default_config, mel_tz):
        """Friday 4pm + 3 hours = Monday 9am"""
        dt = datetime(2026, 1, 23, 16, 0, tzinfo=mel_tz)  # Friday 4pm
        from_epoch = dt.timestamp()
        
        result = next_reminder_in_business_hours(from_epoch, 3, default_config)
        result_dt = datetime.fromtimestamp(result, tz=mel_tz)
        
        assert result_dt.hour == 9
        assert result_dt.day == 26  # Monday
        assert result_dt.weekday() == 0


class TestNextBusinessHourSlotFromEpoch:
    """Tests for next_business_hour_slot_from_epoch function"""
    
    def test_during_business_hours(self, default_config, mel_tz):
        """Monday 12:05pm should return Monday 3:05pm (+ 3 hours)"""
        dt = datetime(2026, 1, 19, 12, 5, tzinfo=mel_tz)  # Monday 12:05pm
        epoch = dt.timestamp()
        
        result = next_business_hour_slot_from_epoch(epoch, default_config)
        result_dt = datetime.fromtimestamp(result, tz=mel_tz)
        
        assert result_dt.hour == 15
        assert result_dt.minute == 5
        assert result_dt.day == 19
    
    def test_after_hours(self, default_config, mel_tz):
        """Monday 6pm should return Tuesday 9am"""
        dt = datetime(2026, 1, 19, 18, 0, tzinfo=mel_tz)  # Monday 6pm
        epoch = dt.timestamp()
        
        result = next_business_hour_slot_from_epoch(epoch, default_config)
        result_dt = datetime.fromtimestamp(result, tz=mel_tz)
        
        assert result_dt.hour == 9
        assert result_dt.minute == 0
        assert result_dt.day == 20  # Tuesday
    
    def test_weekend(self, default_config, mel_tz):
        """Saturday should return Monday 9am"""
        dt = datetime(2026, 1, 18, 10, 0, tzinfo=mel_tz)  # Saturday 10am
        epoch = dt.timestamp()
        
        result = next_business_hour_slot_from_epoch(epoch, default_config)
        result_dt = datetime.fromtimestamp(result, tz=mel_tz)
        
        assert result_dt.hour == 9
        assert result_dt.day == 19  # Monday
        assert result_dt.weekday() == 0


class TestCalculateInitialSchedule:
    """Tests for calculate_initial_schedule function"""
    
    def test_monday_1205pm_schedule(self, default_config, mel_tz):
        """PR on Monday 12:05pm should create correct schedule"""
        pr_dt = datetime(2026, 1, 19, 12, 5, tzinfo=mel_tz)
        pr_epoch = pr_dt.timestamp()
        
        schedule = calculate_initial_schedule(pr_epoch, pr_epoch, default_config)
        
        # Convert to datetimes for easier assertion
        schedule_dts = [datetime.fromtimestamp(t, tz=mel_tz) for t in schedule]
        
        expected = [
            datetime(2026, 1, 19, 15, 5, tzinfo=mel_tz),   # Monday 15:05
            datetime(2026, 1, 20, 9, 0, tzinfo=mel_tz),    # Tuesday 09:00
            datetime(2026, 1, 20, 12, 0, tzinfo=mel_tz),   # Tuesday 12:00
            datetime(2026, 1, 20, 15, 0, tzinfo=mel_tz),   # Tuesday 15:00
            datetime(2026, 1, 21, 9, 0, tzinfo=mel_tz),    # Wednesday 09:00
            datetime(2026, 1, 21, 12, 0, tzinfo=mel_tz),   # Wednesday 12:00
            datetime(2026, 1, 21, 15, 0, tzinfo=mel_tz),   # Wednesday 15:00
        ]
        
        assert len(schedule_dts) == len(expected), f"Expected {len(expected)} reminders, got {len(schedule_dts)}"
        
        for i, (actual, exp) in enumerate(zip(schedule_dts, expected)):
            assert actual == exp, f"Reminder {i+1}: expected {exp.strftime('%A %d %b %H:%M')}, got {actual.strftime('%A %d %b %H:%M')}"
    
    def test_friday_4pm_schedule(self, default_config, mel_tz):
        """PR on Friday 4pm should roll to Monday"""
        pr_dt = datetime(2026, 1, 23, 16, 0, tzinfo=mel_tz)  # Friday 4pm
        pr_epoch = pr_dt.timestamp()
        
        schedule = calculate_initial_schedule(pr_epoch, pr_epoch, default_config)
        schedule_dts = [datetime.fromtimestamp(t, tz=mel_tz) for t in schedule]
        
        # First reminder should be Monday 9am
        assert schedule_dts[0].weekday() == 0  # Monday
        assert schedule_dts[0].hour == 9


class TestCalculateTopupSchedule:
    """Tests for calculate_topup_schedule function"""
    
    def test_tuesday_eventbridge_topup(self, default_config, mel_tz):
        """EventBridge run on Tuesday should add Thursday reminders"""
        pr_dt = datetime(2026, 1, 19, 12, 5, tzinfo=mel_tz)
        pr_epoch = pr_dt.timestamp()
        
        # Initial schedule from Monday
        initial_schedule = [
            datetime(2026, 1, 19, 15, 5, tzinfo=mel_tz).timestamp(),   # Monday 15:05
            datetime(2026, 1, 20, 9, 0, tzinfo=mel_tz).timestamp(),    # Tuesday 09:00
            datetime(2026, 1, 20, 12, 0, tzinfo=mel_tz).timestamp(),   # Tuesday 12:00
            datetime(2026, 1, 20, 15, 0, tzinfo=mel_tz).timestamp(),   # Tuesday 15:00
            datetime(2026, 1, 21, 9, 0, tzinfo=mel_tz).timestamp(),    # Wednesday 09:00
            datetime(2026, 1, 21, 12, 0, tzinfo=mel_tz).timestamp(),   # Wednesday 12:00
            datetime(2026, 1, 21, 15, 0, tzinfo=mel_tz).timestamp(),   # Wednesday 15:00
        ]
        
        # EventBridge runs Tuesday 11:05am
        eb_dt = datetime(2026, 1, 20, 11, 5, tzinfo=mel_tz)
        eb_epoch = eb_dt.timestamp()
        
        new_reminders = calculate_topup_schedule(
            initial_schedule,
            eb_epoch,
            pr_epoch,
            default_config
        )
        
        new_dts = [datetime.fromtimestamp(t, tz=mel_tz) for t in new_reminders]
        
        expected_new = [
            datetime(2026, 1, 22, 9, 0, tzinfo=mel_tz),    # Thursday 09:00
            datetime(2026, 1, 22, 12, 0, tzinfo=mel_tz),   # Thursday 12:00
            datetime(2026, 1, 22, 15, 0, tzinfo=mel_tz),   # Thursday 15:00
        ]
        
        assert len(new_dts) == len(expected_new), f"Expected {len(expected_new)} new reminders, got {len(new_dts)}"
        
        for i, (actual, exp) in enumerate(zip(new_dts, expected_new)):
            assert actual == exp, f"New reminder {i+1}: expected {exp.strftime('%A %d %b %H:%M')}, got {actual.strftime('%A %d %b %H:%M')}"
    
    def test_wednesday_eventbridge_topup(self, default_config, mel_tz):
        """EventBridge run on Wednesday should add Friday reminders"""
        pr_dt = datetime(2026, 1, 19, 12, 5, tzinfo=mel_tz)
        pr_epoch = pr_dt.timestamp()
        
        # Schedule after Tuesday top-up
        tuesday_schedule = [
            datetime(2026, 1, 20, 12, 0, tzinfo=mel_tz).timestamp(),   # Tuesday 12:00
            datetime(2026, 1, 20, 15, 0, tzinfo=mel_tz).timestamp(),   # Tuesday 15:00
            datetime(2026, 1, 21, 9, 0, tzinfo=mel_tz).timestamp(),    # Wednesday 09:00
            datetime(2026, 1, 21, 12, 0, tzinfo=mel_tz).timestamp(),   # Wednesday 12:00
            datetime(2026, 1, 21, 15, 0, tzinfo=mel_tz).timestamp(),   # Wednesday 15:00
            datetime(2026, 1, 22, 9, 0, tzinfo=mel_tz).timestamp(),    # Thursday 09:00
            datetime(2026, 1, 22, 12, 0, tzinfo=mel_tz).timestamp(),   # Thursday 12:00
            datetime(2026, 1, 22, 15, 0, tzinfo=mel_tz).timestamp(),   # Thursday 15:00
        ]
        
        # EventBridge runs Wednesday 11:05am
        eb_dt = datetime(2026, 1, 21, 11, 5, tzinfo=mel_tz)
        eb_epoch = eb_dt.timestamp()
        
        new_reminders = calculate_topup_schedule(
            tuesday_schedule,
            eb_epoch,
            pr_epoch,
            default_config
        )
        
        new_dts = [datetime.fromtimestamp(t, tz=mel_tz) for t in new_reminders]
        
        expected_new = [
            datetime(2026, 1, 23, 9, 0, tzinfo=mel_tz),    # Friday 09:00
            datetime(2026, 1, 23, 12, 0, tzinfo=mel_tz),   # Friday 12:00
            datetime(2026, 1, 23, 15, 0, tzinfo=mel_tz),   # Friday 15:00
        ]
        
        assert len(new_dts) == len(expected_new), f"Expected {len(expected_new)} new reminders, got {len(new_dts)}"
        
        for i, (actual, exp) in enumerate(zip(new_dts, expected_new)):
            assert actual == exp, f"New reminder {i+1}: expected {exp.strftime('%A %d %b %H:%M')}, got {actual.strftime('%A %d %b %H:%M')}"
    
    def test_respects_window_size(self, default_config, mel_tz):
        """Top-up should not schedule beyond WINDOW_SIZE days"""
        pr_dt = datetime(2026, 1, 19, 12, 5, tzinfo=mel_tz)
        pr_epoch = pr_dt.timestamp()
        
        existing = [
            datetime(2026, 1, 21, 15, 0, tzinfo=mel_tz).timestamp(),  # Wednesday 15:00
        ]
        
        # EventBridge runs Tuesday 11:05am
        eb_dt = datetime(2026, 1, 20, 11, 5, tzinfo=mel_tz)
        eb_epoch = eb_dt.timestamp()
        
        new_reminders = calculate_topup_schedule(
            existing,
            eb_epoch,
            pr_epoch,
            default_config
        )
        
        new_dts = [datetime.fromtimestamp(t, tz=mel_tz) for t in new_reminders]
        
        # Should only add up to Thursday 17:00 (2 business days from Tuesday)
        # Should not add Friday
        for dt in new_dts:
            assert dt.day <= 22, f"Should not schedule beyond Thursday (22nd), but found {dt.strftime('%A %d %b')}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
