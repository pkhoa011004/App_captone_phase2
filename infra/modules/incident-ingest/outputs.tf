output "sqs_queue_url" {
  description = "URL of the Incident SQS FIFO Queue"
  value       = aws_sqs_queue.incident_queue.url
}

output "apigw_url" {
  description = "Public URL of the API Gateway (Webhook endpoint cho Alertmanager)"
  value       = aws_apigatewayv2_api.ingest_api.api_endpoint
}
