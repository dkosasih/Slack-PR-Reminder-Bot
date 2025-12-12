# Journey Cash PR Nudge (Lambda + Daily Rolling-Window Top-Up)

A minimal-scope Slack app that nudges PR review threads in a private channel if no emoji reactions appear by the next business day 09:00 Melbourne—recurring indefinitely via a rolling window of scheduled messages. Reminders are cancelled only when the original PR message receives :approved:.

## Behavior
- On PR link posts (`link_shared`), the app schedules a thread reminder for the next business day 09:00 AET and seeds an additional (configurable) number of future reminders.
- A daily EventBridge schedule tops up each PR thread to keep a rolling window of scheduled reminders.
- When a reviewer adds `:approved:` to the original PR message, all pending reminders for that thread are deleted.
- No datastore; no history scans.

## Slack app configuration
- Bot Token Scopes:
  - `links:read`
  - `reactions:read`
  - `chat:write`
- Event Subscriptions:
  - Enable “Event Subscriptions”
  - Request URL: <SlackEventsUrl output>/slack/events
  - Subscribe to bot events:
    - `link_shared`
    - `reaction_added`
- Install the app to your workspace and add it to your private channel (e.g., `#pod-journey-cash-only`).
- Channel ID: find from Slack (e.g., `C04BM708T9N`) and pass as a SAM parameter.

## AWS deploy (SAM)
Prereqs: AWS CLI configured, AWS SAM CLI, Python 3.12.