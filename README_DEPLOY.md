# Deployment Guide

## Consistent Terraform Deployment

All deployments (infrastructure and code changes) use Terraform for consistency.

### Initial Setup

```bash
# Set environment variables
export SLACK_BOT_TOKEN="xoxb-your-token"
export SLACK_SIGNING_SECRET="your-signing-secret"
export CHANNEL_ID="C0A0NDTCCES"
export AWS_PROFILE="personal"
export AWS_REGION="ap-southeast-2"

# Initial deployment
./deploy.sh
```

### Updating Lambda Code

When you change [src/handler.py](src/handler.py), just run the same deployment script:

```bash
./deploy.sh
```

The script will:
1. Build Lambda package with dependencies (`build_lambda.sh`)
2. Deploy with Terraform (detects code changes via `source_code_hash`)
3. Terraform automatically updates Lambda function

### Manual Terraform Commands

If you prefer more control:

```bash
cd terraform

# Build package
./build_lambda.sh

# Set environment variables
export TF_VAR_slack_bot_token="$SLACK_BOT_TOKEN"
export TF_VAR_slack_signing_secret="$SLACK_SIGNING_SECRET"
export TF_VAR_channel_id="$CHANNEL_ID"
export TF_VAR_aws_profile="personal"
export TF_VAR_aws_region="ap-southeast-2"

# Review changes
terraform plan

# Apply changes
terraform apply
```

### How It Works

- `filebase64sha256()` in [terraform/main.tf](terraform/main.tf) calculates hash of `lambda_function.zip`
- When `lambda_function.zip` changes, hash changes
- Terraform detects the change and updates Lambda function code
- No AWS CLI commands needed - pure Infrastructure as Code

### Pause/Resume Bot

**Pause (destroy API Gateway and EventBridge, keep Lambda):**
```bash
cd terraform
terraform destroy -target=aws_apigatewayv2_api.slack_api \
                  -target=aws_apigatewayv2_stage.default \
                  -target=aws_apigatewayv2_integration.lambda_integration \
                  -target=aws_apigatewayv2_route.events \
                  -target=aws_lambda_permission.api_gateway \
                  -target=aws_cloudwatch_event_rule.daily_topup \
                  -target=aws_cloudwatch_event_target.lambda \
                  -target=aws_lambda_permission.eventbridge
```

**Resume (rebuild everything):**
```bash
./deploy.sh
```

### Benefits of This Approach

✅ **Consistency**: All changes go through Terraform
✅ **Reproducibility**: State is tracked, can recreate anytime
✅ **No State Drift**: Terraform always knows actual state
✅ **Automated Detection**: Hash-based change detection
✅ **Version Control**: Infrastructure and code versioned together
