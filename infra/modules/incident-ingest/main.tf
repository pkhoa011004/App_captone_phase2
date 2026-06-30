data "aws_partition" "current" {}

# 1. Tạo SQS FIFO Queue
resource "aws_sqs_queue" "incident_queue" {
  name                        = "${var.prefix}-incident-queue.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  visibility_timeout_seconds  = var.sqs_visibility_timeout
  tags                        = var.tags
}

# 2. Tạo IAM Role & Quyền cho Lambda ghi SQS
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ingest_lambda_role" {
  name               = "${var.prefix}-ingest-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.ingest_lambda_role.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_sqs_policy" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.incident_queue.arn]
  }
}

resource "aws_iam_policy" "lambda_sqs" {
  name   = "${var.prefix}-lambda-sqs-policy"
  policy = data.aws_iam_policy_document.lambda_sqs_policy.json
}

resource "aws_iam_role_policy_attachment" "lambda_sqs_attach" {
  role       = aws_iam_role.ingest_lambda_role.name
  policy_arn = aws_iam_policy.lambda_sqs.arn
}

# 3. Đóng gói (Zip) Code Lambda tự động bằng Terraform
data "archive_file" "ingest_lambda_zip" {
  type        = "zip"
  source_dir  = var.lambda_source_dir
  output_path = var.lambda_zip_output_path
}

# 4. Triển khai AWS Lambda Function
resource "aws_lambda_function" "ingest_lambda" {
  filename         = data.archive_file.ingest_lambda_zip.output_path
  function_name    = "${var.prefix}-ingest-webhook"
  role             = aws_iam_role.ingest_lambda_role.arn
  handler          = var.lambda_handler
  runtime          = var.lambda_runtime
  source_code_hash = data.archive_file.ingest_lambda_zip.output_base64sha256

  environment {
    variables = {
      SQS_QUEUE_URL = aws_sqs_queue.incident_queue.url
    }
  }
  tags = var.tags
}

# 5. Tạo Function URL (API Gateway siêu nhẹ) để public webhook ra ngoài
resource "aws_lambda_function_url" "ingest_webhook_url" {
  function_name      = aws_lambda_function.ingest_lambda.function_name
  authorization_type = "NONE" # Mở public cho Alertmanager gọi (Thực tế nên cài Auth)
}

resource "aws_lambda_permission" "public_invoke" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.ingest_lambda.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

# 6. Tạo API Gateway HTTP API
resource "aws_apigatewayv2_api" "ingest_api" {
  name          = "${var.prefix}-ingest-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda_integration" {
  api_id           = aws_apigatewayv2_api.ingest_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.ingest_lambda.invoke_arn
}

resource "aws_apigatewayv2_route" "default_route" {
  api_id    = aws_apigatewayv2_api.ingest_api.id
  route_key = "POST /"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

resource "aws_apigatewayv2_stage" "default_stage" {
  api_id      = aws_apigatewayv2_api.ingest_api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "apigw_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ingest_api.execution_arn}/*/*"
}

resource "aws_ssm_parameter" "sqs_queue_url" {
  name  = "${var.ssm_parameter_prefix}/sqs_queue_url"
  type  = "String"
  value = aws_sqs_queue.incident_queue.url
}

resource "aws_ssm_parameter" "alertmanager_webhook_url" {
  name  = "${var.ssm_parameter_prefix}/alertmanager_webhook_url"
  type  = "String"
  value = aws_apigatewayv2_api.ingest_api.api_endpoint
}


