output "state_bucket_name" {
  description = "Name of the S3 bucket for Terraform state"
  value       = aws_s3_bucket.terraform_state.id
}

output "state_bucket_arn" {
  description = "ARN of the S3 bucket for Terraform state"
  value       = aws_s3_bucket.terraform_state.arn
}

output "lock_table_name" {
  description = "Name of the DynamoDB table for state locking"
  value       = aws_dynamodb_table.terraform_locks.id
}

output "lock_table_arn" {
  description = "ARN of the DynamoDB table for state locking"
  value       = aws_dynamodb_table.terraform_locks.arn
}

output "backend_config" {
  description = "Backend configuration to use in your main Terraform project"
  value = <<-EOT
    Backend Configuration:
    
    Create terraform/backend.hcl with:
    
    bucket         = "${aws_s3_bucket.terraform_state.id}"
    key            = "pr-reminder-bot/terraform.tfstate"
    region         = "${var.aws_region}"
    dynamodb_table = "${aws_dynamodb_table.terraform_locks.id}"
    encrypt        = true
    
    Then run: terraform init -backend-config=backend.hcl
  EOT
}
