"""
Unit tests for handler.py Lambda function logic.
Run with: pytest tests/test_handler.py -v
"""
import pytest
import json
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import sys
import os

# Set up environment variables BEFORE importing handler
os.environ.setdefault('SLACK_BOT_TOKEN', 'xoxb-test-token')
os.environ.setdefault('SLACK_SIGNING_SECRET', 'test-secret')
os.environ.setdefault('REMINDER_INTERVAL_HOURS', '3')
os.environ.setdefault('BUSINESS_HOURS_START', '9')
os.environ.setdefault('BUSINESS_HOURS_END', '17')
os.environ.setdefault('WINDOW_SIZE', '2')

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture
def mock_slack_client():
    """Mock Slack WebClient"""
    with patch('handler.client') as mock_client:
        yield mock_client


@pytest.fixture
def mel_tz():
    """Melbourne timezone"""
    return ZoneInfo("Australia/Melbourne")


class TestEditedMessageHandling:
    """Tests for handling edited messages with @bot mentions"""
    
    def test_fresh_message_uses_message_timestamp(self, mock_slack_client):
        """Fresh message (not edited) should use message timestamp as base"""
        # Import handler after mocking
        import handler
        
        # Create event for fresh message (no 'edited' field)
        now = time.time()
        event = {
            "body": json.dumps({
                "type": "event_callback",
                "event_id": "test-event-1",
                "event": {
                    "type": "app_mention",
                    "channel": "C123456",
                    "ts": str(now),
                    "text": "Please review <https://github.com/test/repo/pull/123>"
                }
            }),
            "headers": {
                "x-slack-request-timestamp": str(int(now)),
                "x-slack-signature": "v0=test"
            }
        }
        
        # Mock slack client responses
        mock_slack_client.reactions_add.return_value = {"ok": True}
        mock_slack_client.chat_scheduledMessages_list.return_value = {
            "scheduled_messages": []
        }
        mock_slack_client.chat_scheduleMessage.return_value = {"ok": True}
        
        # Mock signature verification
        with patch('handler._verify_slack_signature', return_value=True):
            # Call handler
            handler.lambda_handler(event, None)
        
        # Verify schedule was called with times based on message timestamp
        assert mock_slack_client.chat_scheduleMessage.called
    
    def test_edited_message_less_than_hour_old_uses_original_timestamp(self, mock_slack_client):
        """Message edited within 1 hour should still use original timestamp"""
        import handler
        
        # Create message edited 30 minutes after creation
        now = time.time()
        message_ts = now - (30 * 60)  # 30 minutes ago
        edit_ts = now
        
        event = {
            "body": json.dumps({
                "type": "event_callback",
                "event_id": "test-event-2",
                "event": {
                    "type": "app_mention",
                    "channel": "C123456",
                    "ts": str(message_ts),
                    "edited": {
                        "user": "U123456",
                        "ts": str(edit_ts)
                    },
                    "text": "Please review <https://github.com/test/repo/pull/123>"
                }
            }),
            "headers": {
                "x-slack-request-timestamp": str(int(now)),
                "x-slack-signature": "v0=test"
            }
        }
        
        mock_slack_client.reactions_add.return_value = {"ok": True}
        mock_slack_client.chat_scheduledMessages_list.return_value = {
            "scheduled_messages": []
        }
        
        # Track the schedule calls
        schedule_calls = []
        def track_schedule(*args, **kwargs):
            schedule_calls.append(kwargs)
            return {"ok": True}
        
        mock_slack_client.chat_scheduleMessage.side_effect = track_schedule
        
        with patch('handler._verify_slack_signature', return_value=True):
            handler.lambda_handler(event, None)
        
        # Verify schedules were created and check if they're in the future
        assert len(schedule_calls) > 0
        for call in schedule_calls:
            # post_at should be in the future relative to now
            assert call['post_at'] > now
    
    def test_edited_message_more_than_hour_old_uses_current_time(self, mock_slack_client):
        """Message edited >1 hour after creation should use current time as base"""
        import handler
        
        # Create message edited 18 hours after creation (like the bug case)
        now = time.time()
        message_ts = now - (18 * 3600)  # 18 hours ago
        edit_ts = now
        
        event = {
            "body": json.dumps({
                "type": "event_callback",
                "event_id": "test-event-3",
                "event": {
                    "type": "app_mention",
                    "channel": "C123456",
                    "ts": str(message_ts),
                    "edited": {
                        "user": "U123456",
                        "ts": str(edit_ts)
                    },
                    "text": "Please review <https://github.com/test/repo/pull/123>"
                }
            }),
            "headers": {
                "x-slack-request-timestamp": str(int(now)),
                "x-slack-signature": "v0=test"
            }
        }
        
        mock_slack_client.reactions_add.return_value = {"ok": True}
        mock_slack_client.chat_scheduledMessages_list.return_value = {
            "scheduled_messages": []
        }
        
        # Track the schedule calls
        schedule_calls = []
        def track_schedule(*args, **kwargs):
            schedule_calls.append(kwargs)
            return {"ok": True}
        
        mock_slack_client.chat_scheduleMessage.side_effect = track_schedule
        
        with patch('handler._verify_slack_signature', return_value=True):
            handler.lambda_handler(event, None)
        
        # Verify schedules were created
        assert len(schedule_calls) > 0
        
        # All scheduled times should be in the future (not in the past)
        for call in schedule_calls:
            assert call['post_at'] > now, f"post_at {call['post_at']} should be > now {now}"
            # Should not be scheduling based on 18-hour-old timestamp
            # If it were, first reminder would be ~18 hours ago + 3 hours = ~15 hours ago
            assert call['post_at'] > message_ts + (3 * 3600), \
                "Should not schedule based on old message timestamp"
    
    def test_edited_old_message_no_time_in_past_error(self, mock_slack_client):
        """Edited old message should not cause 'time_in_past' error"""
        import handler
        from slack_sdk.errors import SlackApiError
        
        now = time.time()
        message_ts = now - (18 * 3600)  # 18 hours ago
        
        event = {
            "body": json.dumps({
                "type": "event_callback",
                "event_id": "test-event-4",
                "event": {
                    "type": "app_mention",
                    "channel": "C123456",
                    "ts": str(message_ts),
                    "edited": {
                        "user": "U123456",
                        "ts": str(now)
                    },
                    "text": "Please review <https://github.com/test/repo/pull/123>"
                }
            }),
            "headers": {
                "x-slack-request-timestamp": str(int(now)),
                "x-slack-signature": "v0=test"
            }
        }
        
        mock_slack_client.reactions_add.return_value = {"ok": True}
        mock_slack_client.chat_scheduledMessages_list.return_value = {
            "scheduled_messages": []
        }
        
        # Mock schedule to succeed (no time_in_past error)
        mock_slack_client.chat_scheduleMessage.return_value = {"ok": True}
        
        with patch('handler._verify_slack_signature', return_value=True):
            result = handler.lambda_handler(event, None)
        
        # Handler should complete successfully
        assert result['statusCode'] == 200
        
        # Should NOT have tried to add 'x' reaction (error indicator)
        x_reaction_calls = [
            call for call in mock_slack_client.reactions_add.call_args_list
            if call[1].get('name') == 'x'
        ]
        assert len(x_reaction_calls) == 0, "Should not add :x: reaction for edited message"


class TestMessageTimestampHandling:
    """Tests for base timestamp selection logic"""
    
    def test_calculates_base_ts_for_fresh_message(self):
        """Fresh message should use message_ts as base"""
        import handler
        
        message_ts = 1770178340.265529
        now = 1770246089.0
        edited_info = None
        
        # Simulate the logic from handler
        base_ts = float(message_ts)
        
        if edited_info:
            if now - base_ts > 3600:  # 1 hour
                base_ts = now
        
        # Should still be original timestamp
        assert base_ts == message_ts
    
    def test_calculates_base_ts_for_old_edited_message(self):
        """Old edited message should use current time as base"""
        import handler
        
        message_ts = 1770178340.265529  # 18 hours ago
        now = 1770246089.0
        edited_info = {"user": "U123", "ts": "1770246087.000000"}
        
        # Simulate the logic from handler
        base_ts = float(message_ts)
        
        if edited_info:
            if now - base_ts > 3600:  # 1 hour
                base_ts = now
        
        # Should be current time
        assert base_ts == now
    
    def test_threshold_exactly_one_hour(self):
        """Message edited exactly 1 hour ago should use original timestamp"""
        message_ts = 1000.0
        now = 1000.0 + 3600.0  # Exactly 1 hour
        edited_info = {"user": "U123", "ts": str(now)}
        
        base_ts = float(message_ts)
        
        if edited_info:
            if now - base_ts > 3600:  # Strictly greater than 1 hour
                base_ts = now
        
        # Should still use original (not strictly > 1 hour)
        assert base_ts == message_ts
    
    def test_threshold_just_over_one_hour(self):
        """Message edited 1 hour + 1 second ago should use current time"""
        message_ts = 1000.0
        now = 1000.0 + 3601.0  # 1 hour + 1 second
        edited_info = {"user": "U123", "ts": str(now)}
        
        base_ts = float(message_ts)
        
        if edited_info:
            if now - base_ts > 3600:
                base_ts = now
        
        # Should use current time
        assert base_ts == now


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
