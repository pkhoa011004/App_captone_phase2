output "sqs_queue_url" {
  description = "URL of the Incident SQS FIFO Queue"
  value       = aws_sqs_queue.incident_queue.url
}

output "ingest_webhook_url" {
  description = "Public URL of the Ingest Lambda (Webhook endpoint cho Alertmanager)"
  value       = aws_lambda_function_url.ingest_webhook_url.function_url
}
