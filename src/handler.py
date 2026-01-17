import os, re, time, hmac, hashlib, json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from slack_sdk.web import WebClient
from slack_sdk.errors import SlackApiError

# Required env vars
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]

# Optional config
WINDOW_SIZE = int(os.environ.get("WINDOW_SIZE", "2"))  # how many business days to maintain reminders
REMINDER_INTERVAL_HOURS = int(os.environ.get("REMINDER_INTERVAL_HOURS", "3"))  # hours between reminders during business hours
BUSINESS_HOURS_START = int(os.environ.get("BUSINESS_HOURS_START", "9"))  # 9am
BUSINESS_HOURS_END = int(os.environ.get("BUSINESS_HOURS_END", "17"))  # 5pm
MEL_TZ = ZoneInfo("Australia/Melbourne")

# Slack client and patterns
client = WebClient(token=SLACK_BOT_TOKEN)

# In-memory event deduplication (survives for Lambda container lifetime)
_processed_events = set()

PR_RE = re.compile(r"https?://github\.com/[^/\s]+/[^/\s]+/pull/\d+")
MARKER_RE = re.compile(r"\[PR-NUDGE ts=([0-9]+\.[0-9]+) url=<?(.+?)>?\]")
MARKER_FMT = "[PR-NUDGE ts={} url={}]"

REMINDER_TEXT = os.environ.get(
    "REMINDER_TEXT",
    "Friendly nudge: no emoji reaction yet on this PR. React with 👀 if you’re taking it; mention me in the threadwith :approved: emoji when approved. Thanks!"
)

def _verify_slack_signature(headers, body: str) -> bool:
    # API Gateway may case-normalize headers; prefer lowercase keys
    timestamp = headers.get("x-slack-request-timestamp") or headers.get("X-Slack-Request-Timestamp")
    signature = headers.get("x-slack-signature") or headers.get("X-Slack-Signature")
    if not timestamp or not signature:
        return False
    # Replay guard (5 minutes)
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False
    basestring = f"v0:{timestamp}:{body}"
    my_sig = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode("utf-8"),
        basestring.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(my_sig, signature)

def _is_within_business_hours(dt_local: datetime) -> bool:
    """Check if a datetime is within business hours (Mon-Fri, 9am-5pm Melbourne time)"""
    if dt_local.weekday() >= 5:  # Weekend
        return False
    hour = dt_local.hour
    return BUSINESS_HOURS_START <= hour < BUSINESS_HOURS_END

def _next_reminder_in_business_hours(from_epoch: float, interval_hours: int) -> int:
    """
    Calculate the next reminder time by adding interval_hours to from_epoch,
    rolling to next business day at BUSINESS_HOURS_START if outside business hours or on weekend.
    
    Args:
        from_epoch: Starting timestamp (UTC epoch)
        interval_hours: Hours to add
    
    Returns:
        Next valid reminder timestamp (UTC epoch)
    """
    from_dt_utc = datetime.fromtimestamp(from_epoch, tz=timezone.utc)
    from_dt_local = from_dt_utc.astimezone(MEL_TZ)
    
    # Add the interval
    target_dt_local = from_dt_local + timedelta(hours=interval_hours)
    
    # If target falls outside business hours or on weekend, roll to next business day start
    while not _is_within_business_hours(target_dt_local):
        # If past end of business hours or on weekend, move to next day at start hour
        if target_dt_local.weekday() >= 5 or target_dt_local.hour >= BUSINESS_HOURS_END:
            # Move to next day
            target_dt_local = (target_dt_local + timedelta(days=1)).replace(
                hour=BUSINESS_HOURS_START, minute=0, second=0, microsecond=0
            )
        elif target_dt_local.hour < BUSINESS_HOURS_START:
            # Before business hours, move to start of business hours same day
            target_dt_local = target_dt_local.replace(
                hour=BUSINESS_HOURS_START, minute=0, second=0, microsecond=0
            )
        else:
            # Should not reach here, but break just in case
            break
    
    return int(target_dt_local.astimezone(timezone.utc).timestamp())

def _next_business_hour_slot_from_epoch(epoch_utc: float) -> int:
    """
    Find the next available business hour slot from a given epoch.
    If within business hours, returns the next interval slot.
    If outside business hours, returns next business day at BUSINESS_HOURS_START.
    
    Args:
        epoch_utc: Starting timestamp (UTC epoch)
    
    Returns:
        Next business hour slot timestamp (UTC epoch)
    """
    utc_dt = datetime.fromtimestamp(epoch_utc, tz=timezone.utc)
    local = utc_dt.astimezone(MEL_TZ)
    
    # If within business hours on a weekday, calculate next interval slot
    if _is_within_business_hours(local):
        return _next_reminder_in_business_hours(epoch_utc, REMINDER_INTERVAL_HOURS)
    
    # Outside business hours or weekend - find next business day start
    target = local.replace(hour=BUSINESS_HOURS_START, minute=0, second=0, microsecond=0)
    
    # If before business hours today and it's a weekday, use today
    if local.weekday() < 5 and local.hour < BUSINESS_HOURS_START:
        return int(target.astimezone(timezone.utc).timestamp())
    
    # Otherwise move to next business day
    target += timedelta(days=1)
    while target.weekday() >= 5:  # Skip weekends
        target += timedelta(days=1)
    
    return int(target.astimezone(timezone.utc).timestamp())

def _next_business_day_10am_mel_from_epoch(epoch_utc: float) -> int:
    utc_dt = datetime.fromtimestamp(epoch_utc, tz=timezone.utc)
    local = utc_dt.astimezone(MEL_TZ)
    target = local.replace(hour=10, minute=0, second=0, microsecond=0)
    if local >= target:
        target += timedelta(days=1)
    while target.weekday() >= 5:  # Sat/Sun
        target += timedelta(days=1)
    return int(target.astimezone(timezone.utc).timestamp())

def _next_business_day_10am_after(post_at_epoch_utc: int) -> int:
    ref_local = datetime.fromtimestamp(post_at_epoch_utc, tz=timezone.utc).astimezone(MEL_TZ)
    target = ref_local.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
    while target.weekday() >= 5:
        target += timedelta(days=1)
    return int(target.astimezone(timezone.utc).timestamp())

def _schedule_nudge(channel: str, thread_ts: str, post_at: int, original_ts: str, pr_url: str = ""):
    marker = MARKER_FMT.format(original_ts, pr_url)
    # Replace "this PR" with a link to the PR
    reminder_text = REMINDER_TEXT.replace("this PR", f"<{pr_url}|this PR>") if pr_url else REMINDER_TEXT
    client.chat_scheduleMessage(
        channel=channel,
        text=f"{marker} {reminder_text}",
        post_at=post_at,
        thread_ts=thread_ts,
        reply_broadcast=True
    )

def _get_existing_scheduled_times_for_thread(channel: str, original_ts: str) -> set[int]:
    """Get all existing scheduled times for a specific PR thread"""
    existing_times = set()
    marker_prefix = f"[PR-NUDGE ts={original_ts}"
    cursor = None
    
    while True:
        resp = client.chat_scheduledMessages_list(channel=channel, limit=100, cursor=cursor)
        for item in resp.get("scheduled_messages", []):
            if marker_prefix in (item.get("text") or ""):
                existing_times.add(int(item.get("post_at")))
        cursor = (resp.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break
    
    return existing_times

def _schedule_nudge_if_not_exists(channel: str, thread_ts: str, post_at: int, original_ts: str, existing_times: set[int], pr_url: str = "") -> bool:
    """Schedule a nudge only if no message is already scheduled for that time"""
    if post_at not in existing_times:
        _schedule_nudge(channel, thread_ts, post_at, original_ts, pr_url)
        existing_times.add(post_at)  # Update the set to prevent future duplicates in same batch
        return True
    return False

def _delete_scheduled_nudges_for_thread(channel: str, original_ts: str):
    # Cancel all scheduled messages for this PR thread by matching the marker
    cursor = None
    # Use partial marker match since URL might vary
    marker_prefix = f"[PR-NUDGE ts={original_ts}"
    while True:
        resp = client.chat_scheduledMessages_list(channel=channel, limit=100, cursor=cursor)
        for item in resp.get("scheduled_messages", []):
            if marker_prefix in (item.get("text") or ""):
                try:
                    client.chat_deleteScheduledMessage(
                        channel=channel,
                        scheduled_message_id=item["id"]
                    )
                except SlackApiError as e:
                    print(f"delete scheduled failed: {e}")
        cursor = (resp.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break

def _top_up_all_channels():
    """
    Maintain a rolling window of WINDOW_SIZE future reminders for each PR thread
    across all channels. Discovers channels dynamically from existing scheduled messages.
    """
    # Group scheduled messages by channel and thread
    channel_groups: dict[str, dict[str, tuple[list[int], str]]] = {}  # channel -> {original_ts -> (list[post_at], pr_url)}
    cursor = None
    
    # List all scheduled messages (without channel filter to get all channels)
    while True:
        resp = client.chat_scheduledMessages_list(limit=100, cursor=cursor)
        for item in resp.get("scheduled_messages", []):
            text = item.get("text", "") or ""
            m = MARKER_RE.search(text)
            if not m:
                continue
            
            channel = item.get("channel")
            original_ts = m.group(1)
            pr_url = m.group(2)
            post_at = int(item.get("post_at"))
            
            if channel:
                if channel not in channel_groups:
                    channel_groups[channel] = {}
                if original_ts not in channel_groups[channel]:
                    channel_groups[channel][original_ts] = ([], pr_url)
                channel_groups[channel][original_ts][0].append(post_at)
        
        cursor = (resp.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break
    
    print(f"Found PR reminders in {len(channel_groups)} channel(s)")
    
    # Top up each channel
    for channel, groups in channel_groups.items():
        print(f"Topping up channel {channel} with {len(groups)} PR thread(s)")
        
        for original_ts, (post_ats, pr_url) in groups.items():
            post_ats.sort()
            
            # Calculate target: WINDOW_SIZE business days from now
            now = time.time()
            now_dt = datetime.fromtimestamp(now, tz=timezone.utc).astimezone(MEL_TZ)
            target_dt = now_dt
            days_added = 0
            while days_added < WINDOW_SIZE:
                target_dt += timedelta(days=1)
                if target_dt.weekday() < 5:  # Mon-Fri only
                    days_added += 1
            # Set target to end of business hours on the target day
            target_timestamp = int(target_dt.replace(hour=BUSINESS_HOURS_END, minute=0, second=0, microsecond=0).timestamp())
            
            # Keep adding reminders until we have coverage through target date
            while not post_ats or post_ats[-1] < target_timestamp:
                # Get the base time (last scheduled or first business hour slot from original message)
                if post_ats:
                    base = post_ats[-1]
                else:
                    base = _next_business_hour_slot_from_epoch(float(original_ts))
                
                # Calculate next reminder time using interval
                next_pa = _next_reminder_in_business_hours(base, REMINDER_INTERVAL_HOURS)
                
                # Stop if next reminder exceeds target (don't schedule beyond window)
                if next_pa > target_timestamp:
                    break
                
                try:
                    _schedule_nudge(channel, original_ts, next_pa, original_ts, pr_url)
                    post_ats.append(next_pa)
                    next_dt = datetime.fromtimestamp(next_pa, tz=timezone.utc).astimezone(MEL_TZ)
                    print(f"Scheduled reminder at {next_dt.strftime('%Y-%m-%d %H:%M')} for thread {original_ts}")
                except SlackApiError as e:
                    print(f"top-up schedule failed for channel {channel}: {e}")
                    break
                
def _is_already_reacted(text: str) -> bool:
    return text == "already_reacted"
    
def _is_check_mark_reacted(channel, message_ts) -> bool:
    # Before adding ?, check if ✅ already exists (might be a retry after successful cancel)
    if _add_check_mark(channel, message_ts):
        # If we successfully added ✅, it means first invocation didn't complete
        # But also means there were no reminders, so remove ✅ and add ?
        client.reactions_remove(
            channel=channel,
            timestamp=message_ts,
            name="white_check_mark"
        )
        return False
    
    return True

def _add_check_mark(channel, message_ts) -> bool:
    # React to confirm cancellation
    try:
        client.reactions_add(
            channel=channel,
            timestamp=message_ts,
            name="white_check_mark"
        )
    except SlackApiError as reaction_err:
        if _is_already_reacted(reaction_err.response.get("error")):
            print(f"Already processed (reaction exists), skipping")
            return False
        else:
            raise
    return True

def lambda_handler(event, context):
    print(f"Received event: {json.dumps(event)}")  # Debug logging
    
    # EventBridge scheduled top-up branch
    if event.get("source") == "aws.events":
        try:
            _top_up_all_channels()
        except SlackApiError as e:
            print(f"top-up error: {e}")
        return {"statusCode": 200, "body": ""}

    # Slack Events via API Gateway HTTP API
    body = event.get("body") or ""
    headers = event.get("headers", {})
    print(f"Body length: {len(body)}, Headers: {list(headers.keys())}")  # Debug logging

    if not _verify_slack_signature(headers, body):
        print("Signature verification failed!")  # Debug logging
        return {"statusCode": 403, "body": "invalid signature"}

    payload = json.loads(body)
    print(f"Payload type: {payload.get('type')}, Event type: {payload.get('event', {}).get('type')}")  # Debug logging
    
    # Idempotency check - deduplicate retries using event_id
    event_id = payload.get("event_id")
    if event_id and event_id in _processed_events:
        print(f"Event {event_id} already processed, skipping duplicate")
        return {"statusCode": 200, "body": ""}
    if event_id:
        _processed_events.add(event_id)
        # Keep only last 1000 event IDs to prevent unbounded memory growth
        if len(_processed_events) > 100:
            _processed_events.pop()

    # URL verification handshake
    if payload.get("type") == "url_verification":
        return {"statusCode": 200, "headers": {"Content-Type": "text/plain"}, "body": payload.get("challenge", "")}

    # Event callback handling
    if payload.get("type") == "event_callback":
        ev = payload.get("event", {})
        etype = ev.get("type")

        # Handle app mentions (when users @mention the bot with PR links)
        if etype == "app_mention":
            channel = ev.get("channel")
            message_ts = ev.get("ts")
            text = ev.get("text", "")
            thread_ts = ev.get("thread_ts")  # Present if this is a thread reply
            
            print(f"app_mention event - Channel: {channel}, Text: {text}, Thread: {thread_ts}")  # Debug logging
            
            # Check if this is a thread reply requesting cancellation
            if thread_ts and thread_ts != message_ts:
                # This is a reply in a thread (not the parent message)
                print(f"Detected thread reply, checking for cancellation request")
                
                # Check if message contains :approved: emoji
                if ":approved:" in text or "approved" in text.lower():
                    print(f"Found approval indicator, checking if parent has PR reminders")
                    
                    # Check if the parent message has scheduled reminders
                    try:
                        marker_prefix = f"[PR-NUDGE ts={thread_ts}"
                        has_reminders = False
                        
                        # Quick check if this thread has any scheduled messages
                        resp = client.chat_scheduledMessages_list(channel=channel, limit=100)
                        for item in resp.get("scheduled_messages", []):
                            if marker_prefix in (item.get("text") or ""):
                                has_reminders = True
                                break
                        
                        if has_reminders:
                            print(f"Parent message has reminders, cancelling all scheduled messages")
                            _delete_scheduled_nudges_for_thread(channel, thread_ts)
                            
                            # React to confirm cancellation
                            _add_check_mark(channel, message_ts)
                            print(f"Successfully cancelled reminders for thread {thread_ts}")
                            return {"statusCode": 200, "body": ""}
                        else:
                            print(f"No reminders found for thread {thread_ts}")
                            
                            if(_is_check_mark_reacted(channel, message_ts)):
                                print(f"Already processed successfully (✅ exists), skipping ❓")
                                return {"statusCode": 200, "body": ""}
                            
                            # Genuinely no reminders found - react with question mark
                            try:
                                client.reactions_add(
                                    channel=channel,
                                    timestamp=message_ts,
                                    name="question"
                                )
                            except SlackApiError as reaction_err:
                                if _is_already_reacted(reaction_err.response.get("error")):
                                    print(f"Already processed (reaction exists), skipping")
                                else:
                                    raise
                            return {"statusCode": 200, "body": ""}
                    
                    except SlackApiError as e:
                        print(f"Error checking/cancelling reminders: {e}")
                        # React with X to indicate error (unless already reacted)
                        if _is_already_reacted(e.response.get("error")):
                            try:
                                client.reactions_add(
                                    channel=channel,
                                    timestamp=message_ts,
                                    name="x"
                                )
                            except:
                                pass
                        return {"statusCode": 200, "body": ""}
            
            # Original logic: Extract PR URLs from text (works with both plain URLs and markdown links)
            pr_match = PR_RE.search(text)
            
            if pr_match and channel and message_ts:
                pr_url = pr_match.group(0)
                print(f"Found PR URL: {pr_url}")
                
                try:
                    # React to confirm we received it
                    _add_check_mark(channel, message_ts)
                    
                    # Schedule reminders for this message using interval-based logic
                    base_ts = float(message_ts)
                    existing_times = _get_existing_scheduled_times_for_thread(channel, message_ts)
                    
                    # Find first reminder slot (next available business hour)
                    cursor_time = _next_business_hour_slot_from_epoch(base_ts)
                    
                    # Calculate target end date: WINDOW_SIZE business days from now
                    now = time.time()
                    now_dt = datetime.fromtimestamp(now, tz=timezone.utc).astimezone(MEL_TZ)
                    target_dt = now_dt
                    days_added = 0
                    while days_added < WINDOW_SIZE:
                        target_dt += timedelta(days=1)
                        if target_dt.weekday() < 5:  # Mon-Fri only
                            days_added += 1
                    target_timestamp = int(target_dt.replace(hour=BUSINESS_HOURS_END, minute=0, second=0, microsecond=0).timestamp())
                    
                    # Schedule reminders at interval until we reach target
                    reminder_count = 0
                    while cursor_time <= target_timestamp:
                        if _schedule_nudge_if_not_exists(channel, message_ts, cursor_time, message_ts, existing_times, pr_url):
                            reminder_count += 1
                        cursor_time = _next_reminder_in_business_hours(cursor_time, REMINDER_INTERVAL_HOURS)
                    
                    print(f"Scheduled {reminder_count} reminders for PR: {pr_url}")
                    
                except SlackApiError as e:
                    # If already_reacted, it means we already processed this (retry/duplicate)
                    if _is_already_reacted(e.response.get("error")):
                        print(f"Already processed this message (already_reacted), skipping")
                        return {"statusCode": 200, "body": ""}
                    
                    print(f"schedule failed: {e}")
                    # Try to react with error indicator
                    try:
                        client.reactions_add(
                            channel=channel,
                            timestamp=message_ts,
                            name="x"
                        )
                    except:
                        pass
            
            elif channel and message_ts:
                # No PR link found - react with question mark
                try:
                    client.reactions_add(
                        channel=channel,
                        timestamp=message_ts,
                        name="question"
                    )
                except SlackApiError as e:
                    if _is_already_reacted(e.response.get("error")):
                        print(f"Already processed (reaction exists), skipping")
                    # Silently ignore other reaction errors
                except:
                    pass

        # Cancel pending reminders on :approved: reaction
        elif etype == "reaction_added":
            if ev.get("reaction") == "approved":
                item = ev.get("item", {})
                if item.get("type") == "message":
                    channel = item.get("channel")
                    original_ts = item.get("ts")
                    if channel and original_ts:
                        try:
                            _delete_scheduled_nudges_for_thread(channel, original_ts)
                        except SlackApiError as e:
                            print(f"delete scheduled error: {e}")

    return {"statusCode": 200, "body": ""}

if __name__ == "__main__":
    # Debug entry point - simulates EventBridge trigger
    lambda_handler({"source": "aws.events", "detail-type": "Scheduled Event"}, None)