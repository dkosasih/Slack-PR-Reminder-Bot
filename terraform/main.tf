terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
  # Profile is optional - uses default AWS credentials chain
  # In CI/CD: uses IAM role from environment
  # Locally: uses profile from var.aws_profile if set
  profile = var.aws_profile != "" ? var.aws_profile : null
  
  default_tags {
    tags = var.tags
  }
}

# Data source to get current AWS account info
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Create deployment package
# Build Lambda package with dependencies using local exec
resource "null_resource" "lambda_build" {
  triggers = {
    handler_hash       = filemd5("${path.module}/../src/handler.py")
    requirements_hash  = filemd5("${path.module}/../requirements.txt")
  }

  provisioner "local-exec" {
    command     = "./build_lambda.sh"
    working_dir = path.module
  }
}

# IAM Role for Lambda
resource "aws_iam_role" "lambda_role" {
  name = "${var.function_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

# Attach basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Lambda Function
resource "aws_lambda_function" "slack_events" {
  depends_on       = [null_resource.lambda_build]
  filename         = "${path.module}/lambda_function.zip"
  function_name    = var.function_name
  role            = aws_iam_role.lambda_role.arn
  handler         = "handler.lambda_handler"
  source_code_hash = filebase64sha256("${path.module}/lambda_function.zip")
  runtime         = "python3.12"
  memory_size     = 256
  timeout         = 15
  
  # Limit concurrent executions to prevent bill shock
  reserved_concurrent_executions = 10

  environment {
    variables = {
      SLACK_BOT_TOKEN      = var.slack_bot_token
      SLACK_SIGNING_SECRET = var.slack_signing_secret
      REMINDER_TEXT        = var.reminder_text
      CHANNEL_ID          = var.channel_id
      WINDOW_SIZE         = var.window_size
    }
  }

  tags = var.tags
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = 7

  tags = var.tags
}

# API Gateway HTTP API
resource "aws_apigatewayv2_api" "slack_api" {
  name          = "${var.function_name}-api"
  protocol_type = "HTTP"
  description   = "API Gateway for Slack Events"

  tags = var.tags
}

# API Gateway Stage
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.slack_api.id
  name        = "$default"
  auto_deploy = true
  
  # Throttling settings to prevent abuse
  default_route_settings {
    throttling_burst_limit = 100   # Max requests in a burst
    throttling_rate_limit  = 50    # Sustained requests per second
  }

  tags = var.tags
}

# API Gateway Integration
resource "aws_apigatewayv2_integration" "lambda_integration" {
  api_id           = aws_apigatewayv2_api.slack_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.slack_events.invoke_arn
  payload_format_version = "2.0"
}

# API Gateway Route
resource "aws_apigatewayv2_route" "slack_route" {
  api_id    = aws_apigatewayv2_api.slack_api.id
  route_key = "POST /slack/events"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

# Lambda Permission for API Gateway
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.slack_events.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.slack_api.execution_arn}/*/*"
}

# EventBridge Rule for Daily Top-up
resource "aws_cloudwatch_event_rule" "daily_topup" {
  name                = "${var.function_name}-daily-topup"
  description         = "Daily top-up to maintain rolling window of scheduled PR nudges"
  schedule_expression = var.schedule_expression

  tags = var.tags
}

# EventBridge Target
resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.daily_topup.name
  target_id = "LambdaTarget"
  arn       = aws_lambda_function.slack_events.arn
}

# Lambda Permission for EventBridge
resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.slack_events.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_topup.arn
}

# CloudWatch Alarm for High Lambda Invocations
resource "aws_cloudwatch_metric_alarm" "high_invocations" {
  alarm_name          = "${var.function_name}-high-invocations"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name        = "Invocations"
  namespace          = "AWS/Lambda"
  period             = "300"  # 5 minutes
  statistic          = "Sum"
  threshold          = "1000"  # Alert if >1000 invocations in 5 min
  alarm_description  = "This metric monitors lambda invocations for potential abuse"
  treat_missing_data = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.slack_events.function_name
  }

  tags = var.tags
}

# CloudWatch Alarm for Lambda Errors
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${var.function_name}-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name        = "Errors"
  namespace          = "AWS/Lambda"
  period             = "300"
  statistic          = "Sum"
  threshold          = "10"
  alarm_description  = "This metric monitors lambda errors"
  treat_missing_data = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.slack_events.function_name
  }

  tags = var.tags
}

# CloudWatch Alarm for Lambda Throttles
resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  alarm_name          = "${var.function_name}-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name        = "Throttles"
  namespace          = "AWS/Lambda"
  period             = "60"
  statistic          = "Sum"
  threshold          = "5"
  alarm_description  = "This metric monitors lambda throttling events"
  treat_missing_data = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.slack_events.function_name
  }

  tags = var.tags
}
