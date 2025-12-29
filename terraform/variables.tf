variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "ap-southeast-2"
}

variable "aws_profile" {
  description = "AWS profile to use for deployment (optional, uses default credentials chain if not set)"
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
  default     = "no emoji reaction yet on this PR. React with 👀 if you’re taking it; mention me in the thread with :approved: emoji when approved. Thanks!"
}

variable "window_size" {
  description = "Number of business days to maintain reminders for each PR (rolling window)"
  type        = number
  default     = 2
}

variable "reminder_interval_hours" {
  description = "Hours between reminders during business hours"
  type        = number
  default     = 3
}

variable "business_hours_start" {
  description = "Start of business hours (hour in 24-hour format)"
  type        = number
  default     = 9
}

variable "business_hours_end" {
  description = "End of business hours (hour in 24-hour format)"
  type        = number
  default     = 17
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
