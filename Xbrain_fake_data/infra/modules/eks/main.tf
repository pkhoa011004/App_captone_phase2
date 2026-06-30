data "aws_partition" "current" {}

locals {
  prefix = "${var.project}-${var.environment}"
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  iam_role_use_name_prefix = false

  enable_cluster_creator_admin_permissions = false

  cluster_endpoint_public_access       = true
  cluster_endpoint_private_access      = true
  cluster_endpoint_public_access_cidrs = var.cluster_endpoint_public_access_cidrs != null ? var.cluster_endpoint_public_access_cidrs : ["0.0.0.0/0"]

  vpc_id     = var.vpc_id
  subnet_ids = var.subnet_ids

  enable_irsa    = true
  create_kms_key = true
  cluster_encryption_config = {
    resources = ["secrets"]
  }

  cluster_addons = {
    coredns    = {}
    kube-proxy = {}
    vpc-cni    = {}
  }

  eks_managed_node_groups = {
    default = {
      name                     = "${local.prefix}-node-group"
      iam_role_use_name_prefix = false
      instance_types           = [var.instance_type]

      min_size     = var.scaling_config.min_size
      max_size     = var.scaling_config.max_size
      desired_size = var.scaling_config.desired_size
    }
  }

  access_entries = merge(
    var.admin_role_arn != null && var.admin_role_arn != "" ? {
      admin = {
        principal_arn = var.admin_role_arn
        policy_associations = {
          admin = {
            policy_arn   = "arn:${data.aws_partition.current.partition}:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
            access_scope = { type = "cluster" }
          }
        }
      }
    } : {},

    var.devops_team_role_arn != null && var.devops_team_role_arn != "" ? {
      devops_team = {
        principal_arn = var.devops_team_role_arn
        policy_associations = {
          dev_access = {
            policy_arn   = "arn:${data.aws_partition.current.partition}:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
            access_scope = { type = "cluster" }
          }
        }
      }
    } : {},

    var.backend_devs_role_arn != null && var.backend_devs_role_arn != "" ? {
      backend_devs = {
        principal_arn = var.backend_devs_role_arn
        policy_associations = {
          dev_access = {
            policy_arn   = "arn:${data.aws_partition.current.partition}:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"
            access_scope = { type = "cluster" }
          }
        }
      }
    } : {}
  )

  tags = var.tags
}
