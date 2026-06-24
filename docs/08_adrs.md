<!-- Doc owner: <Nhóm CDO-05>
     Status: Ongoing log W11-W12
     Format: 1 ADR per major decision. Append-only - không xóa ADR cũ. --># Architecture Decision Records — Task Force 1 · CDO-05

<!-- Doc owner: CDO-05
     Status: Ongoing log W11-W12
     Format: 1 ADR per major decision. Append-only — không xóa ADR cũ. -->

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

---

## Danh mục ADR

| ADR | Chủ đề | Status | Date |
|---|---|---|---|
| ADR-001 | Compute target — EKS over ECS / Lambda | Accepted | 2026-06-24 |
| ADR-002 | Data storage — DynamoDB cho incident state + idempotency | Accepted | 2026-06-24 |
| ADR-003 | CI/CD strategy — CodePipeline + ArgoCD | Accepted | 2026-06-24 |
| ADR-004 | Observability stack — Prometheus + Loki + CloudWatch | Proposed | — |
| ADR-005 | Security baseline — IAM least-privilege + Secrets Manager | Proposed | — |
| ADR-006 | Cost trade-off — On-demand vs Reserved cho demo | Proposed | — |

---

## ADR-001 — EKS over ECS / Lambda for compute layer

- **Status**: Accepted
- **Date**: 2026-06-24
- **Context**: TF1 Triage Hub cần chạy đồng thời nhiều thành phần: Demo App, AIOps Backend, TF1 AI Engine API, Observability Stack (Prometheus, Grafana, Loki, OTel Collector). Các thành phần này cần chạy liên tục để sẵn sàng xử lý alert bất kỳ lúc nào và cần metadata model nhất quán xuyên suốt từ workload đến metric, log, alert và deployment state. CDO-05 cần chọn một compute platform phù hợp để host toàn bộ stack này trong thời gian build W11-W12.
- **Decision**: Chọn **EKS (Elastic Kubernetes Service)** làm core compute platform. Toàn bộ app workload, AIOps Backend, AI Engine, và Observability Stack đều chạy trên cùng một EKS cluster. ECS Fargate có thể dùng phụ trợ cho các scheduled task nhỏ nếu cần, gom vào cùng cluster để giảm operational cost.
- **Consequence**:
  - ✅ Kubernetes ecosystem cung cấp metadata model nhất quán: `tenant_id`, `service`, `env`, `namespace`, `deployment`, `version`, `pod` dùng xuyên suốt từ workload đến metric/log/alert/deployment state — giúp AIOps build RCA context đầy đủ hơn.
  - ✅ Prometheus Operator, ServiceMonitor, PrometheusRule, Alertmanager tích hợp tự nhiên trong K8s — observability gần workload hơn, không cần custom glue layer.
  - ✅ ArgoCD GitOps chạy trong cluster, quản lý deployment và recent change metadata — AIOps có thể dùng deployment event để enrich RCA context.
  - ✅ RBAC, NetworkPolicy, Namespace cho phép enforce tenant isolation và bounded query access ở tầng platform.
  - ✅ Team CDO-05 đã học K8s trong W10 (RBAC, OPA, ArgoCD, Prometheus stack) — không cần học thêm, áp dụng trực tiếp kiến thức đã có.
  - ⚠️ Baseline cost cao hơn ECS/Lambda vì EKS cluster và node group luôn chạy dù không có alert. Chi phí cluster tối thiểu khoảng $70–100/tháng.
  - ⚠️ Operational complexity cao hơn: cần quản lý node group, ingress controller, RBAC, NetworkPolicy, monitoring stack, GitOps. Phù hợp vì team đã quen, nhưng thời gian setup W11 sẽ tốn hơn so với managed services.
  - ⚠️ Không có cold start như Lambda, nhưng node scale-out khi alert spike có thể mất 2–3 phút nếu cần thêm node mới — cần pre-warm đủ capacity cho demo.
- **Alternatives considered**:
  - **AWS Lambda + API Gateway (Serverless-first)**: Chi phí thấp hơn (pay-per-invocation), không cần manage cluster, scale tự động. Bị loại vì cold start 1–3s ảnh hưởng p99 latency của alert path; khó gom K8s deployment metadata vào RCA context; observability stack không thể chạy serverless hoàn toàn. Phù hợp hơn cho CDO angle khác trong cùng TF1.
  - **ECS Fargate standalone**: Đơn giản hơn EKS, không cần manage control plane, cost thấp hơn. Bị loại vì thiếu Kubernetes ecosystem (Prometheus Operator, ServiceMonitor, PrometheusRule, ArgoCD, NetworkPolicy, Namespace isolation) — phải build nhiều custom glue layer hơn để đạt cùng mức metadata consistency cho AIOps RCA.
  - **EC2 self-managed**: Kiểm soát tối đa nhưng operational overhead quá cao cho thời gian build W11-W12. Bị loại ngay.

---

## ADR-002 — DynamoDB cho incident state và idempotency

- **Status**: Accepted
- **Date**: 2026-06-24
- **Context**: TF1 Triage Hub cần lưu trạng thái xử lý từng incident (`RECEIVED`, `AI_ANALYZED`, `JIRA_CREATED`, `SLACK_SENT`, `FAILED`) và đảm bảo idempotency để tránh tạo ticket Jira hoặc gửi Slack message trùng khi có retry. Ngoài ra cần query nhanh theo `tenant_id` và `timestamp` để audit trail. Metric và log không được lưu vào database riêng — chỉ lưu trong Prometheus và CloudWatch Logs/Loki tương ứng.
- **Decision**: Chọn **DynamoDB on-demand** làm storage cho incident state và idempotency. Schema: `incident_id` (hash key) + `timestamp` (range key). Global Secondary Index (GSI) theo `tenant_id` + `timestamp` để query audit theo tenant. TTL 90 ngày cho audit record. S3 dùng để lưu audit evidence dài hạn (alert payload, context/evidence package, AI response, Jira/Slack payload) nếu cần — phần này TBD.
- **Consequence**:
  - ✅ Serverless, không cần manage database server trong khi đã có EKS cluster cần quản lý — tránh thêm operational overhead.
  - ✅ On-demand billing phù hợp với workload alert-driven không liên tục — chỉ tốn tiền khi có incident thật.
  - ✅ Query theo `tenant_id` + `timestamp` qua GSI nhanh và đơn giản — đủ cho audit trail và multi-tenant isolation check.
  - ✅ TTL tự động xóa record cũ sau 90 ngày — không cần build cleanup job.
  - ✅ DynamoDB conditional write hỗ trợ idempotency key pattern tự nhiên — tránh race condition khi retry.
  - ⚠️ Không có complex SQL query — chỉ query theo key/GSI. Đủ cho use case audit trail đơn giản của TF1, nhưng nếu cần analytics phức tạp sau này phải export sang S3 + Athena.
  - ⚠️ Hot partition nếu nhiều incident cùng `tenant_id` trong thời gian ngắn — mitigate bằng `incident_id` là UUID random làm hash key, tránh partition skew.
- **Alternatives considered**:
  - **RDS PostgreSQL**: Full SQL, dễ query phức tạp, audit report linh hoạt hơn. Bị loại vì cần manage RDS instance — thêm operational overhead khi đã có EKS. Cost cao hơn DynamoDB on-demand cho workload thưa. Overkill cho use case incident state + idempotency đơn giản.
  - **S3 + Athena**: Chi phí thấp nhất cho storage dài hạn, query bằng SQL qua Athena. Bị loại vì Athena query latency cao (vài giây), không phù hợp cho idempotency check real-time khi xử lý incident. S3 vẫn được dùng phụ trợ cho audit evidence dài hạn.
  - **Redis / ElastiCache**: Latency thấp nhất cho idempotency check. Bị loại vì không có persistence tốt, TTL management phức tạp hơn DynamoDB, thêm một managed service nữa cần setup và monitor.

---

## ADR-003 — CI/CD strategy: CodePipeline + ArgoCD

- **Status**: Accepted
- **Date**: 2026-06-24
- **Context**: CDO-05 cần một CI/CD pipeline để build container image, chạy test, scan security và deploy lên EKS cluster. Cần phân biệt rõ hai phần: CI (build/test/scan) và CD (deploy lên K8s). Pipeline phải hỗ trợ GitOps để đảm bảo trạng thái cluster luôn sync với Git, có rollback nhanh khi cần và drift detection.
- **Decision**: Chọn **AWS CodePipeline** cho phần CI (build + test + scan + push image lên ECR) và **ArgoCD** cho phần CD (GitOps deploy lên EKS). Hai công cụ đảm nhận vai trò tách biệt: CodePipeline lo phần build pipeline; ArgoCD lo phần sync K8s manifest từ Git vào cluster. Deploy strategy: **canary** — 10% traffic trước, quan sát error rate và latency, sau đó tăng lên 50% rồi 100%.
- **Consequence**:
  - ✅ Phân tách rõ CI và CD — CodePipeline không cần biết cluster kubeconfig, ArgoCD không cần biết build logic. Boundary sạch, dễ debug.
  - ✅ ArgoCD đã học trong W10, team quen cách dùng — không mất thời gian học mới trong W11-W12.
  - ✅ GitOps với ArgoCD đảm bảo cluster state luôn có source of truth trong Git — rollback chỉ cần revert Git commit, ArgoCD tự sync.
  - ✅ ArgoCD drift detection tự phát hiện khi cluster state lệch khỏi Git — daily drift report về Slack.
  - ✅ Canary deploy giảm blast radius khi deploy có lỗi — error rate > 1% hoặc p99 latency > 800ms thì auto-abort và rollback.
  - ✅ CodePipeline native với AWS ecosystem — dễ integrate ECR, Secrets Manager, IAM OIDC trong cùng account.
  - ⚠️ CodePipeline có less flexibility hơn GitHub Actions cho custom workflow — nhưng đủ cho build/test/scan/push standard pipeline của TF1.
  - ⚠️ ArgoCD cần thêm một workload trong cluster — tốn resource nhỏ (~200MB RAM) nhưng không đáng kể.
  - ⚠️ Canary deploy phức tạp hơn rolling update — cần Argo Rollouts hoặc Ingress weight config. Trade-off chấp nhận được vì team đã học Argo Rollouts trong W9.
- **Alternatives considered**:
  - **GitHub Actions (CI) + ArgoCD (CD)**: GitHub Actions linh hoạt hơn CodePipeline, marketplace action phong phú. Bị loại vì cần thêm GitHub secret để access AWS — thêm credential surface. CodePipeline dùng IAM OIDC native hơn trong AWS ecosystem của TF1.
  - **CodePipeline + Flux (thay ArgoCD)**: Flux cũng là GitOps tool tốt. Bị loại vì team đã học ArgoCD trong W10, chuyển sang Flux mất thêm thời gian học trong W11-W12.
  - **CodePipeline all-in (CI + CD)**: CodePipeline có thể deploy thẳng lên EKS qua EKS deploy action. Bị loại vì không có GitOps, không có drift detection, rollback phức tạp hơn — mất các lợi ích của GitOps model.
  - **Blue-green deploy (thay Canary)**: Blue-green đơn giản hơn canary — chỉ cần switch ALB target group. Bị loại vì cần chạy double resource (blue + green) cùng lúc — tốn cost trong demo budget $100–150. Canary tiết kiệm hơn, chỉ tăng traffic dần.

---

## ADR-004 — Observability stack: Prometheus + Loki + CloudWatch

- **Status**: Proposed
- **Date**: —
- **Context**: <!-- Cần điền sau khi team confirm stack observability cụ thể -->
- **Decision**: <!-- TBD -->
- **Consequence**: <!-- TBD -->
- **Alternatives considered**: <!-- TBD -->

---

## ADR-005 — Security baseline: IAM least-privilege + Secrets Manager

- **Status**: Proposed
- **Date**: —
- **Context**: <!-- Cần điền sau khi Thắng confirm security design -->
- **Decision**: <!-- TBD -->
- **Consequence**: <!-- TBD -->
- **Alternatives considered**: <!-- TBD -->

---

## ADR-006 — Cost trade-off: On-demand vs Reserved cho demo

- **Status**: Proposed
- **Date**: —
- **Context**: <!-- Cần điền sau khi có số thật từ 05_cost_analysis.md -->
- **Decision**: <!-- TBD -->
- **Consequence**: <!-- TBD -->
- **Alternatives considered**: <!-- TBD -->

---

<!-- Append ADR mới ở dưới. Khi 1 ADR bị superseded, đánh dấu Status + link forward. -->