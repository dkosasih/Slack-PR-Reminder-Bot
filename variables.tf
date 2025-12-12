variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to use for deployment"
  type        = string
  default     = "personal"
}

variable "project_name" {
  description = "Project name used as prefix for resource names"
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
  description = "Slack channel ID to maintain via scheduled top-ups (e.g., C04BM708T9N)"
  type        = string
}

variable "window_size" {
  description = "Number of future reminders to keep per PR thread (rolling window)"
  type        = number
  default     = 2
}
