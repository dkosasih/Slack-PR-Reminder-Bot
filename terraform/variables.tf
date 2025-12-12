variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS profile to use for deployment"
  type        = string
  default     = "personal"
}

variable "function_name" {
  description = "Name of the Lambda function"
  type        = string
  default     = "pr-reminder-slack-bot"
}

variable "slack_bot_token" {
  description = "Slack Bot Token (xoxb-...)"
  type        = string
  sensitive   = true
}

variable "slack_signing_secret" {
  description = "Slack app signing secret"
  type        = string
  sensitive   = true
}

variable "reminder_text" {
  description = "Text posted as the reminder in the PR thread"
  type        = string
  default     = "Friendly nudge: no emoji reaction yet on this PR. React with 👀 if you're taking it; ✅ when approved; 🎉 when merged. Thanks!"
}

variable "channel_id" {
  description = "Slack channel ID to maintain via scheduled top-ups"
  type        = string
}

variable "window_size" {
  description = "Number of future reminders to keep per PR thread (rolling window)"
  type        = number
  default     = 2
}

variable "schedule_expression" {
  description = "EventBridge schedule expression for daily top-up"
  type        = string
  default     = "cron(5 0 * * ? *)"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Project     = "PR Reminder Slack Bot"
    ManagedBy   = "Terraform"
  }
}
