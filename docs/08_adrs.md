# Architecture Decision Records - TF1 · CDO-05

**Target**: ≥3 ADR cho Pack #1 (W11) · ≥5 ADR cho Pack #2 (W12).
*Quy tắc*: Ghi nhận 1 ADR cho mỗi quyết định kiến trúc lớn có trade-off thực tế và chi phí thay đổi cao.

---

## Danh mục ADR

| ADR | Chủ đề | Status | Date |
|---|---|---|---|
| ADR-001 | Compute target - EKS over ECS / Lambda | Accepted | 2026-06-24 |
| ADR-002 | Data storage - DynamoDB cho incident state + idempotency | Accepted | 2026-06-24 |
| ADR-003 | CI/CD strategy - GitHub Actions + ArgoCD | Accepted | 2026-06-25 |
| ADR-004 | Observability stack - Prometheus + Loki + CloudWatch | Accepted | 2026-06-25 |
| ADR-005 | Security baseline - IAM least-privilege + Secrets Manager | Accepted | 2026-06-25 |
| ADR-006 | Cost trade-off - On-demand vs Reserved cho demo | Accepted | 2026-06-25 |
| ADR-007 | Alert Event Pipeline - SQS FIFO + DynamoDB/S3 | Accepted | 2026-06-24 |

---

## ADR-001 - Compute target - EKS over ECS / Lambda for compute layer

- **Status**: Accepted
- **Context**: Dự án **TF1 Triage Hub** yêu cầu xây dựng một nền tảng vận hành sự cố thông minh (**AIOps Incident Triage Platform**) để hiện thực hóa góc tiếp cận khác biệt (*Differentiation Angle*): *"Reliable Incident Triage Pipeline with Alert Storm Control and AI Call Gating"*. Hệ thống đòi hỏi một **mô hình siêu dữ liệu nhất quán (workload metadata consistency)** chạy xuyên suốt từ luồng runtime cho tới logs, metrics, alerts và lịch sử deployment nhằm cung cấp đầy đủ ngữ cảnh cho AI Engine phân tích nguyên nhân gốc rễ (RCA) theo từng khung thời gian sự cố.
- **Decision**: Chọn **Amazon EKS (Elastic Kubernetes Service)** làm nền tảng tính toán cốt lõi. Toàn bộ các cấu phần bao gồm: Demo App workloads, CDO Incident Correlator Worker, AI Engine API, và observability stack (Prometheus, Loki, Grafana, Alertmanager) đều chạy đồng bộ trên cùng một EKS cluster.
- **Consequence**:
  - ✅ **Đồng bộ siêu dữ liệu tuyệt đối**: Siêu dữ liệu `tenant_id`, `service`, `env`, `namespace`, `deployment`, `version`, `pod` đi liền mạch từ: K8s Workloads $\rightarrow$ Prometheus $\rightarrow$ Loki $\rightarrow$ Alertmanager $\rightarrow$ ArgoCD $\rightarrow$ Correlator State $\rightarrow$ AI Engine, giúp AI phân tích ngữ cảnh chính xác, ngăn rò rỉ dữ liệu chéo giữa các tenant.
  - ✅ **Hệ sinh thái Observability & GitOps native**: Tích hợp tự nhiên Prometheus Operator và ArgoCD GitOps trong cluster giúp thu thập metrics/logs sát sườn workloads và lưu vết lịch sử deployment làm bằng chứng chẩn đoán RCA.
  - ✅ **Ranh giới bảo mật mạnh mẽ**: Sử dụng Namespace, NetworkPolicy, ServiceAccount, và IRSA/Pod Identity để phân quyền tối giản (least privilege) và thiết lập vùng truy cập giới hạn (bounded query access) cho AI Engine.
  - ⚠️ **Chi phí cố định và độ phức tạp cao**: Cần duy trì EKS control plane và node group liên tục (~$70–100/tháng) và đòi hỏi kỹ năng vận hành K8s (RBAC, Ingress, NetworkPolicy). Đổi lại, hệ thống có khả năng lọc nhiễu tốt (alert storm control), giúp giảm tần suất gọi LLM đắt đỏ.
- **Alternatives considered**:
  - *AWS Lambda (Serverless-first)*: Bị loại vì Lambda chỉ phù hợp tác vụ ngắn hạn. Hệ thống cần chạy các thành phần dài hạn như demo app, worker và observability stack. Dùng Lambda gây phân mảnh siêu dữ liệu (metadata fragmentation), khiến AI khó gom đủ ngữ cảnh RCA.
  - *ECS Fargate*: Bị loại vì siêu dữ liệu trên ECS bị phân mảnh ở nhiều nơi (ECS Task, CloudWatch, EventBridge, ALB, Tags). CDO sẽ phải viết rất nhiều mã nguồn tùy biến (glue logic) để chắp vá dữ liệu, trong khi EKS cung cấp hệ sinh thái này hoàn toàn tự nhiên.
  - *EC2 self-managed*: Bị loại ngay lập tức do chi phí quản trị và vận hành hạ tầng quá lớn.

---

## ADR-002 - Data storage - DynamoDB cho incident state + idempotency

- **Status**: Accepted
- **Context**: Hệ thống cần lưu trạng thái xử lý từng incident (`RECEIVED`, `AI_ANALYZED`, `JIRA_CREATED`, `SLACK_SENT`, `FAILED`) và đảm bảo tính idempotency (chống trùng lặp) để tránh tạo ticket Jira hoặc gửi Slack trùng khi có cơ chế retry. Đồng thời cần truy vấn nhanh theo `tenant_id` và `timestamp` để kiểm toán (audit trail) mà không lưu trữ log/metric thô.
- **Decision**: Chọn **DynamoDB on-demand** làm kho lưu trữ trạng thái incident và idempotency. Schema: `incident_id` (hash key) + `timestamp` (range key). Sử dụng Global Secondary Index (GSI) theo `tenant_id` + `timestamp` để phục vụ kiểm toán và bật tính năng TTL 90 ngày để tự động dọn dẹp dữ liệu cũ.
- **Consequence**:
  - ✅ Serverless, không cần manage database server trong khi đã có EKS cluster cần quản lý — tránh thêm operational overhead.
  - ✅ On-demand billing phù hợp với workload alert-driven không liên tục — chỉ tốn tiền khi có incident thật.
  - ✅ Query theo `tenant_id` + `timestamp` qua GSI nhanh và đơn giản — đủ cho audit trail và multi-tenant isolation check.
  - ✅ TTL tự động xóa record cũ sau 90 ngày — không cần build cleanup job.
  - ✅ DynamoDB conditional write hỗ trợ idempotency key pattern tự nhiên — tránh race condition khi retry.
  - ⚠️ Không có complex SQL query — chỉ query theo key/GSI. Đủ cho use case audit trail đơn giản của TF1, nhưng nếu cần analytics phức tạp sau này phải export sang S3 + Athena.
  - ⚠️ Hot partition nếu nhiều incident cùng `tenant_id` trong thời gian ngắn — mitigate bằng `incident_id` là UUID random làm hash key, tránh partition skew.
- **Alternatives considered**:
  - *RDS PostgreSQL*: Cung cấp full SQL, truy vấn linh hoạt. Bị loại vì tốn công quản trị và chi phí vận hành RDS cao hơn đáng kể so với DynamoDB cho lượng traffic nhỏ.
  - *S3 + Athena*: Chi phí cực thấp cho lưu trữ lâu dài. Bị loại vì độ trễ truy vấn (query latency) của Athena rất cao (vài giây), không đáp ứng được yêu cầu kiểm tra chống trùng lặp (idempotency check) theo thời gian thực.
  - *Redis / Amazon ElastiCache*: Tốc độ truy cập nhanh nhất. Bị loại vì khả năng lưu trữ lâu dài (persistence) kém hơn DynamoDB và phát sinh thêm chi phí/vận hành một dịch vụ lưu cache riêng biệt.

---

## ADR-003 - CI/CD strategy - GitHub Actions + ArgoCD

- **Status**: Accepted
- **Context**: CDO-05 cần một CI/CD pipeline để build container image, chạy test, scan security và deploy lên EKS cluster. Cần phân biệt rõ hai phần: CI (build/test/scan) và CD (deploy lên K8s). Pipeline phải hỗ trợ GitOps để đảm bảo trạng thái cluster luôn sync với Git, có rollback nhanh khi cần và drift detection.
- **Decision**: Chọn **GitHub Actions** cho phần CI (build + test + scan + push image lên ECR) và **ArgoCD** cho phần CD (GitOps deploy lên EKS). Hai công cụ đảm nhận vai trò tách biệt: GitHub Actions lo phần build pipeline; ArgoCD lo phần sync K8s manifest từ Git vào cluster. Deploy strategy: **canary** — 10% traffic trước, quan sát error rate và latency, sau đó tăng lên 50% rồi 100%.
- **Consequence**:
  - ✅ Phân tách rõ CI và CD — GitHub Actions không cần biết cluster kubeconfig, ArgoCD không cần biết build logic. Boundary sạch, dễ debug.
  - ✅ GitHub Actions cực kỳ linh hoạt, hỗ trợ kho Action Marketplace phong phú (dễ dàng tích hợp các bước test, scan Trivy/Snyk, push ECR).
  - ✅ Bảo mật cao nhờ tích hợp AWS OIDC Federation — GitHub Actions gọi AWS services (ECR, etc.) thông qua IAM Role tạm thời (OIDC), không cần lưu trữ static Access Key nhạy cảm trong GitHub Secrets.
  - ✅ ArgoCD đã học trong W10, team quen cách dùng — không mất thời gian học mới trong W11-W12.
  - ✅ GitOps với ArgoCD đảm bảo cluster state luôn có source of truth trong Git — rollback chỉ cần revert Git commit, ArgoCD tự sync.
  - ✅ ArgoCD drift detection tự phát hiện khi cluster state lệch khỏi Git — daily drift report về Slack.
  - ✅ Canary deploy giảm blast radius khi deploy có lỗi — error rate > 1% hoặc p99 latency > 800ms thì auto-abort và rollback.
  - ⚠️ Cần kết nối từ bên ngoài (GitHub runner) vào AWS ECR — giải quyết bằng IAM OIDC role để tránh rủi ro credential.
  - ⚠️ ArgoCD cần thêm một workload trong cluster — tốn resource nhỏ (~200MB RAM) nhưng không đáng kể.
  - ⚠️ Canary deploy phức tạp hơn rolling update — cần Argo Rollouts hoặc Ingress weight config. Trade-off chấp nhận được vì team đã học Argo Rollouts trong W9.
- **Alternatives considered**:
  - *AWS CodePipeline (CI) + ArgoCD (CD)*: Native hoàn toàn trong AWS ecosystem. Bị loại vì CodePipeline kém linh hoạt hơn GitHub Actions, viết script phức tạp hơn, thời gian build chậm hơn và team ít quen thuộc hơn so với GitHub Actions.
  - *GitHub Actions + Flux (thay ArgoCD)*: Flux cũng là GitOps tool tốt. Bị loại vì team đã học ArgoCD trong W10, chuyển sang Flux mất thêm thời gian học trong W11-W12.
  - *GitHub Actions all-in (CI + CD)*: GitHub Actions có thể deploy thẳng lên EKS qua kubectl/Helm. Bị loại vì không có GitOps model, không có drift detection, rollback phức tạp hơn và cần cung cấp kubeconfig trực tiếp cho GitHub Actions (tăng rủi ro bảo mật).
  - *Blue-green deploy (thay Canary)*: Blue-green đơn giản hơn canary — chỉ cần switch ALB target group. Bị loại vì cần chạy double resource (blue + green) cùng lúc — tốn cost trong demo budget $100–150. Canary tiết kiệm hơn, chỉ tăng traffic dần.

---

## ADR-004 - Observability stack - Prometheus + Loki + CloudWatch

- **Status**: Accepted
- **Context**: Dự án yêu cầu hệ thống giám sát tập trung để theo dõi các SLO về độ trễ, tỉ lệ lỗi và tính sẵn sàng của cả workloads trên EKS (Demo App, worker, AI Engine) lẫn hạ tầng AWS serverless (Lambda, SQS, DynamoDB). Dữ liệu thu thập cần gắn nhãn metadata nhất quán theo `tenant_id` phục vụ AI Engine truy vấn RCA có giới hạn.
- **Decision**: Chọn **Prometheus Operator (Prometheus + Grafana + Alertmanager)** cho metrics và **Loki** cho logs chạy trực tiếp trong cụm EKS. Sử dụng **Amazon CloudWatch** để giám sát các dịch vụ managed của AWS (Lambda, SQS queue depth, DynamoDB metrics).
- **Consequence**:
  - ✅ **Độ trễ thấp & K8s native**: Metrics và logs được thu thập trực tiếp trong cụm bằng các collector cực nhẹ (Fluent Bit/Loki agent, Prometheus scrape targets), giữ nguyên vẹn metadata của K8s workloads.
  - ✅ **Hỗ trợ Alert Gating**: Alertmanager tích hợp mượt mà với PrometheusRules giúp gom nhóm (grouping) và giảm nhiễu alerts từ tầng K8s trước khi gửi đến Ingest Lambda.
  - ✅ **Dashboard SLO trực quan**: Grafana hiển thị đầy đủ dashboard thời gian thực về SLO và chi phí phục vụ buổi chấm demo.
  - ⚠️ **Tiêu tốn tài nguyên node**: Việc chạy Prometheus/Loki trong cụm chiếm dụng CPU/Memory và dung lượng ổ cứng của worker node. Mitigate bằng cách giới hạn retention time ngắn (7 ngày cho sandbox, 14 ngày cho prod) và cấu hình resource limits chặt chẽ.
- **Alternatives considered**:
  - *CloudWatch Container Insights*: Giám sát EKS workloads đẩy trực tiếp lên CloudWatch. Bị loại vì chi phí truyền và lưu trữ logs/metrics lên CloudWatch rất cao cho lượng workloads lớn, và khó cấu hình Alertmanager rules native.
  - *Datadog / SaaS monitoring*: Bị loại vì vượt quá ngân sách capstone (yêu cầu trả phí bản quyền bên ngoài).
  - *Elasticsearch/Fluentd/Kibana (EFK Stack)*: Bị loại vì Elasticsearch tiêu tốn quá nhiều RAM và Disk, dễ làm sập cụm EKS t3.medium có tài nguyên hạn chế.

---

## ADR-005 - Security baseline - IAM least-privilege + Secrets Manager

- **Status**: Accepted
- **Context**: Hệ thống xử lý thông tin nhạy cảm (Jira API tokens, Slack Webhooks, AWS credentials) và chạy trong mô hình pooled multi-tenant. Cần thiết lập ranh giới bảo mật nghiêm ngặt để tránh rò rỉ dữ liệu chéo tenant (cross-tenant leak) và bảo vệ các thông tin nhạy cảm trong suốt luồng CI/CD và runtime.
- **Decision**: Áp dụng **IAM Roles for Service Accounts (IRSA)** cho pod-level AWS access control. Sử dụng **Kubernetes NetworkPolicy** để cô lập namespace và chặn giao tiếp liên tenant trái phép. Sử dụng **AWS Secrets Manager** làm store tập trung, đồng bộ vào cluster bằng **External Secrets Operator (ESO)**. Bật mã hóa SSE-S3/SSE-SQS cho dữ liệu lưu trữ và truyền tải.
- **Consequence**:
  - ✅ **Không dùng static keys**: Loại bỏ hoàn toàn AWS Access Key tĩnh; pods assume IAM role tạm thời bằng cơ chế OIDC.
  - ✅ **Cô lập dữ liệu tenant**: NetworkPolicy chặn đứng các cuộc tấn công quét mạng nội bộ từ pod bị xâm nhập sang các tenant namespace khác.
  - ✅ **Không lộ lọt Secrets**: Toàn bộ secrets nằm an toàn ở Secrets Manager, không bao giờ xuất hiện trong Git, Git history hoặc Docker image.
  - ⚠️ **Độ phức tạp ops cao**: Cần viết nhiều cấu hình YAML cho NetworkPolicies, OIDC Trust Relationships và ExternalSecrets. Đòi hỏi cấu hình đúng ngay từ đầu để tránh chặn nhầm luồng traffic hợp lệ.
- **Alternatives considered**:
  - *Static AWS Access Keys in K8s Secrets*: Bị loại vì cực kỳ kém an toàn, khó xoay vòng (rotate) và dễ bị vô tình commit lên Git.
  - *EKS Node Group Instance Role*: Bị loại vì tất cả pods trên node sẽ có chung quyền của Node, vi phạm nghiêm trọng nguyên tắc đặc quyền tối thiểu (least privilege).
  - *Sử dụng K8s Secrets thủ công*: Bị loại vì phải nhập thủ công bằng tay hoặc qua CI/CD, tăng nguy cơ lộ lọt secrets trong log pipeline.

---

## ADR-006 - Cost trade-off - On-demand vs Reserved cho demo

- **Status**: Accepted
- **Context**: Ngân sách capstone được cấp rất giới hạn ($100–150 trong 2 tuần). Hệ thống lại cần chạy cụm EKS (control plane và worker node) liên tục kèm nhiều dịch vụ AWS khác. Cần có chiến lược tối ưu hóa chi phí tối đa mà vẫn đảm bảo tính sẵn sàng cho buổi chấm.
- **Decision**: Chọn cụm EKS chạy trên **t3.medium instances** (2 nodes baseline), cấu hình Auto Scaling Group tối thiểu 1 node và tối đa 3 nodes. Chọn **DynamoDB on-demand** và **S3 Standard có Lifecycle Policy tự động dọn dẹp sau 30 ngày**. Thiết lập trigger tắt cụm hoặc scale node group về 0 vào ban đêm/cuối tuần khi không làm việc.
- **Consequence**:
  - ✅ **Kiểm soát chi phí tuyệt đối**: Giữ tổng chi phí hạ tầng trong khoảng $110 - $130 cho 2 tuần, hoàn toàn nằm trong budget.
  - ✅ **Tránh lãng phí**: On-demand pricing cho DynamoDB/S3 giúp không tốn tiền khi không có alerts chạy qua hệ thống.
  - ⚠️ **Độ trễ scale-out**: Khi alert storm bùng nổ, cụm EKS mất 2-3 phút để scale node mới lên. Mitigate bằng cách pre-warm node group trước buổi demo chính thức để tránh bị chậm trễ trong quá trình chấm điểm.
- **Alternatives considered**:
  - *m5.large/m5.xlarge instances cho EKS*: Bị loại vì chi phí quá cao, baseline running cost của 2 nodes m5.large sẽ vượt quá budget $150 chỉ trong 10 ngày.
  - *Reserved Instances (RI) / Savings Plans*: Bị loại vì yêu cầu cam kết thời gian sử dụng tối thiểu 1 năm, không khả thi cho dự án học tập 2 tuần.
  - *DynamoDB Provisioned Capacity*: Bị loại vì khó ước lượng traffic chính xác của alert storms, dễ gây lãng phí chi phí fixed khi không sử dụng.

---

## ADR-007 - Alert Event Pipeline - SQS FIFO + DynamoDB/S3

- **Status**: Accepted
- **Context**: Tín hiệu cảnh báo từ Observability stack gửi về hệ thống là cực kỳ quan trọng. Nếu xảy ra sự cố nghẽn mạng hoặc worker bị sập, cơ chế *Lambda Async Retry* không đảm bảo lưu trữ alert lâu dài, dễ gây mất cảnh báo sinh mệnh hoặc tạo trùng lặp ticket trên Jira/Slack khi retry.
- **Decision**: Chốt sử dụng mô hình kết hợp **Ingest Lambda**, **SQS FIFO Queue** làm bộ đệm giảm chấn, **Amazon DynamoDB** làm kho lưu trữ trạng thái (**State Store**), và **Amazon S3** làm kho lưu trữ bằng chứng sự cố (**Evidence Store**).
- **Consequence**:
  - ✅ **Độ bền vững tuyệt đối (Durability)**: SQS FIFO bảo vệ alert tối đa 14 ngày kể cả khi worker phía sau bị sập, không bao giờ bị mất tín hiệu cảnh báo âm thầm.
  - ✅ **Khử trùng lặp 2 lớp**: Khử trùng 5 phút ở đầu vào bằng SQS FIFO, chống trùng lặp đầu ra vĩnh viễn bằng cách ghi nhận `idempotency_key` tại DynamoDB trước khi gọi API Jira/Slack.
  - ✅ **Cô lập lỗi và Replay**: Sử dụng SQS FIFO Dead Letter Queue (DLQ) để tự động cô lập các tin nhắn bị lỗi định dạng, hỗ trợ cơ chế phát lại (replay) dễ dàng sau khi sửa lỗi code mà không cần giả lập lại sự cố.
  - ⚠️ **Tăng độ phức tạp cấu hình**: Phải quản lý nhiều dịch vụ tích hợp.
  - ⚠️ **Giới hạn băng thông**: SQS FIFO giới hạn mặc định 300 TPS. Cần chủ động kích hoạt tính năng *High Throughput* để nâng giới hạn lên **3.000+ TPS** đề phòng các đợt bùng nổ cảnh báo lớn (Alert Storm).
- **Alternatives considered**:
  - *Chỉ dùng Lambda Async Retry*: Bị loại vì thời gian lưu trữ quá ngắn (tối đa vài tiếng), dễ nuốt mất tin nhắn khi sập hệ thống và không hỗ trợ DLQ/Replay.
  - *SQS Standard Queue*: Bị loại vì cơ chế giao hàng *at-least-once* (có thể gửi trùng) và không đảm bảo thứ tự, gây áp lực lớn lên tầng ứng dụng để tự xử lý chống trùng lặp.