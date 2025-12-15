variable "aws_region" {
  description = "AWS region for state infrastructure"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS profile to use (optional)"
  type        = string
  default     = ""
}

variable "state_bucket_name" {
  description = "Name of the S3 bucket for Terraform state"
  type        = string
  # Must be globally unique
  # Example: "mycompany-terraform-state" or "pr-reminder-tf-state-123456"
}

variable "lock_table_name" {
  description = "Name of the DynamoDB table for state locking"
  type        = string
  default     = "terraform-state-lock"
}
