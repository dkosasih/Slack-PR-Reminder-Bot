# Troubleshooting: No Events Reaching Lambda

Your Lambda is not being invoked when posting PR links. Here's the checklist:

## 1. Verify Slack App Event Subscriptions

Go to https://api.slack.com/apps → Your App → Event Subscriptions

**Required Settings:**
- ✅ Enable Events: **ON**
- ✅ Request URL: `https://t1sjxesq9g.execute-api.ap-southeast-2.amazonaws.com/slack/events`
- ✅ Status should show: **Verified ✓**

**Subscribe to bot events:**
- `link_shared` (required - triggers when PR link posted)
- `reaction_added` (required - triggers when emoji added)

**App Unfurl Domains:**
- Add domain: `github.com`

## 2. Verify OAuth Scopes

Go to OAuth & Permissions → Scopes

**Required Bot Token Scopes:**
- `links:read` - To receive link_shared events
- `chat:write` - To send scheduled messages
- `chat:write.public` - To post in channels without being invited

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
