variable "ci_role_arn" {
  description = "ARN of the CI/CD IAM role allowed to push images"
  type        = string
}

variable "repositories" {
  description = "List of ECR repository names to create"
  type        = list(string)
}

variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "image_tag_mutability" {
  type        = string
  description = "The tag mutability setting for the repository (MUTABLE or IMMUTABLE)"
  default     = "MUTABLE"
}

variable "tags" {
  type    = map(string)
  default = {}
}
