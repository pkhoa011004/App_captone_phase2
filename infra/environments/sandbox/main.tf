

data "aws_partition" "current" {}
data "aws_caller_identity" "current" {}

locals {
  prefix         = "${var.project}-${var.environment}"
  tfstate_bucket = "xbrain-capstone-cdo5-${var.environment}-tfstate"
}

data "aws_availability_zones" "available" {
  state = "available"
}

module "networking" {
  source = "../../modules/networking"

  project              = var.project
  environment          = var.environment
  tags                 = var.tags
  vpc_cidr             = var.vpc_cidr
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  availability_zones   = slice(data.aws_availability_zones.available.names, 0, 2)
  aws_region           = var.aws_region

  single_nat_gateway = true
  eks_cluster_name   = "${local.prefix}-cluster"
}

module "eks" {
  source = "../../modules/eks"

  project     = var.project
  environment = var.environment
  tags        = var.tags

  vpc_id     = module.networking.vpc_id
  subnet_ids = module.networking.private_subnet_ids

  cluster_name    = "${var.project}-${var.environment}-cluster"
  cluster_version = var.cluster_version

  admin_role_arn        = coalesce(var.admin_role_arn, data.aws_caller_identity.current.arn)
  devops_team_role_arn  = var.devops_team_role_arn
  backend_devs_role_arn = var.backend_devs_role_arn

  instance_type  = var.instance_type
  scaling_config = var.eks_scaling_config
}

module "eks_addons" {
  source     = "../../modules/eks-addons"
  depends_on = [module.eks]
}

module "external_secrets" {
  source = "../../modules/external-secrets"

  project               = var.project
  environment           = var.environment
  tags                  = var.tags
  eks_cluster_name      = module.eks.cluster_name
  eks_oidc_provider_arn = module.eks.oidc_provider_arn
  aws_region            = var.aws_region

  depends_on = [module.eks]
}

module "github_oidc" {
  source = "../../modules/github-oidc"

  role_name          = "${local.prefix}-ci"
  policy_name        = "${local.prefix}-ci-policy"
  policy_description = "Policy for CI/CD role to push images to ECR"
  github_repos       = [var.github_repo]
  tags               = var.tags

  policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage"
        ]
        Resource = "*"
      },
      {
        Sid      = "EKSDescribe"
        Effect   = "Allow"
        Action   = ["eks:DescribeCluster", "eks:ListClusters"]
        Resource = "*"
      },
      {
        Sid    = "TerraformStateS3"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:${data.aws_partition.current.partition}:s3:::${local.tfstate_bucket}",
          "arn:${data.aws_partition.current.partition}:s3:::${local.tfstate_bucket}/*"
        ]
      }
    ]
  })
}

module "ecr" {
  source       = "../../modules/ecr"
  ci_role_arn  = module.github_oidc.role_arn
  tags         = var.tags
  repositories = var.ecr_repositories
  project      = var.project
  environment  = var.environment
}

module "incident_ingest" {
  source = "../../modules/incident-ingest"

  prefix                 = local.prefix
  tags                   = var.tags
  lambda_source_dir      = "${path.module}/../../../apps/ingest-lambda"
  lambda_zip_output_path = "${path.module}/.temp/ingest_lambda.zip"
  ssm_parameter_prefix   = "/${var.project}/${var.environment}"
}
