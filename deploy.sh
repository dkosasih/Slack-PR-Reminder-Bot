#!/bin/bash
set -e

# Deploy PR Reminder Slack Bot using environment variables
# Usage: ./deploy.sh

echo "🚀 Deploying PR Reminder Slack Bot..."

# Check required environment variables
required_vars=("SLACK_BOT_TOKEN" "SLACK_SIGNING_SECRET" "CHANNEL_ID")
for var in "${required_vars[@]}"; do
  if [ -z "${!var}" ]; then
    echo "❌ Error: $var environment variable is not set"
    echo "Please set: export $var=your-value"
    exit 1
  fi
done

# Set defaults
export TF_VAR_slack_bot_token="${SLACK_BOT_TOKEN}"
export TF_VAR_slack_signing_secret="${SLACK_SIGNING_SECRET}"
export TF_VAR_channel_id="${CHANNEL_ID}"
export TF_VAR_aws_region="${AWS_REGION:-us-east-1}"
export TF_VAR_aws_profile="${AWS_PROFILE:-personal}"
export TF_VAR_window_size="${WINDOW_SIZE:-2}"

cd terraform

echo "📦 Initializing Terraform..."
if [ -f "backend.hcl" ]; then
  terraform init -backend-config=backend.hcl
else
  echo "⚠️  No backend.hcl found, using local state"
  terraform init
fi

echo "✅ Validating configuration..."
terraform validate

echo "📋 Planning deployment..."
terraform plan -out=tfplan

echo ""
read -p "Apply these changes? (yes/no): " confirm
if [ "$confirm" = "yes" ]; then
  echo "🔧 Applying changes..."
  terraform apply tfplan
  
  echo ""
  echo "✅ Deployment complete!"
  echo ""
  echo "📍 Slack Events URL:"
  terraform output -raw slack_events_url
  echo ""
else
  echo "❌ Deployment cancelled"
  rm tfplan
  exit 1
fi
