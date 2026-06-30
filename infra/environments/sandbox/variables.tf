variable "project" {
  type    = string
  default = "xbrain-cdo5"
}

variable "environment" {
  type    = string
  default = "sandbox"
}

variable "aws_region" {
  type    = string
}

variable "tags" {
  type = map(string)
  default = {
    Project     = "xbrain-cdo5"
    Environment = "sandbox"
    ManagedBy   = "Terraform"
  }
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.3.0/24", "10.0.4.0/24"]
}



variable "cluster_version" {
  type    = string
  default = "1.29"
}

variable "instance_type" {
  type    = string
  default = "t3a.large"
}

variable "eks_scaling_config" {
  description = "Scaling configuration for EKS node group"
  type = object({
    min_size     = number
    max_size     = number
    desired_size = number
  })
  default = {
    min_size     = 1
    max_size     = 2
    desired_size = 1
  }
}

variable "github_repo" {
  type        = string
  description = "GitHub repository for the project (e.g., user/repo)"
  default     = "me-dangnhatminh/xbrain-capstone-cdo5"
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

variable "ecr_repositories" {
  type    = list(string)
  default = ["tf1-platform-service", "tf1-ai-engine", "tf1-simulator"]
}
