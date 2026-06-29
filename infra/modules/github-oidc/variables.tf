variable "github_provider_url" {
  type        = string
  description = "The URL of the GitHub OIDC provider"
  default     = "https://token.actions.githubusercontent.com"
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to resources"
  default     = {}
}

variable "role_name" {
  type        = string
  description = "Name of the IAM role for GitHub CI"
}

variable "github_repos" {
  type        = list(string)
  description = "List of GitHub repositories (org/repo) allowed to assume the role"
}

variable "policy_name" {
  type        = string
  description = "Name of the IAM policy for the CI role"
}

variable "policy_json" {
  type        = string
  description = "JSON document of the IAM policy to attach to the CI role"
}

variable "policy_description" {
  type        = string
  description = "Description for the IAM policy"
  default     = "IAM Policy for GitHub CI role"
}
