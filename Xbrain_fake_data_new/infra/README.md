# Infrastructure — Terraform IaC

> Terraform v1.9+ · AWS Provider ~> 5.0 · State: S3 + DynamoDB lock

## Layout

```
infra/
├── modules/                          # Reusable, environment-agnostic
│   ├── networking/                   # VPC, 3-AZ subnets, NAT, SG, VPC Endpoints
│   ├── eks/                          # EKS cluster, managed node group, IRSA, OIDC
│   ├── data-store/                   # DynamoDB tables (tenant config, audit index)
│   ├── observability/                # CloudWatch Log Groups, Metric Alarms, SNS topics
│   └── tenant-provision/             # Per-tenant: K8s namespace, IRSA role, DB partition key
└── environments/
    ├── dev/                          # Dev root module (replicas=1, t3.medium)
    │   ├── main.tf                   # Gọi modules/ với dev-specific vars
    │   ├── terraform.tfvars          # Dev values
    │   └── backend.tf                # key = "dev/terraform.tfstate"
    └── prod/                         # Prod root module (replicas=3, m5.large)
        ├── main.tf
        ├── terraform.tfvars
        └── backend.tf                # key = "prod/terraform.tfstate"
```

## State Management

| Concern | Approach |
|---|---|
| Remote state | S3 per-environment (`dev/terraform.tfstate`, `prod/terraform.tfstate`) |
| Locking | DynamoDB (`tf1-cdo05-tflock`, hash key = `LockID`) |
| Encryption | SSE-S3 + bucket policy deny unencrypted transport |
| Versioning | S3 versioning ON — rollback bằng `terraform state pull` từ version cũ |
| Access | CI assume role via OIDC (không static key) |

## Naming Convention

Tất cả AWS resources tuân theo pattern:

```
tf1-cdo05-{env}-{component}-{resource}
```

Ví dụ: `tf1-cdo05-prod-eks-cluster`, `tf1-cdo05-dev-vpc`, `tf1-cdo05-prod-audit-dynamodb`

## Prerequisites

- Terraform >= 1.9
- AWS CLI v2 configured
- S3 state bucket + DynamoDB lock table đã tồn tại
- IAM role `tf1-cdo05-infra-deploy-role` với OIDC trust

## Usage

```bash
# Từ environment directory (vd: infra/environments/dev/)
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```
