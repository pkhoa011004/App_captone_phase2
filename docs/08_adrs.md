# Architecture Decision Records - CDO-05 · Task Force 1

<!-- Doc owner: <Nhóm CDO-05>
     Status: Ongoing log W11-W12
     Format: 1 ADR per major decision. Append-only - không xóa ADR cũ. -->

> **ADR là gì**: Architecture Decision Record. File log mỗi quyết định kiến trúc quan trọng + lý do tại sao chọn cái đó (chứ không phải mấy phương án khác). Mục đích: 6 tháng sau quay lại codebase vẫn nhớ "à hồi đó chọn X vì Y, không phải vì tôi thích".
>
> **Khi nào viết ADR**:
> - Decision có **trade-off thật** (chọn X có cost, chọn Y có benefit).
> - Decision **reversal cost cao** (vd đổi compute target = rebuild infra).
> - Decision có thể bị hỏi "sao chọn vậy?" trong Individual Defense buổi chấm.
>
> **KHÔNG cần ADR cho**: chuyện nhỏ không có trade-off (tên resource, naming convention, vv).
>
> **Khi 1 ADR cũ không còn áp dụng**: đánh dấu `Status: Superseded by ADR-NNN`, KHÔNG xóa ADR cũ. Append-only.

**Target**: ≥3 ADR cho Pack #1 (W11) · ≥5 ADR cho Pack #2 (W12).

**Ví dụ topic cần ADR (Nhóm CDO)**:
- Infra angle pick (serverless / K8s / streaming / lakehouse / managed observability)
- Compute target (Lambda vs ECS Fargate vs EKS)
- Data storage (DynamoDB vs RDS vs S3+Athena)
- CI/CD strategy (GitHub Actions vs CodePipeline, canary vs blue-green)
- Observability stack (Prometheus+Grafana vs CloudWatch native)
- Security baseline (IAM scope, secrets injection pattern, network isolation)
- Cost trade-off (Reserved Instance vs On-demand cho demo)

---

## ADR-001 — EKS over ECS/Lambda for compute layer

- **Status**: Accepted
- **Date**: 2026-06-24
- **Context**: TF1 Triage Hub cần platform cho AI incident triage. CDO cần chọn compute layer để host AI Engine + Platform Service + observability stack. Bài toán không chỉ là chạy container — cần ecosystem thống nhất cho metric, log, alert, runtime state, deployment metadata để AI có đủ context cho RCA.
- **Decision**: Chọn **EKS (K8s-heavy)** làm differentiation angle chính.
- **Consequence**:
  - ✅ Kubernetes ecosystem cung cấp metadata model nhất quán (namespace/label/annotation) xuyên suốt workload, metric, log, alert, deployment state.
  - ✅ Prometheus Operator + ServiceMonitor + Alertmanager native integration cho alerting flow.
  - ✅ Argo CD/GitOps cung cấp deployment context tự nhiên (recent changes).
  - ✅ NetworkPolicy + RBAC cho tenant isolation ở compute level.
  - ⚠️ Baseline cost cao hơn ECS (~$50-70/tuần cho EKS control plane + nodes).
  - ⚠️ Ops complexity cao: cần quản lý EKS, node group, ingress, monitoring stack.
- **Alternatives considered**:
  - ECS Fargate: Rẻ hơn, ops đơn giản hơn. Rejected vì thiếu ecosystem cho observability + RCA context nhất quán.
  - Lambda + API Gateway: Rẻ nhất. Rejected vì cold start ảnh hưởng p99 latency SLO, và không thể hiện runtime context (pod state, deployment metadata) cho AI RCA.

---

## ADR-002 — Terraform over CDK/CloudFormation for IaC

- **Status**: Accepted
- **Date**: 2026-06-24
- **Context**: CDO-05 cần IaC tool để provision EKS, VPC, DynamoDB, IAM, S3 và quản lý state across environments. Tool cần hỗ trợ plan-before-apply workflow cho mentor review, module reuse, và multi-provider (AWS + K8s + Helm).
- **Decision**: Chọn **Terraform v1.9+** (HCL).
- **Consequence**:
  - ✅ `terraform plan` output là evidence trực quan nhất cho mentor review trên PR.
  - ✅ HCL declarative, dễ đọc, team đã có kinh nghiệm từ W3-W9.
  - ✅ Multi-provider: dùng AWS provider + Kubernetes provider + Helm provider trong cùng codebase.
  - ✅ State drift detection native — phát hiện manual changes trên console.
  - ⚠️ State management overhead: cần S3 + DynamoDB cho remote state + locking.
  - ⚠️ HCL learning curve cho member mới (nhưng team đã quen).
- **Alternatives considered**:
  - AWS CDK (TypeScript): Rejected vì team chưa dùng, imperative code khó review hơn HCL declarative, và `cdk diff` limited so với `terraform plan`.
  - CloudFormation: Rejected vì verbose YAML (2000+ dòng), no native drift detection, nested stacks khó maintain.

---

## ADR-003 — ArgoCD over Flux for GitOps CD

- **Status**: Accepted
- **Date**: 2026-06-24
- **Context**: CDO-05 cần GitOps tool để deploy K8s manifests lên EKS cluster. Tool cần hỗ trợ App of Apps pattern, canary deployment, UI dashboard (cho demo buổi chấm), drift detection, và sync windows.
- **Decision**: Chọn **ArgoCD** + **Argo Rollouts**.
- **Consequence**:
  - ✅ Web UI trực quan — vũ khí demo buổi chấm (show real-time cluster state, sync status, rollout progress).
  - ✅ Argo Rollouts canary deployment native integration (cùng CNCF ecosystem).
  - ✅ App of Apps pattern built-in — quản lý multi-environment dễ dàng.
  - ✅ Sync windows built-in — restrict prod deployment ngoài giờ hành chính.
  - ⚠️ Thêm component chạy trong cluster (ArgoCD server, repo server, application controller).
  - ⚠️ Learning curve cho team member chưa dùng ArgoCD.
- **Alternatives considered**:
  - Flux v2: Rejected vì không có UI (CLI only, khó demo), canary cần Flagger (separate project), không có sync windows native.
  - Jenkins CD: Rejected vì không phải GitOps tool, không có drift detection, không có K8s-native deployment management.

---

## ADR-004 — Canary over Blue-Green for AI Engine deployment

- **Status**: Accepted
- **Date**: 2026-06-24
- **Context**: AI Engine là component quan trọng nhất — nếu model trả kết quả sai, toàn bộ ticket chẩn đoán sai. Cần deployment strategy cho phép validate bản mới trước khi route 100% traffic, với auto-rollback nếu metrics vi phạm SLO.
- **Decision**: Chọn **Canary** (Argo Rollouts) cho AI Engine. **Rolling Update** cho Platform Service (less critical).
- **Consequence**:
  - ✅ Traffic control granular: 10% → 50% → 100% — validate bản mới với traffic thật.
  - ✅ Metric-based auto-abort: AnalysisRun check error rate + p99 latency + AI confidence.
  - ✅ Resource overhead chỉ ~10% (thêm 1 pod canary), tiết kiệm budget.
  - ✅ Rollback instant (shift traffic back) — RTO < 30s.
  - ⚠️ Cần Argo Rollouts CRD (thêm dependency trong cluster).
  - ⚠️ Cần Prometheus metrics available để AnalysisRun query (dependency on observability stack Wave 3).
- **Alternatives considered**:
  - Blue-Green: Rejected vì double resource overhead (2 full deployment sets) — vượt budget capstone. Rollback nhanh nhưng không có metric-based abort, phải manual check.
  - Rolling Update: Rejected cho AI Engine vì không có traffic control — nếu bản mới lỗi, tất cả traffic bị ảnh hưởng trước khi phát hiện. Chấp nhận cho Platform Service vì component này less critical.

---

<!-- Append ADR mới ở dưới. Khi 1 ADR bị superseded, đánh dấu Status + link forward.

Suggested ADR areas còn lại (cần thêm cho Pack #2):
- ADR-005: Database choice + multi-tenant pattern (silo/pool/bridge)
- ADR-006: Observability stack (Prometheus+Grafana vs CloudWatch native)
- ADR-007: Tenant isolation depth (compute level vs data level vs network level)
- ADR-008: Cost optimization trade-off (cold start vs always-on)
-->
