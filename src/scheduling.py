"""
Pure business logic for PR reminder scheduling.
This module contains no dependencies on Slack API or AWS services.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


class SchedulingConfig:
    """Configuration for scheduling logic"""
    def __init__(
        self,
        reminder_interval_hours: int = 3,
        business_hours_start: int = 9,
        business_hours_end: int = 17,
        window_size: int = 2,
        timezone_str: str = "Australia/Melbourne"
    ):
        self.reminder_interval_hours = reminder_interval_hours
        self.business_hours_start = business_hours_start
        self.business_hours_end = business_hours_end
        self.window_size = window_size
        self.timezone = ZoneInfo(timezone_str)


def is_within_business_hours(dt_local: datetime, config: SchedulingConfig) -> bool:
    """
    Check if a datetime is within business hours (Mon-Fri, 9am-5pm by default).
    
    Args:
        dt_local: Datetime in the local timezone
        config: Scheduling configuration
    
    Returns:
        True if within business hours, False otherwise
    """
    if dt_local.weekday() >= 5:  # Weekend
        return False
    hour = dt_local.hour
    return config.business_hours_start <= hour < config.business_hours_end


def next_reminder_in_business_hours(
    from_epoch: float,
    interval_hours: int,
    config: SchedulingConfig
) -> int:
    """
    Calculate the next reminder time by adding interval_hours to from_epoch,
    rolling to next business day at business hours start if outside business hours or on weekend.
    
    Args:
        from_epoch: Starting timestamp (UTC epoch)
        interval_hours: Hours to add
        config: Scheduling configuration
    
    Returns:
        Next valid reminder timestamp (UTC epoch)
    """
    from_dt_utc = datetime.fromtimestamp(from_epoch, tz=timezone.utc)
    from_dt_local = from_dt_utc.astimezone(config.timezone)
    
    # Add the interval
    target_dt_local = from_dt_local + timedelta(hours=interval_hours)
    
    # If target falls outside business hours or on weekend, roll to next business day start
    while not is_within_business_hours(target_dt_local, config):
        # If past end of business hours or on weekend, move to next day at start hour
        if target_dt_local.weekday() >= 5 or target_dt_local.hour >= config.business_hours_end:
            # Move to next day
            target_dt_local = (target_dt_local + timedelta(days=1)).replace(
                hour=config.business_hours_start, minute=0, second=0, microsecond=0
            )
        elif target_dt_local.hour < config.business_hours_start:
            # Before business hours, move to start of business hours same day
            target_dt_local = target_dt_local.replace(
                hour=config.business_hours_start, minute=0, second=0, microsecond=0
            )
        else:
            # Should not reach here, but break just in case
            break
    
    return int(target_dt_local.astimezone(timezone.utc).timestamp())


def next_business_hour_slot_from_epoch(epoch_utc: float, config: SchedulingConfig) -> int:
    """
    Find the next available business hour slot from a given epoch.
    If within business hours, returns the next interval slot.
    If outside business hours, returns next business day at business hours start.
    
    Args:
        epoch_utc: Starting timestamp (UTC epoch)
        config: Scheduling configuration
    
    Returns:
        Next business hour slot timestamp (UTC epoch)
    """
    utc_dt = datetime.fromtimestamp(epoch_utc, tz=timezone.utc)
    local = utc_dt.astimezone(config.timezone)
    
    # If within business hours on a weekday, calculate next interval slot
    if is_within_business_hours(local, config):
        return next_reminder_in_business_hours(epoch_utc, config.reminder_interval_hours, config)
    
    # Outside business hours or weekend - find next business day start
    target = local.replace(hour=config.business_hours_start, minute=0, second=0, microsecond=0)
    
    # If before business hours today and it's a weekday, use today
    if local.weekday() < 5 and local.hour < config.business_hours_start:
        return int(target.astimezone(timezone.utc).timestamp())
    
    # Otherwise move to next business day
    target += timedelta(days=1)
    while target.weekday() >= 5:  # Skip weekends
        target += timedelta(days=1)
    
    return int(target.astimezone(timezone.utc).timestamp())


def calculate_initial_schedule(
    pr_timestamp: float,
    now_timestamp: float,
    config: SchedulingConfig
) -> list[int]:
    """
    Calculate initial schedule for a PR created at pr_timestamp.
    Creates reminders covering WINDOW_SIZE business days from now.
    
    Args:
        pr_timestamp: When the PR was created (UTC epoch)
        now_timestamp: Current time (UTC epoch)
        config: Scheduling configuration
    
    Returns:
        List of reminder timestamps (UTC epoch)
    """
    schedule = []
    
    # Calculate target: WINDOW_SIZE business days from now
    now_dt = datetime.fromtimestamp(now_timestamp, tz=timezone.utc).astimezone(config.timezone)
    target_dt = now_dt
    days_added = 0
    while days_added < config.window_size:
        target_dt += timedelta(days=1)
        if target_dt.weekday() < 5:  # Mon-Fri only
            days_added += 1
    target_timestamp = int(target_dt.replace(
        hour=config.business_hours_end,
        minute=0,
        second=0,
        microsecond=0
    ).timestamp())
    
    # Schedule reminders at interval until we reach target
    cursor_time = next_business_hour_slot_from_epoch(pr_timestamp, config)
    while cursor_time <= target_timestamp:
        schedule.append(cursor_time)
        cursor_time = next_reminder_in_business_hours(
            cursor_time,
            config.reminder_interval_hours,
            config
        )
    
    return schedule


def calculate_topup_schedule(
    existing_schedule: list[int] | list[float],
    now_timestamp: float,
    pr_timestamp: float,
    config: SchedulingConfig
) -> list[int]:
    """
    Calculate what new reminders to add during EventBridge top-up.
    
    Args:
        existing_schedule: Current scheduled reminder timestamps (UTC epoch)
        now_timestamp: Current time when top-up runs (UTC epoch)
        pr_timestamp: Original PR timestamp (UTC epoch)
        config: Scheduling configuration
    
    Returns:
        List of new reminder timestamps to add (UTC epoch)
    """
    # Filter out reminders that have already fired
    remaining = [t for t in existing_schedule if t > now_timestamp]
    remaining.sort()
    
    # Calculate target: WINDOW_SIZE business days from now
    now_dt = datetime.fromtimestamp(now_timestamp, tz=timezone.utc).astimezone(config.timezone)
    target_dt = now_dt
    days_added = 0
    while days_added < config.window_size:
        target_dt += timedelta(days=1)
        if target_dt.weekday() < 5:  # Mon-Fri only
            days_added += 1
    target_timestamp = int(target_dt.replace(
        hour=config.business_hours_end,
        minute=0,
        second=0,
        microsecond=0
    ).timestamp())
    
    # Add new reminders until we reach target
    new_reminders = []
    post_ats = remaining.copy()
    
    while not post_ats or post_ats[-1] < target_timestamp:
        if post_ats:
            base = post_ats[-1]
        else:
            # No existing schedule, start from PR time
            base = next_business_hour_slot_from_epoch(pr_timestamp, config)
        
        next_reminder = next_reminder_in_business_hours(
            base,
            config.reminder_interval_hours,
            config
        )
        
        # Stop if next reminder exceeds target (don't schedule beyond window)
        if next_reminder > target_timestamp:
            break
        
        post_ats.append(next_reminder)
        new_reminders.append(next_reminder)
    
    return new_reminders
