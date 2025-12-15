# CI/CD Deployment Guide

This guide explains how to deploy the PR Reminder Slack Bot using CI/CD pipelines.

## Prerequisites

### 1. Create S3 Bucket for Terraform State

```bash
# Create S3 bucket
aws s3 mb s3://your-terraform-state-bucket --region us-east-1

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket your-terraform-state-bucket \
  --versioning-configuration Status=Enabled

# Enable encryption
aws s3api put-bucket-encryption \
  --bucket your-terraform-state-bucket \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'
```

### 2. Create DynamoDB Table for State Locking

```bash
aws dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

### 3. Create IAM Role for GitHub Actions (OIDC)

```bash
# Create trust policy file
cat > trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_USERNAME/pr-reminder-slack-bot:*"
        }
      }
    }
  ]
}
EOF

# Create the role
aws iam create-role \
  --role-name GitHubActionsRole \
  --assume-role-policy-document file://trust-policy.json

# Attach necessary policies
aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/PowerUserAccess
```

## GitHub Secrets Configuration

Go to your GitHub repository → Settings → Secrets and variables → Actions

### Required Secrets

```
AWS_ROLE_ARN             = arn:aws:iam::YOUR_ACCOUNT_ID:role/GitHubActionsRole
TF_STATE_BUCKET          = your-terraform-state-bucket
TF_STATE_LOCK_TABLE      = terraform-state-lock
SLACK_BOT_TOKEN          = xoxb-your-slack-bot-token
SLACK_SIGNING_SECRET     = your-slack-signing-secret
SLACK_CHANNEL_ID         = C04BM708T9N
```

### Optional Variables

```
WINDOW_SIZE              = 2
```

## Alternative: Using AWS Access Keys (Less Secure)

If you can't use OIDC, you can use access keys:

### Create IAM User

```bash
aws iam create-user --user-name github-actions-terraform

# Attach policies
aws iam attach-user-policy \
  --user-name github-actions-terraform \
  --policy-arn arn:aws:iam::aws:policy/PowerUserAccess

# Create access keys
aws iam create-access-key --user-name github-actions-terraform
```

### Add to GitHub Secrets

```
AWS_ACCESS_KEY_ID        = AKIA...
AWS_SECRET_ACCESS_KEY    = your-secret-key
```

### Update Workflow

In `.github/workflows/terraform.yml`, comment out OIDC and uncomment access key section.

## Deployment Flow

### Pull Request
1. Triggered on PR to `main` branch
2. Runs `terraform fmt`, `init`, `validate`, `plan`
3. Posts plan as PR comment
4. No apply happens

### Merge to Main
1. Triggered on push to `main` branch
2. Runs full validation
3. Automatically applies changes
4. Outputs the Slack Events URL

## Local Development with Remote State

Update `terraform/backend.hcl.example` with your values and rename to `backend.hcl`:

```bash
cd terraform
cp backend.hcl.example backend.hcl
# Edit backend.hcl with your bucket name

# Initialize with backend config
terraform init -backend-config=backend.hcl

# Deploy locally
terraform apply \
  -var="slack_bot_token=${SLACK_BOT_TOKEN}" \
  -var="slack_signing_secret=${SLACK_SIGNING_SECRET}" \
  -var="channel_id=${SLACK_CHANNEL_ID}" \
  -var="aws_profile=personal"
```

## Environment Variables Method

For CI/CD or local development, you can use environment variables:

```bash
export TF_VAR_slack_bot_token="xoxb-..."
export TF_VAR_slack_signing_secret="..."
export TF_VAR_channel_id="C04BM708T9N"
export TF_VAR_aws_region="us-east-1"

cd terraform
terraform init -backend-config=backend.hcl
terraform apply
```

## Monitoring Deployments

### View GitHub Actions
- Go to your repository → Actions tab
- Click on the workflow run
- View logs for each step

### View Terraform State
```bash
aws s3 ls s3://your-terraform-state-bucket/pr-reminder-bot/
```

### Check Lambda Function
```bash
aws lambda get-function --function-name pr-reminder-slack-bot
```

## Troubleshooting

### State Lock Issues
If deployment fails with state lock error:

```bash
# List locks
aws dynamodb scan --table-name terraform-state-lock

# Force unlock (use with caution)
terraform force-unlock LOCK_ID
```

### Backend Configuration Error
```bash
# Re-initialize backend
terraform init -reconfigure -backend-config=backend.hcl
```

### Permission Denied
Verify IAM role/user has necessary permissions:
- Lambda: CreateFunction, UpdateFunctionCode
- API Gateway: CreateApi, CreateStage
- EventBridge: PutRule, PutTargets
- IAM: CreateRole, AttachRolePolicy

## Best Practices

1. **Always use remote state** in team environments
2. **Enable state locking** to prevent concurrent modifications
3. **Use OIDC over access keys** for better security
4. **Store all secrets** in GitHub Secrets, never in code
5. **Review plans** in PR comments before merging
6. **Tag resources** for cost tracking and management
7. **Enable CloudWatch Logs** for debugging
8. **Use separate environments** (dev/staging/prod) with different backends

## GitLab CI/CD Alternative

If using GitLab, create `.gitlab-ci.yml`:

```yaml
variables:
  TF_VERSION: "1.6"
  TF_ROOT: ${CI_PROJECT_DIR}/terraform

stages:
  - validate
  - plan
  - apply

terraform-validate:
  stage: validate
  image: hashicorp/terraform:${TF_VERSION}
  script:
    - cd ${TF_ROOT}
    - terraform init
    - terraform validate
  only:
    - merge_requests
    - main

terraform-plan:
  stage: plan
  image: hashicorp/terraform:${TF_VERSION}
  script:
    - cd ${TF_ROOT}
    - terraform init
    - terraform plan -out=tfplan
  artifacts:
    paths:
      - ${TF_ROOT}/tfplan
  only:
    - merge_requests
    - main

terraform-apply:
  stage: apply
  image: hashicorp/terraform:${TF_VERSION}
  script:
    - cd ${TF_ROOT}
    - terraform init
    - terraform apply -auto-approve tfplan
  dependencies:
    - terraform-plan
  only:
    - main
  when: manual
```
