# Requirements Analysis - Task force 1 Infra

## 1. Đề tài context

TF1 xây dựng **Triage Hub** cho SaaS B2B (~20k user, ~50 microservice). Đội ngũ on-call gồm 8 engineer phải chịu hơn 50 alert/tuần, mất từ 30-60 phút cho mỗi alert để tìm nguyên nhân (tra cứu log, query metric, viết ticket Jira, ping team sở hữu). MTTR tăng cao, Ban giám đốc (Board) hỏi mỗi quý nhưng CTO không trả lời được vì không có dữ liệu đo lường.

Triage Hub tự động hóa quy trình: nhận alert -> lấy context (log + metric + thông tin deploy) -> AI chẩn đoán (diagnose) nguyên nhân + đề xuất hướng xử lý -> tạo ticket Jira -> ping Slack kèm nút nhấn 1-click xác nhận (ack). **KHÔNG tự động khắc phục (auto-remediation)**, luôn giữ vai trò của con người trong quy trình quyết định (human-in-the-loop).

Phân chia trách nhiệm: **CDO** đảm bảo dữ liệu quan sát (metric, log) có siêu dữ liệu (metadata) đầy đủ và truy vấn được theo tenant/service/env/window. **AIOps** lấy dữ liệu đó, phân tích, tìm nguyên nhân, sinh payload Jira/Slack. **CDO** nhận payload và gửi Jira/Slack thật, lưu lại lịch sử kiểm toán và trạng thái (audit/state).

## 2. Infra non-functional requirements

Từ ngữ cảnh đề tài, nhóm em rút ra các yêu cầu kỹ thuật cho nền tảng hạ tầng (infra) như sau:

**Từ tình huống "50 microservice, >50 alert/tuần, burst khi critical service down"**:
- **Multi-tenant scale**: >= 50 tenant. Hệ thống phải chịu tải được 50 microservice đồng thời, mỗi service phải gắn `tenant_id` để tránh rò rỉ dữ liệu (data leak) giữa các tenant.
- **Burst handling**: Khi dịch vụ quan trọng (critical service) bị sập, alert sẽ dồn dập liên tục (gây hiệu ứng cascading). Hạ tầng phải tự động co giãn (auto-scale) tức thì để không gây nghẽn đường ống xử lý (pipeline). Sử dụng HPA với cấu hình tối thiểu (min) 2, tối đa (max) 6, kích hoạt khi CPU đạt 70%.
- **Error rate < 0.5%**: Alert không được phép bị thất lạc (lost) hoặc chậm trễ trong việc xử lý. Mỗi alert đóng vai trò cực kỳ quan trọng, nếu mất đi thì đội ngũ on-call sẽ không biết có sự cố (incident) xảy ra.

**Từ tình huống "mất 30-60 phút/alert, MTTR tăng"**:
- **SLO p99 latency (routing) < 1000ms**: Thời gian điều hướng (routing) của hạ tầng (ALB + Ingress) phải nhỏ, không tính thời gian xử lý AI (AI inference time). Mục tiêu là góp phần giảm MTTR.
- **E2E alert -> ticket p99 < 30s**: Từ lúc alert được kích hoạt (fire) đến khi tạo xong ticket Jira phải nhỏ hơn 30 giây, nhằm góp phần giảm thiểu chỉ số MTTA/MTTR.

**Từ yêu cầu "context isolation per-tenant, không leak cross-tenant"**:
- **Tenant data isolation**: Strict 100%. Mọi đường truyền dữ liệu (data path bao gồm queue, DB, storage, logs) phải được gắn `tenant_id`. Sử dụng IAM policy và NetworkPolicy để bắt buộc cô lập (enforce isolation).
- **Security baseline**: Áp dụng IAM tối thiểu quyền hạn (least-privilege) + lưu audit log trong 90 ngày. Mọi truy vấn dữ liệu quan sát (observability query) phải được giới hạn (bounded) theo tenant/service/env/window, tuyệt đối không cho phép truy vấn trên toàn bộ hệ thống.
- **No auto-remediation**: Đảm bảo 100% có sự rà soát của con người (human-reviewed). TF1 chỉ thực hiện phân loại (triage), tìm nguyên nhân gốc rễ và đề xuất hướng xử lý chứ không tự động sửa lỗi hệ thống. AI chỉ đưa ra gợi ý (suggest), con người luôn là bên đưa ra quyết định cuối cùng.

**Từ yêu cầu "audit trail mỗi AI decision link ticket field, traceability đầy đủ"**:
- **Auditability & Traceability**: Đảm bảo log lại 100% các quyết định của AI. Sử dụng kho lưu trữ kiểm toán bất biến (immutable audit store như S3 Object Lock), mỗi bản ghi (record) phải được gắn liên kết chặt chẽ `trace_id` <-> `ticket_id` <-> `tenant_id` để có thể truy vết toàn bộ dòng chảy xử lý.

**Từ yêu cầu "thuyết phục AIOps chọn platform của mình"**:
- **Availability >= 99.5%**: Cam kết EKS control plane có SLA đạt 99.95%. Vì đội ngũ on-call phụ thuộc hoàn toàn vào hệ thống, nền tảng không được phép ngừng hoạt động một cách âm thầm.
- **Onboarding SLA < 30 min/tenant**: Việc thiết lập môi trường cho tenant mới phải được thực hiện thông qua module IaC (Terraform) hoàn toàn tự động, không thực hiện cấu hình thủ công (manual provisioning).
- **Observability**: Cung cấp đầy đủ metrics + logs cho từng lượt gọi AI (AI invocation). Phát sinh dữ liệu về độ trễ (latency), độ tin cậy (confidence) và tỷ lệ lỗi (error rate) trên từng lượt gọi để hỗ trợ tracing từ đầu đến cuối (end-to-end).
- **Resilience / Fallback**: Cơ chế tự phục hồi và suy giảm hiệu năng mượt mà (graceful degradation). Áp dụng chính sách retry kèm exponential backoff và hàng đợi thư rác (DLQ) cho các cuộc gọi ra bên ngoài (external call như Jira, Slack, Bedrock); có phương án dự phòng (fallback) khi Jira/Slack/Bedrock gặp sự cố.

## 3. Differentiation angle (KEY)

### Angle chọn: **K8s-heavy / EKS-native AIOps Platform**

Nhóm chọn **EKS-native** không phải vì Lambda hoặc ECS không làm được, mà vì bài toán TF1 Triage Hub không đơn thuần là bài toán host một container hay chạy một function theo event. Đây là bài toán xây dựng một nền tảng AIOps cần gom nhiều lớp dữ liệu vận hành gồm alert, metric, log, deploy metadata, runtime state và ownership mapping về cùng một mô hình metadata nhất quán để AI có thể phân tích RCA theo đúng phạm vi `tenant_id + service + env + time_window`.

Vì vậy, hướng của nhóm không phải là “cheapest hosting”, mà là **production-like AIOps platform**: workload chạy trên Kubernetes, observability nằm gần workload, metadata được chuẩn hóa bằng Kubernetes labels/annotations, alert đi qua pipeline có retry/DLQ, và AI Engine chỉ được truy vấn context trong phạm vi được kiểm soát.

### 3.1 Vì sao không chọn Lambda làm trục chính?

Lambda vẫn rất phù hợp cho các bước ngắn, stateless và event-driven. Trong thiết kế của nhóm, Lambda nên được dùng ở **alert ingestion layer**:

```text
Alertmanager → Ingest Lambda → SQS
```

Ingest Lambda chỉ cần nhận webhook, validate incident seed, normalize event, tạo `incident_id/correlation_id/idempotency_key`, rồi push message vào SQS. Đây là phần Lambda làm rất tốt.

Tuy nhiên, **full AI Engine/RCA workflow** không chỉ là xử lý một event đơn giản. Nó cần nhận incident seed, query Prometheus/Loki/CloudWatch theo tenant/service/env/time-window, lấy deploy metadata nếu có, build context/evidence, chạy RCA, tính confidence, sinh report, rồi trả Slack/Jira payload. Các bước này phụ thuộc dữ liệu lẫn nhau: RCA cần metrics/logs/deploy evidence, report cần RCA result, Slack/Jira payload cần summary/report cuối cùng.

Nếu nhét toàn bộ workflow này vào một Lambda thì vẫn làm được cho MVP nhỏ, nhưng trade-off không tốt: latency query observability có thể không ổn định, time window có thể rộng, log volume có thể lớn, external call như Slack/Jira có thể timeout/rate-limit, và nếu fail ở bước cuối thì retry có thể làm chạy lại nhiều bước trước đó. Khi đó vẫn phải bổ sung state/idempotency để biết bước nào đã xong, artifact nào đã sinh ra, Slack/Jira đã gửi chưa.

Nếu tách thành nhiều Lambda thì sẽ phát sinh orchestration: Lambda fetch metrics, Lambda fetch logs, Lambda fetch deploy metadata, Lambda RCA, Lambda report, Lambda notify. Lúc này cần thêm Step Functions để điều phối, DynamoDB để lưu workflow state/idempotency, S3 để lưu context/report artifacts, và thiết kế retry/resume cho từng bước. Cách này khả thi, nhưng độ phức tạp orchestration tăng lên và không còn đơn giản hơn container worker.

Vì vậy, nhóm chọn hướng:

```text
Alertmanager
→ Ingest Lambda
→ SQS Incident Queue
→ TF1 Worker / AI Engine chạy container
→ RCA report
→ Slack/Jira payload
→ DynamoDB incident_state
```

Tóm lại: **Lambda tốt cho nhận alert, container tốt cho xử lý incident nhiều bước**.

### 3.2 Vì sao không chỉ chọn ECS/Fargate?

ECS Fargate là lựa chọn rất hợp lý nếu mục tiêu chính là giảm độ phức tạp vận hành. ECS giúp chạy container đơn giản hơn EKS, không cần quản lý nhiều Kubernetes resource, không cần vận hành ingress controller, RBAC, NetworkPolicy, CRD hay GitOps controller. Nếu chỉ cần chạy TF1 API service và background processor thì ECS/Fargate là trade-off rất mạnh.

Tuy nhiên, nhóm chọn EKS vì angle của nhóm là **K8s-native AIOps platform**, không chỉ là container hosting. Với TF1, giá trị lớn nhất nằm ở việc chuẩn hóa runtime metadata và observability context. Kubernetes cung cấp sẵn một mô hình rất phù hợp để gắn metadata vào workload:

```text
namespace      → tenant/env boundary
labels         → tenant_id, service, env, version, team
annotations    → runbook, owner, deploy metadata
ServiceAccount → identity/IAM boundary
Deployment/Pod → runtime state
Event          → runtime/change signal
```

Khi Prometheus/Loki/OTel thu metrics/logs, các Kubernetes labels này có thể đi kèm telemetry. Điều đó giúp AIOps query context đúng scope theo `tenant_id + service + env + time_window`, thay vì phải tự ghép nhiều nguồn metadata rời rạc.

ECS cũng làm được bằng task metadata, CloudWatch, EventBridge, tagging convention và CI/CD metadata. Nhưng khi bài toán cần liên kết workload, log, metric, alert rule, deployment state và runtime state, ECS thường cần nhiều custom glue hơn. EKS cho nhóm một mô hình nhất quán hơn để xây AIOps context.

### 3.3 EKS ecosystem phù hợp với AIOps hơn

EKS mở ra một hệ sinh thái rất tự nhiên cho bài toán này:

- **Prometheus Operator / ServiceMonitor / PrometheusRule**: thu metric và định nghĩa alert gần workload.
    
- **Alertmanager**: grouping, dedup, inhibition và route alert.
    
- **Loki / Promtail / Grafana Alloy / OTel Collector**: thu log/trace/metric theo Kubernetes metadata.
    
- **Argo CD / GitOps**: quản lý deployment và tạo nguồn deploy metadata rõ ràng.
    
- **Argo Rollouts**: hỗ trợ canary/rollback và tạo tín hiệu thay đổi release.
    
- **RBAC / ServiceAccount / IRSA**: kiểm soát quyền truy cập giữa workload và AWS service.
    
- **NetworkPolicy**: giới hạn luồng truy cập giữa namespace/service.
    
- **HPA / KEDA**: scale API/worker theo CPU, queue depth hoặc custom metric.
    
- **Namespace / labels / annotations**: chuẩn hóa tenant/service/env/version/owner/runbook.
    

Điểm mạnh nhất của EKS trong bài này là **metadata consistency**. Cùng một bộ metadata có thể đi xuyên suốt:

```text
Workload
→ Metrics
→ Logs
→ Alert
→ Deploy metadata
→ Runtime state
→ AIOps context query
→ RCA report
```

Đây là lợi thế quan trọng cho một hệ thống AI incident triage, vì chất lượng RCA phụ thuộc rất lớn vào việc context có đúng scope, đúng service, đúng tenant và đúng time window hay không.

### 3.4 Alert reliability: event-driven nhưng không serverless-first

Nhóm vẫn tận dụng serverless ở đúng chỗ. Alert là critical signal nên không nên xử lý trực tiếp kiểu fire-and-forget. Pipeline cần có buffer, retry, DLQ, replay và idempotency.

Thiết kế đề xuất:

```text
Alertmanager
→ Ingest Lambda
→ SQS Incident Queue
→ AIOps Worker trên EKS
→ TF1 AI Engine/RCA
→ Slack/Jira integration
→ DynamoDB incident_state
→ S3 audit/report artifact nếu cần
```

Trong đó:

```text
SQS = buffer, retry, DLQ, replay
DynamoDB = incident_state, idempotency, correlation, resume workflow
S3 = context/report/audit artifact
CloudWatch/Grafana = monitor chính incident pipeline
```

DynamoDB không chỉ để chống duplicate. Nó còn giúp biết incident đang ở bước nào, alert nào đã merge vào incident, Slack/Jira đã tạo chưa, lần retry trước fail ở đâu, và workflow có thể resume từ đúng bước lỗi thay vì chạy lại toàn bộ.

### 3.5 Trade-off chấp nhận

Nhóm chấp nhận EKS có chi phí và độ phức tạp vận hành cao hơn ECS/Fargate hoặc serverless-first:

- Có baseline cost cho EKS control plane và node group.
    
- Cần quản lý Kubernetes resource, ingress, RBAC, NetworkPolicy, autoscaling và observability stack.
    
- Cần discipline về labels/annotations để tránh metadata bị lệch.
    
- Debug có thể phức tạp hơn vì liên quan cả Kubernetes layer và AWS layer.
    

Tuy nhiên, trade-off này phù hợp với mục tiêu của nhóm: xây một nền tảng AIOps gần production, có observability-native, metadata consistency, GitOps, runtime context, isolation và incident workflow đáng tin cậy.

### 3.6 Win axis

**Ecosystem + Metadata Consistency + Observability + Production Realism**

EKS giúp nhóm khác biệt ở chỗ không chỉ chạy AI Engine, mà xây được một nền tảng để AI Engine có context tốt hơn: metric/log/deploy/runtime metadata được chuẩn hóa, query được giới hạn theo tenant/service/env/window, alert event có retry/DLQ, incident state có idempotency/resume, và toàn bộ pipeline có observability riêng.

### Locked T3 W11

24/06/2026
