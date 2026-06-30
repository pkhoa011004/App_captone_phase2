data "aws_caller_identity" "current" {}

locals {
  prefix = "${var.project}-${var.environment}"
}

# 1. IAM Policy cho ESO để lấy Parameter Store
data "aws_iam_policy_document" "eso" {
  statement {
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath"
    ]
    resources = [
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${var.project}/${var.environment}/*"
    ]
  }
}

resource "aws_iam_policy" "eso" {
  name        = "${local.prefix}-eso-policy"
  description = "IAM Policy for External Secrets Operator to access SSM Parameter Store"
  policy      = data.aws_iam_policy_document.eso.json
  tags        = var.tags
}

# 2. IAM Role (IRSA) cho ServiceAccount external-secrets
module "eso_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.30"

  role_name = "${local.prefix}-eso-role"

  oidc_providers = {
    main = {
      provider_arn               = var.eks_oidc_provider_arn
      namespace_service_accounts = ["${var.helm_namespace}:external-secrets"]
    }
  }

  role_policy_arns = {
    eso = aws_iam_policy.eso.arn
  }

  tags = var.tags
}

# 3. Helm Release cài đặt ESO
resource "helm_release" "external_secrets" {
  name             = "external-secrets"
  repository       = "https://charts.external-secrets.io"
  chart            = "external-secrets"
  namespace        = var.helm_namespace
  create_namespace = true
  version          = var.helm_chart_version

  set {
    name  = "installCRDs"
    value = "true"
  }

  set {
    name  = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
    value = module.eso_irsa.iam_role_arn
  }
}
