variable "prefix" {
  type        = string
  description = "Prefix for resource naming"
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to resources"
  default     = {}
}

variable "lambda_source_dir" {
  type        = string
  description = "Path to the Lambda function source code directory"
}

variable "lambda_zip_output_path" {
  type        = string
  description = "Path where the zipped Lambda code should be saved"
}

variable "lambda_handler" {
  type        = string
  description = "The handler for the Lambda function"
  default     = "index.handler"
}

variable "lambda_runtime" {
  type        = string
  description = "The runtime for the Lambda function"
  default     = "python3.11"
}

variable "sqs_visibility_timeout" {
  type        = number
  description = "Visibility timeout for SQS in seconds"
  default     = 300
}

variable "ssm_parameter_prefix" {
  type        = string
  description = "Prefix for SSM Parameter names (e.g. /project/environment)"
}
