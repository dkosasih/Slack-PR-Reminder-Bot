import os, re, time, hmac, hashlib, json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from slack_sdk.web import WebClient
from slack_sdk.errors import SlackApiError

# Required env vars
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]

# Optional config
CHANNEL_ID = os.environ.get("CHANNEL_ID")  # used by the daily top-up path
WINDOW_SIZE = int(os.environ.get("WINDOW_SIZE", "2"))  # how many future reminders per PR thread
MEL_TZ = ZoneInfo("Australia/Melbourne")

# Slack client and patterns
client = WebClient(token=SLACK_BOT_TOKEN)

PR_RE = re.compile(r"https?://github\.com/[^/\s]+/[^/\s]+/pull/\d+")
MARKER_RE = re.compile(r"\[PR-NUDGE ts=([0-9]+\.[0-9]+)\]")
MARKER_FMT = "[PR-NUDGE ts={}]"

REMINDER_TEXT = os.environ.get(
    "REMINDER_TEXT",
    "Friendly nudge: no emoji reaction yet on this PR. React with 👀 if you’re taking it; ✅ when approved; 🎉 when merged. Thanks!"
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

def _is_pr_links(links: list[dict]) -> bool:
    return any(PR_RE.search(l.get("url", "")) for l in links)

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

def _schedule_nudge(channel: str, thread_ts: str, post_at: int, original_ts: str):
    marker = MARKER_FMT.format(original_ts)
    client.chat_scheduleMessage(
        channel=channel,
        text=f"{marker} {REMINDER_TEXT}",
        post_at=post_at,
        thread_ts=thread_ts,
        reply_broadcast=True
    )

def _get_existing_scheduled_times_for_thread(channel: str, original_ts: str) -> set[int]:
    """Get all existing scheduled times for a specific PR thread"""
    existing_times = set()
    marker = MARKER_FMT.format(original_ts)
    cursor = None
    
    while True:
        resp = client.chat_scheduledMessages_list(channel=channel, limit=100, cursor=cursor)
        for item in resp.get("scheduled_messages", []):
            if marker in (item.get("text") or ""):
                existing_times.add(int(item.get("post_at")))
        cursor = (resp.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break
    
    return existing_times

def _schedule_nudge_if_not_exists(channel: str, thread_ts: str, post_at: int, original_ts: str, existing_times: set[int]) -> bool:
    """Schedule a nudge only if no message is already scheduled for that time"""
    if post_at not in existing_times:
        _schedule_nudge(channel, thread_ts, post_at, original_ts)
        existing_times.add(post_at)  # Update the set to prevent future duplicates in same batch
        return True
    return False

def _delete_scheduled_nudges_for_thread(channel: str, original_ts: str):
    # Cancel all scheduled messages for this PR thread by matching the marker
    cursor = None
    marker = MARKER_FMT.format(original_ts)
    while True:
        resp = client.chat_scheduledMessages_list(channel=channel, limit=100, cursor=cursor)
        for item in resp.get("scheduled_messages", []):
            if marker in (item.get("text") or ""):
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

def _top_up_window_for_channel(channel: str):
    """
    Maintain a rolling window of WINDOW_SIZE future reminders for each PR thread,
    identified by the marker [PR-NUDGE ts=<original_ts>].
    """
    if not channel:
        return

    groups: dict[str, list[int]] = {}  # original_ts -> list[post_at]
    cursor = None
    while True:
        resp = client.chat_scheduledMessages_list(channel=channel, limit=100, cursor=cursor)
        for item in resp.get("scheduled_messages", []):
            text = item.get("text", "") or ""
            m = MARKER_RE.search(text)
            if not m:
                continue
            original_ts = m.group(1)
            post_at = int(item.get("post_at"))
            groups.setdefault(original_ts, []).append(post_at)
        cursor = (resp.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break

    for original_ts, post_ats in groups.items():
        post_ats.sort()
        while len(post_ats) < WINDOW_SIZE:
            base = post_ats[-1] if post_ats else _next_business_day_10am_mel_from_epoch(float(original_ts))
            next_pa = _next_business_day_10am_after(base)
            try:
                _schedule_nudge(channel, original_ts, next_pa, original_ts)
                post_ats.append(next_pa)
            except SlackApiError as e:
                print(f"top-up schedule failed: {e}")
                break

def lambda_handler(event, context):
    print(f"Received event: {json.dumps(event)}")  # Debug logging
    
    # EventBridge scheduled top-up branch
    if event.get("source") == "aws.events":
        try:
            _top_up_window_for_channel(CHANNEL_ID)  # type: ignore[arg-type]
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
            user = ev.get("user")
            
            print(f"app_mention event - Channel: {channel}, Text: {text}")  # Debug logging
            
            # Extract PR URLs from text (works with both plain URLs and markdown links)
            pr_match = PR_RE.search(text)
            
            if pr_match and channel and message_ts:
                pr_url = pr_match.group(0)
                print(f"Found PR URL: {pr_url}")
                
                try:
                    # React to confirm we received it
                    client.reactions_add(
                        channel=channel,
                        timestamp=message_ts,
                        name="white_check_mark"
                    )
                    
                    # Schedule reminders for this message
                    base_ts = float(message_ts)
                    existing_times = _get_existing_scheduled_times_for_thread(channel, message_ts)
                    
                    first = _next_business_day_10am_mel_from_epoch(base_ts)
                    _schedule_nudge_if_not_exists(channel, message_ts, first, message_ts, existing_times)
                    
                    # Add 5 more hours from first
                    first_plus_5h = first + (5 * 60 * 60)
                    _schedule_nudge_if_not_exists(channel, message_ts, first_plus_5h, message_ts, existing_times)
                    
                    cursor_pa = first
                    for _ in range(WINDOW_SIZE - 1):
                        cursor_pa = _next_business_day_10am_after(cursor_pa)
                        _schedule_nudge_if_not_exists(channel, message_ts, cursor_pa, message_ts, existing_times)
                        
                        # Add 5 more hours from each subsequent day
                        cursor_pa_plus_5h = cursor_pa + (5 * 60 * 60)
                        _schedule_nudge_if_not_exists(channel, message_ts, cursor_pa_plus_5h, message_ts, existing_times)
                    
                    print(f"Scheduled reminders for PR: {pr_url}")
                    
                except SlackApiError as e:
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