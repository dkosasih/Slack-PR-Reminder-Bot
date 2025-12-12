output "slack_events_url" {
  description = "Public HTTPS endpoint for Slack event subscriptions"
  value       = "${aws_apigatewayv2_api.slack_api.api_endpoint}/slack/events"
}

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.slack_events_function.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.slack_events_function.arn
}

output "api_gateway_id" {
  description = "ID of the API Gateway"
  value       = aws_apigatewayv2_api.slack_api.id
}

output "eventbridge_rule_name" {
  description = "Name of the EventBridge rule for daily top-up"
  value       = aws_cloudwatch_event_rule.daily_topup.name
}
