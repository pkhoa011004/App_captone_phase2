variable "project" { type = string }
variable "tags" {
  description = "Common resource tags"
  type        = map(string)
  default     = {}
}
variable "environment" {
  type = string
  validation {
    condition     = contains(["sandbox", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: sandbox, staging, prod"
  }
}

variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }

variable "cluster_name" { type = string }
variable "cluster_version" { type = string }

variable "instance_type" { type = string }
variable "scaling_config" {
  type = object({
    desired_size = number
    max_size     = number
    min_size     = number
  })
}

variable "admin_role_arn" {
  type    = string
  default = null
}
variable "devops_team_role_arn" {
  type    = string
  default = null
}
variable "backend_devs_role_arn" {
  type    = string
  default = null
}

variable "cluster_endpoint_public_access_cidrs" {
  description = "List of CIDR blocks which can access the Amazon EKS public API server endpoint"
  type        = list(string)
  default     = null
}
