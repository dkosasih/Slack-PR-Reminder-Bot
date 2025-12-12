# PR Reminder Slack Bot - Terraform Deployment

This directory contains Terraform configuration to deploy the PR Reminder Slack Bot to AWS.

## Prerequisites

- [Terraform](https://www.terraform.io/downloads.html) >= 1.0
- AWS CLI configured with credentials
- Slack Bot Token and Signing Secret

## Project Structure

```
terraform/
├── main.tf                    # Main Terraform configuration
├── variables.tf               # Variable definitions
├── outputs.tf                 # Output definitions
├── terraform.tfvars.example   # Example variables file
└── .gitignore                # Git ignore rules
```

## Quick Start

### 1. Configure Variables

Copy the example variables file and update with your values:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and set:
- `slack_bot_token` - Your Slack bot token (xoxb-...)
- `slack_signing_secret` - Your Slack signing secret
- `channel_id` - Your Slack channel ID
- `aws_profile` - Your AWS profile (default: personal)
- `aws_region` - AWS region (default: us-east-1)

### 2. Initialize Terraform

```bash
terraform init
```

### 3. Review the Deployment Plan

```bash
terraform plan
```

### 4. Deploy

```bash
terraform apply
```

Type `yes` when prompted to confirm deployment.

### 5. Get the Slack Events URL

After deployment, Terraform will output the Slack Events URL:

```bash
terraform output slack_events_url
```

Use this URL to configure your Slack app's Event Subscriptions.

## Configuration

### Required Variables

- `slack_bot_token` - Slack Bot Token (sensitive)
- `slack_signing_secret` - Slack app signing secret (sensitive)
- `channel_id` - Slack channel ID for scheduled top-ups

### Optional Variables

- `aws_region` - AWS region (default: us-east-1)
- `aws_profile` - AWS profile name (default: personal)
- `function_name` - Lambda function name (default: pr-reminder-slack-bot)
- `window_size` - Number of future reminders per PR (default: 2)
- `schedule_expression` - Cron expression for daily top-up (default: "cron(5 0 * * ? *)")
- `reminder_text` - Custom reminder message text
- `tags` - Resource tags

## Resources Created

- **Lambda Function** - Handles Slack events and schedules reminders
- **IAM Role** - Lambda execution role with CloudWatch Logs permissions
- **API Gateway HTTP API** - Receives Slack event webhooks
- **EventBridge Rule** - Triggers daily top-up job
- **CloudWatch Log Group** - Stores Lambda function logs

## Outputs

- `slack_events_url` - URL for Slack Event Subscriptions
- `lambda_function_name` - Name of the Lambda function
- `lambda_function_arn` - ARN of the Lambda function
- `api_gateway_id` - API Gateway ID
- `api_gateway_endpoint` - API Gateway endpoint
- `eventbridge_rule_name` - EventBridge rule name

## Updating the Deployment

After making changes to the Lambda code in the `src/` directory:

```bash
cd terraform
terraform apply
```

Terraform will detect the changes and update the Lambda function.

## Destroying Resources

To remove all deployed resources:

```bash
terraform destroy
```

Type `yes` when prompted to confirm deletion.

## Slack App Configuration

After deployment, configure your Slack app:

1. **Bot Token Scopes** (OAuth & Permissions):
   - `links:read`
   - `reactions:read`
   - `chat:write`

2. **Event Subscriptions**:
   - Enable Event Subscriptions
   - Request URL: Use the `slack_events_url` from Terraform outputs
   - Subscribe to bot events:
     - `link_shared`
     - `reaction_added`

3. **Install App**:
   - Install the app to your workspace
   - Add the bot to your private channel

## Troubleshooting

### View Lambda Logs

```bash
aws logs tail /aws/lambda/pr-reminder-slack-bot --follow --profile personal
```

### Test Lambda Function

```bash
aws lambda invoke \
  --function-name pr-reminder-slack-bot \
  --payload '{"source":"aws.events"}' \
  --profile personal \
  response.json
```

### Check API Gateway Endpoint

```bash
terraform output api_gateway_endpoint
```

## Security Notes

- Never commit `terraform.tfvars` to version control (it contains secrets)
- The Slack tokens are marked as sensitive in Terraform
- IAM role follows least-privilege principle
- API Gateway uses signature verification for security
