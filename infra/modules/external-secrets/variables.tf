variable "project" {
  type        = string
  description = "Project name"
}

variable "environment" {
  type        = string
  description = "Environment (e.g. sandbox, prod)"
}

variable "tags" {
  type        = map(string)
  description = "Tags for resources"
  default     = {}
}

variable "eks_cluster_name" {
  type        = string
  description = "Name of the EKS cluster"
}

variable "eks_oidc_provider_arn" {
  type        = string
  description = "ARN of the EKS OIDC Provider for IRSA"
}

variable "aws_region" {
  type        = string
  description = "AWS region"
}

variable "helm_namespace" {
  type        = string
  description = "Namespace to install External Secrets Operator"
  default     = "external-secrets"
}

variable "helm_chart_version" {
  type        = string
  description = "Version of the external-secrets helm chart"
  default     = "0.9.18"
}
