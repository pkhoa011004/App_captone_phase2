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
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
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
