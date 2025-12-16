# Troubleshooting: No Events Reaching Lambda

Your Lambda is not being invoked when posting PR links. Here's the checklist:

## 1. App Mentions Setup (Current Approach)

Go to https://api.slack.com/apps → Your App → Event Subscriptions

**Required Settings:**
- ✅ Enable Events: **ON**
- ✅ Request URL: `https://t1sjxesq9g.execute-api.ap-southeast-2.amazonaws.com/slack/events`
- ✅ Status should show: **Verified ✓**

**Subscribe to bot events:**
- `app_mention` (required - triggers when users @mention the bot)
- `reaction_added` (required - triggers when emoji added for cancellation)

**NO App Unfurl Domains needed** - we parse URLs from the message text directly

## 2. Verify OAuth Scopes

Go to OAuth & Permissions → Scopes

**Required Bot Token Scopes:**
- `app_mentions:read` - To receive mentions of the bot
- `chat:write` - To send scheduled messages
- `reactions:write` - To react with ✅/❌/❓ confirmation
- `reactions:read` - To detect :approved: reactions for cancellation

## 3. Reinstall App (if scopes changed)

If you just added scopes, you MUST reinstall:
- Go to Install App → Reinstall to Workspace
- This will generate a NEW token

## 4. Test Event Subscriptions Manually

In your Slack app settings → Event Subscriptions:
- Click "Resend" on the Request URL to verify it's working
- Should return your challenge string

## 5. Check if Bot is in Channel

- In Slack channel, type: `/invite @YourBotName`
- Or go to channel Details → Integrations → Add apps

## Common Issues:

**Issue**: Events not reaching Lambda
**Fix**: Request URL not verified OR bot not invited to channel

**Issue**: url_verification challenge failing
**Fix**: Check signature verification - may need to temporarily disable for testing

**Issue**: link_shared events not firing
**Fix**: Missing `links:read` scope OR `github.com` not in App Unfurl Domains
