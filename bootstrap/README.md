# Terraform Bootstrap

This directory contains Terraform configuration to create the **remote state infrastructure** (S3 bucket and DynamoDB table) needed for the main application deployment.

## ⚠️ Run This FIRST (One Time Only)

You must deploy this bootstrap infrastructure **before** deploying the main application.

## What This Creates

1. **S3 Bucket** - Stores Terraform state files
   - Versioning enabled (keep history)
   - Encryption enabled (AES256)
   - Public access blocked
   - Lifecycle policy (cleanup old versions after 90 days)

2. **DynamoDB Table** - Prevents concurrent state modifications
   - Pay-per-request billing
   - Simple lock mechanism

## Quick Start

### 1. Configure Variables

```bash
cd bootstrap
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and set a **globally unique** bucket name:

```hcl
state_bucket_name = "yourname-pr-reminder-tf-state"
aws_region = "us-east-1"
aws_profile = "personal"  # Optional
```

### 2. Deploy Bootstrap Infrastructure

```bash
terraform init
terraform plan
terraform apply
```

### 3. Copy Backend Configuration

After successful deployment, Terraform will output the backend configuration:

```bash
terraform output -raw backend_config
```

Copy this configuration to create `../terraform/backend.hcl`

### 4. Initialize Main Application

```bash
cd ../terraform
terraform init -backend-config=backend.hcl
```

Now you can deploy your main application!

## Alternative: Use the Bootstrap Script

```bash
cd bootstrap
./bootstrap.sh
```

This script will:
1. Check for required variables
2. Deploy the infrastructure
3. Automatically create backend.hcl for you
4. Initialize the main Terraform project

## Environment Variables Method

```bash
export TF_VAR_state_bucket_name="yourname-pr-reminder-tf-state"
export TF_VAR_aws_region="us-east-1"
export TF_VAR_aws_profile="personal"

cd bootstrap
terraform init
terraform apply
```

## Important Notes

### Bucket Naming
- Must be **globally unique** across all AWS accounts
- Use lowercase letters, numbers, and hyphens only
- 3-63 characters long
- Good pattern: `{org}-{project}-tf-state-{random}`
- Example: `acme-pr-reminder-tf-state-a1b2c3`

### Cost
- **S3**: ~$0.023/GB/month (negligible for state files)
- **DynamoDB**: Pay per request (~$0.25/million requests)
- **Total**: Usually < $1/month

### State File Location
This bootstrap configuration uses **local state** (stored in `terraform.tfstate` file in this directory).

⚠️ **Keep this file safe!** It contains the information about your state infrastructure.

Consider:
- Committing it to a private git repo (it's not sensitive)
- Backing it up somewhere safe
- Or manually track the bucket and table names

### Destroying Bootstrap Infrastructure

⚠️ **Only do this if you want to destroy everything!**

```bash
# First, destroy the main application
cd ../terraform
terraform destroy

# Then destroy the bootstrap
cd ../bootstrap
terraform destroy
```

This will:
1. Delete the DynamoDB table
2. Delete all state file versions
3. Delete the S3 bucket

## Troubleshooting

### Bucket Already Exists
If you get "BucketAlreadyExists" error, the name is taken globally. Try a different name.

### Access Denied
Ensure your AWS credentials have permissions to:
- Create S3 buckets
- Create DynamoDB tables
- Manage S3 bucket policies and settings

### Can't Delete Bucket
If destroying fails due to bucket not being empty:

```bash
# Empty the bucket first
aws s3 rm s3://your-bucket-name --recursive

# Then try destroy again
terraform destroy
```

## Next Steps

After bootstrapping:

1. ✅ S3 bucket and DynamoDB table are created
2. ✅ Create `../terraform/backend.hcl` with the output configuration
3. ✅ Run `cd ../terraform && terraform init -backend-config=backend.hcl`
4. ✅ Deploy your application: `terraform apply`

Your remote state is now configured! All team members can share the same state file.
