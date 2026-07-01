# Capstone Phase 2 — Task Force 1 · CDO-05

> **Đề tài**: Triage Hub — AIOps Incident Triage Automation
> **Client**: CTO SaaS startup B2B, ~20k user, ~50 microservice. On-call burnt out, MTTR tăng.
> **Team**: CDO-05 (Cloud/DevOps)
> **Task Force**: TF1
> **Timeline**: W11 (22/06–26/06) → W12 (29/06–03/07)

---

## Quick Links

| Document | Mô tả | Pack |
|---|---|---|
| [Requirements Analysis](docs/01_requirements_analysis.md) | Phân tích yêu cầu, NFRs, constraints | #1 |
| [Infra Design](docs/02_infra_design.md) | Kiến trúc hạ tầng, multi-tenant, component table | #1 |
| [Security Design](docs/03_security_design.md) | Network security, IAM, secret management | #1 |
| [Deployment Design](docs/04_deployment_design.md) | CI/CD, GitOps, deployment strategy, observability | #1 |
| [Cost Analysis](docs/05_cost_analysis.md) | Chi phí per-tenant, budget tracking | #1 → #2 |
| [Test & Eval Report](docs/07_test_eval_report.md) | Kết quả test, chaos response evidence | #2 |
| [ADRs](docs/08_adrs.md) | Architecture Decision Records | #1 + #2 |

---

## Repo Structure

```
xbrain-capstone-cdo5/
│
├── .github/workflows/           # GitHub Actions CI/CD pipelines
│                                # - Pipeline 1: Infra (Terraform fmt → validate → tfsec → plan → apply)
│                                # - Pipeline 2: Platform Service (test → trivy → build → push ECR → update manifests)
│
├── docs/                        # Tài liệu thiết kế dự án
│   ├── 01–08_*.md               # Design docs đánh số theo thứ tự
│   └── assets/                  # Diagrams, screenshots cho docs
│
├── infra/                       # Terraform IaC
│   ├── modules/                 # Reusable, environment-agnostic modules
│   │   ├── networking/          #   VPC, subnets, NAT, SG, VPC Endpoints
│   │   ├── eks/                 #   EKS cluster, managed node group, IRSA, OIDC
│   │   ├── data-store/          #   DynamoDB tables (tenant config, audit)
│   │   ├── observability/       #   CloudWatch Log Groups, Metric Alarms, SNS
│   │   └── tenant-provision/    #   Per-tenant: namespace, IRSA role, DB partition
│   └── environments/            # Per-env root modules gọi vào modules/
│       ├── dev/                 #   Dev config (replicas=1, t3.medium)
│       └── prod/                #   Prod config (replicas=3, m5.large)
│
├── manifests/                   # Kubernetes manifests (Kustomize + ArgoCD)
│   ├── argocd/                  # ArgoCD Application CRs (App-of-Apps root)
│   ├── base/                    # Shared K8s resources (DRY)
│   │   ├── platform-service/    #   Deployment, Service, HPA
│   │   └── ai-engine/           #   Argo Rollout (Canary), Service, HPA
│   └── overlays/                # Per-env Kustomize patches
│       ├── dev/                 #   Dev patches (replicas, resource limits)
│       └── prod/                #   Prod patches (replicas, resource limits)
│
├── scripts/                     # Utility scripts (bootstrap, helpers)
│
├── CODEOWNERS                   # GitHub code ownership rules
├── Makefile                     # Common dev commands (tf-plan, tf-apply, etc.)
└── .gitignore                   # Terraform, IDE, secrets, Python, Node
```

### Conventions

| Concern | Pattern | Mô tả |
|---|---|---|
| IaC | **Terraform module/env** | `modules/` chứa logic tái sử dụng, `environments/{env}/` chứa root module + tfvars riêng |
| K8s manifests | **Kustomize base/overlay** | `base/` chứa shared YAML, `overlays/{env}/` patch per-env |
| CD | **ArgoCD App-of-Apps** | 1 root Application quản lý nhiều child apps theo sync waves |
| CI | **GitHub Actions** | 3 pipeline tách biệt: Infra, Platform App, ArgoCD CD |
| Naming | `tf1-cdo05-{env}-{component}-{resource}` | Tất cả AWS resources tuân theo pattern này |

### Environments

| Env | Infra | Manifests | Branch | Deploy |
|---|---|---|---|---|
| **Dev** | `infra/environments/dev/` | `manifests/overlays/dev/` | `develop` | Auto on merge |
| **Prod** | `infra/environments/prod/` | `manifests/overlays/prod/` | `main` | Manual approve |

> **Note**: Budget capstone giới hạn 2 env. Dev đóng vai trò staging — test xong trên dev, merge vào main = deploy prod.

---

## Checkpoint Checklist

### Progress #1 — EOD T4 W11 (light)
- [ ] `01_requirements_analysis.md` (draft)
- [ ] `02_infra_design.md` (draft + angle declared + multi-tenant approach)
- [ ] `08_adrs.md` (≥2 ADR cho key decisions)

### Evidence Pack #1 ⭐ — EOD T6 W11
- [ ] `01_requirements_analysis.md`
- [ ] `02_infra_design.md` (with multi-tenant approach)
- [ ] `03_security_design.md` (draft)
- [ ] `04_deployment_design.md` (draft)
- [ ] `05_cost_analysis.md` (skeleton)
- [ ] `08_adrs.md` (≥3 ADRs)
- [ ] Base infra (VPC + cluster + observability) chạy được

### Progress #2 — EOD T2 W12 (light)
- [ ] AI engine integration started
- [ ] Tenant onboarding flow draft

### Evidence Pack #2 ⭐ — EOD T4 W12 (code freeze 18h)
- [ ] All docs final
- [ ] `05_cost_analysis.md` **measured**
- [ ] `07_test_eval_report.md` **new** với chaos response evidence
- [ ] `08_adrs.md` final (≥5 ADRs)
- [ ] Platform infra deployed + integrated với AI engine
- [ ] git tag `final`