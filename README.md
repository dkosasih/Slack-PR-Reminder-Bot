# PR Reminder Slack Bot

A Slack bot that automatically sends periodic reminders for GitHub Pull Requests during business hours, helping teams stay on top of code reviews.

## Table of Contents

- [Overview](#overview)
- [How to Use](#how-to-use)
  - [Setting Up Reminders](#setting-up-reminders)
  - [Cancelling Reminders](#cancelling-reminders)
- [How It Works](#how-it-works)
  - [Scheduling Logic](#scheduling-logic)
  - [Business Hours](#business-hours)
  - [Automatic Top-Up](#automatic-top-up)
- [Configuration](#configuration)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)

---

## Overview

This bot monitors Slack channels for GitHub PR links and automatically schedules reminders at regular intervals during business hours (9am-5pm weekdays). When someone reacts to or approves a PR, you can cancel the reminders by mentioning the bot in the thread.

**Key Features:**
- 🕐 Interval-based reminders (default: every 3 hours)
- 📅 Business hours only (9am-5pm, Mon-Fri)
- 🌏 Melbourne timezone (AEDT/AEST)
- 🔄 Automatic maintenance via EventBridge
- 🔗 Clickable PR links in reminders
- ✅ Easy cancellation with `:approved:` reaction

---

## How to Use

### Setting Up Reminders

**1. Mention the bot with a PR link:**

```
@PR-Reminder https://github.com/example/repo/pull/123
```

**2. The bot will:**
- React with ✅ to confirm it received your message
- Schedule reminders every 3 hours during business hours
- Maintain reminders for the next 2 business days (configurable)

**3. Reminders will appear in the thread:**
```
Friendly nudge: no emoji reaction yet on this PR. 
React with 👀 if you're taking it; mention me in the thread 
with :approved: emoji when approved. Thanks!
```

The text "this PR" will be a clickable link to your GitHub PR.

### Cancelling Reminders

When the PR is approved or no longer needs reminders:

**Option 1: Reply in thread with :approved: emoji**
```
@PR-Reminder :approved:
```

**Option 2: Just type the emoji**
```
@PR-Reminder approved
```

**Option 3: Add `:approved:` reaction to the original message**
Currently not supported due to limited permission.

The bot will:
- ✅ React with a checkmark to confirm cancellation
- Delete all scheduled reminders for that PR
- Stop sending future reminders

**If no reminders exist or no link in the mention:**
- ❓ React with a question mark to indicate nothing was found

---

## How It Works

### Scheduling Logic

#### Initial Setup (When PR is First Mentioned)

1. **Find Next Business Hour Slot**
   - If message sent at 8am Monday → First reminder at 9am Monday
   - If message sent at 2pm Monday → First reminder at 5pm Monday (if 3h interval)
   - If message sent at 6pm Monday → First reminder at 9am Tuesday
   - If message sent on Saturday → First reminder at 9am Monday

2. **Schedule Reminders at Intervals**
   - Default: Every 3 hours during business hours
   - Example with 3-hour interval:
     ```
     Monday:   9am → 12pm → 3pm
     Tuesday:  9am → 12pm → 3pm
     Wednesday: 9am → 12pm → 3pm
     ```

3. **Coverage Window**
   - Default: 2 business days ahead
   - Reminders are scheduled to cover this rolling window

#### Interval Calculation

The bot adds the configured interval (default 3 hours) and adjusts based on business hours:

**Example Scenarios (3-hour interval):**

| Current Time | Next Reminder | Reason |
|--------------|---------------|--------|
| Monday 9am   | Monday 12pm   | Within business hours |
| Monday 3pm   | Tuesday 9am   | 3pm + 3h = 6pm (past 5pm) → next day |
| Friday 4pm   | Monday 9am    | 4pm + 3h = 7pm → skip weekend |
| Tuesday 11am | Tuesday 2pm   | Within business hours |

**Business Hours Rules:**
- Hours: 9am - 5pm (17:00)
- Days: Monday - Friday
- Timezone: Australia/Melbourne
- Reminders pause overnight and on weekends
- Resume at 9am next business day

### Automatic Top-Up

**EventBridge Daily Trigger** (runs at 12:05am UTC daily):

1. **Scans** all scheduled reminder messages across all channels
2. **Groups** by PR thread
3. **Calculates** if coverage extends through target window (WINDOW_SIZE business days)
4. **Schedules** additional reminders if needed to maintain coverage

This ensures reminders continue indefinitely until cancelled.

### Cancellation Process

**When `:approved:` is detected in a thread:**

1. **Search** for scheduled messages matching that thread
2. **Delete** all matching scheduled messages
3. **React** with ✅ to confirm
4. **Handle retries** - If Slack retries the event, bot detects existing ✅ and skips

**Duplicate Prevention:**
- Bot checks for existing ✅ reaction before adding ❓
- Uses `already_reacted` error handling from Slack API
- Handles Slack event retries gracefully (when Lambda takes >3s to respond)

### Message Format

**Marker (hidden from users):**
```
[PR-NUDGE ts=1234567890.123456 url=https://github.com/org/repo/pull/123]
```

**Reminder Text:**
```
Friendly nudge: no emoji reaction yet on <https://github.com/org/repo/pull/123|this PR>. 
React with 👀 if you're taking it; mention me in the thread with :approved: emoji when approved. Thanks!
```

The marker allows the bot to:
- Identify which thread a reminder belongs to
- Extract the PR URL for clickable links
- Group reminders by thread for cancellation

---

## Configuration

### Environment Variables

Configure via Terraform variables or environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `WINDOW_SIZE` | `2` | Number of business days to maintain reminders |
| `REMINDER_INTERVAL_HOURS` | `3` | Hours between reminders during business hours |
| `BUSINESS_HOURS_START` | `9` | Start hour (24-hour format) |
| `BUSINESS_HOURS_END` | `17` | End hour (24-hour format) |
| `REMINDER_TEXT` | See default | Custom reminder message text |

### Terraform Configuration

Edit [terraform/variables.tf](terraform/variables.tf):

```hcl
variable "window_size" {
  default = 2  # Days
}

variable "reminder_interval_hours" {
  default = 3  # Hours
}

variable "business_hours_start" {
  default = 9  # 9am
}

variable "business_hours_end" {
  default = 17  # 5pm
}
```

### Customizing Reminder Text

The default reminder text can be customized via the `REMINDER_TEXT` environment variable:

```bash
export REMINDER_TEXT="Hey team! This PR still needs review. Please take a look when you can!"
```

**Important:** If you customize the text and want the PR link to be clickable, include the phrase "this PR" in your text. The bot will replace "this PR" with a clickable link.

---

## Examples

### Example 1: Standard PR Reminder Flow

**Monday 10:30am - User posts PR:**
```
@PR Reminder Bot https://github.com/myorg/myrepo/pull/456
```

**Bot schedules reminders:**
```
Monday:    1:30pm, 4:30pm
Tuesday:   9:00am, 12:00pm, 3:00pm
Wednesday: 9:00am, 12:00pm, 3:00pm
```

**Tuesday 2pm - PR approved:**
```
@PR Reminder Bot :approved:
```

**Bot response:**
- ✅ Reaction added to message
- All remaining reminders cancelled
- No more reminders sent

### Example 2: After-Hours PR

**Friday 5:30pm - User posts PR:**
```
@PR Reminder Bot https://github.com/myorg/backend/pull/789
```

**Bot schedules reminders (skips weekend):**
```
Monday:   9:00am, 12:00pm, 3:00pm
Tuesday:  9:00am, 12:00pm, 3:00pm
```

### Example 3: False Cancellation Attempt

**User tries to cancel non-existent reminders:**
```
@PR Reminder Bot :approved:
```

**Bot response:**
- ❓ Reaction added (indicating no reminders found)
- No cancellation performed

### Example 4: Different Interval (1 hour)

**Configuration:**
```bash
REMINDER_INTERVAL_HOURS=1
```

**Monday 9am - Reminder schedule:**
```
Monday:    10am, 11am, 12pm, 1pm, 2pm, 3pm, 4pm
Tuesday:   9am, 10am, 11am, 12pm, 1pm, 2pm, 3pm, 4pm
```

---

## Troubleshooting

### Bot doesn't respond to PR mention

**Check:**
1. Bot is mentioned with `@PR Reminder Bot` (use actual bot name)
2. Message contains valid GitHub PR URL
3. Lambda function is deployed and accessible
4. CloudWatch logs: `/aws/lambda/pr-reminder-slack-bot`

**Expected behavior:**
- Bot reacts with ✅ within seconds
- Check scheduled messages with [check_scheduled_messages.py](check_scheduled_messages.py)

### Cancellation not working

**Check:**
1. `:approved:` is in a thread reply (not a new message)
2. Thread has actual scheduled reminders
3. Check CloudWatch logs for errors

**Expected behavior:**
- Bot reacts with ✅ if reminders cancelled
- Bot reacts with ❓ if no reminders found

### Reminders appearing at wrong times

**Verify:**
1. Timezone is set to `Australia/Melbourne`
2. Business hours configuration: `BUSINESS_HOURS_START=9`, `BUSINESS_HOURS_END=17`
3. Interval: `REMINDER_INTERVAL_HOURS=3`

**Test locally:**
```bash
python test_scheduling_logic.py
```

### Duplicate reminders or reactions

**Cause:** Slack retries events when Lambda takes >3 seconds

**Bot handles this automatically:**
- Checks for existing reactions before adding
- Uses `already_reacted` error handling
- Deduplicates event IDs within container lifetime

**If persisting:**
- Check Lambda timeout setting (should be 15s)
- Check Lambda memory (should be 256MB+)
- Review CloudWatch logs for retry patterns

### Reminders stop after a few days

**Check EventBridge:**
```bash
aws events list-rules --region ap-southeast-2 --profile personal
```

**Expected:**
- Rule: `pr-reminder-slack-bot-daily-topup`
- Schedule: `cron(5 0 * * ? *)` (daily at 12:05am UTC)
- State: `ENABLED`

**Verify top-up is running:**
- Check CloudWatch logs around 11am Melbourne time
- Look for "Topping up channel" messages

### No reminders scheduled

**Check:**
```bash
python check_scheduled_messages.py
```

**Common issues:**
1. PR URL not recognized (must be `https://github.com/org/repo/pull/123` format)
2. Lambda function error (check CloudWatch logs)
3. Slack API permissions (bot needs `chat:write`, `reactions:write`, `chat:write.public`)

---

## Architecture

```
┌─────────────┐
│   Slack     │
│   Message   │
└──────┬──────┘
       │
       │ Webhook (API Gateway)
       ▼
┌─────────────────────────────┐
│     AWS Lambda Function     │
│  ┌──────────────────────┐  │
│  │   Event Handler      │  │
│  │  - Parse PR URL      │  │
│  │  - Schedule reminders│  │
│  │  - Cancel reminders  │  │
│  └──────────────────────┘  │
└──────┬──────────────────────┘
       │
       │ Scheduled Messages API
       ▼
┌─────────────────┐
│  Slack Platform │
│  (Scheduled Msg)│
└─────────────────┘

┌─────────────────┐
│  EventBridge    │ ◄─── Daily trigger (12:05am UTC)
│  (Cron Job)     │
└────────┬────────┘
         │
         │ Invoke Lambda
         ▼
    Top-up process
    (Maintain window)
```

---

## Deployment

See [README_DEPLOY.md](README_DEPLOY.md) for deployment instructions.

---

## Testing

### Test Scheduling Logic

```bash
python test_scheduling_logic.py
```

### Check Scheduled Messages

```bash
python check_scheduled_messages.py
```

### Check Lambda Logs

```bash
python check_lambda_logs.py
```

Or via AWS CLI:
```bash
aws logs tail /aws/lambda/pr-reminder-slack-bot --follow --region ap-southeast-2 --profile personal
```

---

## License

MIT License - See LICENSE file for details.

---

## Support

For issues or questions:
1. Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
2. Review CloudWatch logs
3. Test locally with provided scripts
4. Check Slack API permissions
