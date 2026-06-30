output "role_arn" {
  value       = aws_iam_role.this.arn
  description = "ARN of the CI IAM Role"
}

output "role_name" {
  value       = aws_iam_role.this.name
  description = "Name of the CI IAM Role"
}

output "provider_arn" {
  value       = aws_iam_openid_connect_provider.this.arn
  description = "ARN of the GitHub OIDC Provider"
}
