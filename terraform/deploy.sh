#!/bin/bash
set -e

# PR Reminder Slack Bot - Deployment Script
# Uses Terraform for consistent infrastructure and code deployment

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check required environment variables
required_vars=("SLACK_BOT_TOKEN" "SLACK_SIGNING_SECRET" "CHANNEL_ID")
for var in "${required_vars[@]}"; do
  if [ -z "${!var}" ]; then
    echo "❌ Error: $var environment variable is not set"
    echo "Please set: export $var=your-value"
    exit 1
  fi
done

echo "🚀 Deploying PR Reminder Slack Bot..."

# Build Lambda package first
echo "📦 Building Lambda package..."
cd "$SCRIPT_DIR/"
./build_lambda.sh

# Set Terraform variables
export TF_VAR_slack_bot_token="${SLACK_BOT_TOKEN}"
export TF_VAR_slack_signing_secret="${SLACK_SIGNING_SECRET}"
export TF_VAR_channel_id="${CHANNEL_ID}"
export TF_VAR_aws_region="${AWS_REGION:-ap-southeast-2}"
export TF_VAR_aws_profile="${AWS_PROFILE:-personal}"
export TF_VAR_window_size="${WINDOW_SIZE:-2}"

echo "🔧 Deploying with Terraform..."
terraform apply -auto-approve

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📍 Slack Events URL:"
terraform output -raw slack_events_url
echo ""
