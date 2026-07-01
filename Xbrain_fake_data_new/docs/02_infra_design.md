# Infrastructure Design - Task Force 1 · CDO 5

## 1. Architecture diagram

```text
User / Load Generator
        │
        ▼
Application Load Balancer
        │
        ▼
Demo App Workloads on EKS
        │
        ├── metrics
        │      ▼
        │   Prometheus
        │      ▼
        │   PrometheusRule
        │
        ├── logs
        │      ▼
        │   Loki
        │
        └── dashboards
               ▼
            Grafana
```

## 1.1 Main incident flow

```text
PrometheusRule
        │
        ▼
Alertmanager
Grouping / Inhibition / Silence / Repeat interval
        │
        ▼
Ingest Lambda
Validate + Normalize alert webhook
        │
        ▼
SQS FIFO Raw Alert Queue
Durable alert buffer
        │
        ▼
CDO Incident Correlator Worker on EKS
Deduplicate + Correlate alert events
        │
        ▼
AI Engine / RCA
Query Prometheus/Loki + perform RCA
        │
        ▼
Integration Lambda / CDO Integration Layer
Create / update Slack and Jira
        │
        ▼
Slack / Jira
Human-facing incident notification and tracking
```

## 1.2 Shared state and artifact stores

DynamoDB and S3 are not linear components in the main data path. They are shared stores used by multiple components in the incident pipeline.

```text
                         ┌──────────────────────────────┐
                         │ DynamoDB incident_state       │
                         │ State / Idempotency / Status  │
                         │ Workflow progress / Pointers  │
                         └──────────────────────────────┘
                                      ▲
                                      │ read/write
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
Ingest Lambda              CDO Correlator Worker          Integration Lambda
write ingest state         read/write workflow state      read/write Jira/Slack state
write queue state          write AI status                write integration status
optional S3 URI pointer    write S3 URI pointers          write S3 URI pointers
```

```text
                         ┌──────────────────────────────┐
                         │ S3 Incident Artifact Store    │
                         │ Payloads / Evidence / Reports│
                         │ Replay / Audit material       │
                         └──────────────────────────────┘
                                      ▲
                                      │ put/read object
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
Ingest Lambda              CDO Correlator Worker          AI Engine
optional raw alert          grouped alerts                context used
payload snapshot            incident context              evidence used
                             AI request/response           RCA output

                                      │
                                      ▼
                              Integration Lambda
                              Jira/Slack request
                              Jira/Slack response
```

Core rule:

```text
DynamoDB tracks workflow state and idempotency.
S3 stores incident artifacts and evidence.
DynamoDB stores pointers to S3 objects, not full reports or large payloads.
```

When a component creates an artifact:

```text
1. The component creates an artifact.
2. The component writes the artifact to S3.
3. The component updates DynamoDB with the S3 URI and artifact status.
```

Example:

```text
CDO Correlator Worker creates rca_report.json
→ PutObject to S3
→ Update DynamoDB:
   report.status = STORED
   report_s3_uri = s3://incident-artifacts/{tenant_id}/{service}/{incident_id}/rca_report.json
```

## 1.3 Caption

This architecture uses Amazon EKS as the main runtime platform for the demo application, the CDO Incident Correlator Worker, and the Kubernetes-native observability stack. User traffic enters through an Application Load Balancer and reaches demo workloads running inside EKS.

The application emits metrics and logs. Metrics are stored in Prometheus, logs are stored in Loki, and Grafana is used for dashboard and investigation. PrometheusRule evaluates metrics and fires alerts when abnormal conditions are detected.

Alertmanager acts as the first alert noise-control layer. It groups related alerts, inhibits dependent alerts, supports silence rules, and controls repeat intervals before alerts enter the incident pipeline.

Ingest Lambda receives the Alertmanager webhook, validates required metadata, normalizes the alert payload, optionally stores raw alert evidence in S3, writes initial ingest/queue state to DynamoDB if required, and sends the alert event to SQS FIFO.

SQS FIFO is used only for alert events. It provides durable buffering, retry, visibility timeout, FIFO DLQ, and backlog visibility. Metrics and logs do not go through SQS FIFO.

The CDO Incident Correlator Worker polls SQS FIFO, checks DynamoDB state for idempotency, deduplicates repeated alerts, groups related alerts into incident-level triggers, writes correlation artifacts to S3, updates DynamoDB workflow state, and calls the AI Engine only when an incident is new or meaningfully updated.

The AI Engine is owned by the AIOps/AI team. It receives the incident-level trigger, queries Prometheus and Loki through bounded read access, builds the metric/log context, performs RCA, and returns structured output such as root cause, confidence, evidence, missing context, and suggested actions. If scoped S3 access is granted, the AI Engine may also write the exact context and evidence it used for analysis to S3.

Integration Lambda or the CDO Integration Layer creates or updates Slack and Jira. It reads incident state from DynamoDB, reads reports or payloads from S3 if needed, sends updates to Slack/Jira, stores integration request/response audit records in S3, and updates DynamoDB with Slack/Jira status.

CloudWatch monitors AWS-side pipeline components such as Lambda, SQS FIFO, FIFO DLQ, DynamoDB, S3, and integration logs.

---

## 1.4 Data ownership boundary

The system has two different data flows.

### Normal observability flow

```text
App on EKS
→ Prometheus metrics
→ Loki logs
→ Grafana dashboards
→ SRE / AI Engine query by tenant/service/env/time window
```

This flow is used for normal monitoring, SRE investigation, dashboarding, and RCA context retrieval.

Important boundary:

```text
Metrics/logs do not go through SQS FIFO.
Metrics stay in Prometheus.
Kubernetes application logs stay in Loki.
AWS-side service logs/metrics stay in CloudWatch.
```

The AI Engine can query observability data through bounded access.

Recommended query dimensions:

```text
tenant_id
service
env
namespace
time_window
alertname
severity
```

### Alert incident flow

```text
PrometheusRule
→ Alertmanager
→ Ingest Lambda
→ SQS FIFO
→ CDO Incident Correlator Worker
→ AI Engine / RCA
→ Integration Lambda / CDO Integration Layer
→ Slack / Jira
```

This flow is used only when an alert event is fired and the incident triage workflow needs to start.

Key distinction:

```text
Metric/log raw = analysis data.
Alert event = incident workflow trigger.
```

Metrics and logs are not pushed through the alert pipeline. The alert pipeline only carries incident trigger events and workflow state transitions.

---

## 1.5 Responsibility boundary: CDO vs AIOps / AI Engine

CDO does not own RCA logic and does not build the final AI reasoning logic.

CDO owns:

```text
- runtime platform on EKS
- demo application runtime environment
- Prometheus, Grafana, Alertmanager, Loki
- consistent observability metadata
- bounded read access to Prometheus/Loki/CloudWatch
- network policy, IAM, RBAC, and secret access boundary
- alert ingestion from Alertmanager
- SQS FIFO alert buffering and FIFO DLQ
- alert deduplication and correlation
- incident workflow state in DynamoDB
- incident artifact/evidence storage in S3
- Jira/Slack integration reliability if assigned to CDO
- CloudWatch monitoring for AWS-side pipeline services
```

AIOps / AI Engine owns:

```text
- receive incident-level trigger from CDO
- query Prometheus metrics by tenant/service/env/window
- query Loki logs by tenant/service/env/window
- normalize and aggregate metrics/logs
- build time-window context
- calculate baseline/trend/anomaly
- perform RCA
- return root cause, confidence, evidence, missing context, and suggested actions
- optionally write AI context/evidence/RCA artifacts to scoped S3 prefix
```

Final boundary:

```text
CDO owns platform, alert reliability, workflow state, and audit storage.
AI owns observability interpretation and RCA.
```

AI Engine should not own SQS FIFO retry, incident idempotency, or Jira/Slack side-effect control.

---

# 2. Component table

|Component|AWS Service / Tool|Reason|Cost note|
|---|---|---|---|
|Compute|Amazon EKS|Main runtime for demo app, CDO Correlator Worker, and observability stack. Chosen because Kubernetes gives consistent workload metadata, namespace, labels, service discovery, NetworkPolicy, and GitOps-friendly deployment context.|Higher fixed cost than ECS/Lambda because of EKS control plane and worker nodes. Accepted for Kubernetes-native design.|
|API entry|ALB + AWS Load Balancer Controller|Public entry point for user/load generator traffic into demo app on EKS. Managed through Kubernetes Ingress.|ALB has hourly and traffic-based cost. Keep one shared ALB for MVP.|
|Metrics|Prometheus|Stores application and Kubernetes metrics, evaluates PrometheusRule, and provides query source for SRE/AIOps.|Runs inside EKS, consumes node CPU/memory/storage. Retention should be limited for MVP.|
|Logs|Loki|Stores Kubernetes workload logs and supports label-based query by namespace, pod, service, tenant_id, env, and time window.|Runs inside EKS. Cost depends on log volume and retention.|
|Dashboard|Grafana|Dashboard and investigation UI for metrics, logs, and alert status.|Runs inside EKS. Low MVP footprint.|
|Alert noise control|Alertmanager|First-layer alert noise control: grouping, inhibition, silence, group_wait, repeat_interval.|Runs as part of monitoring stack.|
|Alert ingestion|Ingest Lambda|Receives Alertmanager webhook, validates required fields, normalizes alert payload, optionally writes raw evidence, and sends message to SQS FIFO.|Low cost for MVP because alert volume is small.|
|Event queue|SQS FIFO Raw Alert Queue + FIFO DLQ|Durable alert buffer, retry, visibility timeout, backlog visibility, FIFO DLQ for failed alerts. Decouples monitoring from downstream processing.|Low for capstone traffic. Must monitor backlog and FIFO DLQ.|
|Incident worker|CDO Incident Correlator Worker on EKS|Polls SQS FIFO, deduplicates alerts, correlates related alerts, updates DynamoDB, writes S3 artifacts, and calls AI Engine when needed.|Runs on EKS worker nodes. Can scale by backlog.|
|Incident state|DynamoDB|Stores incident_state, alert_fingerprint, correlation_key, workflow progress, retry_count, Jira ticket ID, Slack thread ID, last_error, and S3 URI pointers. Enables idempotency.|Low for MVP. On-demand mode is simpler for unpredictable demo traffic.|
|Artifact storage|S3|Stores original alert payload, grouped alerts, AI request/response, AI context/evidence, RCA report, Jira/Slack payloads, and replay/debug material.|Low cost. Can use lifecycle policy to move older evidence to cheaper tier.|
|RCA engine|AI Engine|Performs RCA by querying Prometheus/Loki and analyzing incident context.|Owned by AIOps team. Cost depends on model/runtime.|
|External integration|Integration Lambda / CDO Integration Layer + Jira + Slack|Creates/updates Jira and Slack. One incident should map to one Jira ticket and one Slack thread.|External service cost depends on account/license, not core AWS infra.|
|AWS-side monitoring|CloudWatch|Monitors Lambda logs, SQS FIFO backlog, FIFO DLQ count, DynamoDB errors/throttles, S3 errors, and AWS integration logs.|Cost depends on log volume and retention. Set retention policy.|
|Secret management|Secrets Manager / SSM|Stores Jira token, Slack token/webhook, AI Engine API key, and runtime secrets.|Low if secret count is small.|
|Pod AWS access|IAM + IRSA / EKS Pod Identity|Allows EKS pods to access SQS FIFO, DynamoDB, S3, and Secrets Manager with least privilege.|No major direct cost, but important for security.|

---

## 2.1 Component responsibility

|Component|Does|Does not do|
|---|---|---|
|ALB|Routes public traffic to demo app/API service on EKS.|Does not call AI Engine directly.|
|EKS|Runs app workloads, Worker, and observability stack.|Does not store durable incident state by itself.|
|Demo App|Generates traffic, metrics, logs, and failure scenarios.|Does not perform RCA or create Jira/Slack.|
|Prometheus|Scrapes metrics, stores time-series, evaluates rules.|Does not store application logs.|
|Loki|Stores Kubernetes application/workload logs.|Does not monitor AWS managed services.|
|Grafana|Provides dashboard and investigation UI.|Does not own incident workflow state.|
|Alertmanager|Groups, inhibits, silences, and controls repeated alerts before ingestion.|Does not perform deep multi-service incident correlation or Jira/Slack idempotency.|
|Ingest Lambda|Validates and normalizes alert webhook, optionally stores raw alert artifact, writes initial ingest/queue state, pushes alert to SQS FIFO.|Does not do RCA, does not deeply query metrics/logs, does not call AI Engine for RCA, does not create Jira/Slack.|
|SQS FIFO|Stores alert event durably and supports retry/FIFO DLQ.|Does not store metric/log raw and does not write to DynamoDB/S3 by itself.|
|SQS FIFO DLQ|Stores messages that fail too many times.|Does not fix failed messages automatically.|
|CDO Correlator Worker|Polls SQS FIFO, deduplicates alerts, correlates related alerts, updates DynamoDB, writes S3 artifacts, decides whether to call AI Engine.|Does not own RCA reasoning, baseline calculation, anomaly interpretation, or deep log analysis.|
|DynamoDB|Stores incident state, idempotency keys, workflow progress, Jira/Slack IDs, and pointers to S3 artifacts.|Does not store raw logs, full metric windows, or large AI evidence.|
|S3 Artifact Store|Stores audit evidence, AI request/response, payload snapshots, RCA reports, and replay/debug material.|Does not track live workflow state and does not serve as the state machine.|
|AI Engine|Queries observability data, builds RCA context, performs reasoning, optionally writes AI artifacts to S3, returns RCA/confidence/suggested actions.|Does not own alert durability, SQS FIFO retry, pipeline state, or Jira/Slack side-effect control.|
|Integration Lambda / CDO Integration Layer|Creates/updates Jira and Slack, writes request/response audit artifacts, updates DynamoDB.|Does not perform RCA.|
|Jira/Slack|Human-facing incident tracking and notification.|Does not act as source of truth for workflow state.|
|CloudWatch|Monitors AWS-side pipeline components.|Does not replace Loki for Kubernetes application logs.|

---

# 3. Differentiation angle deep-dive

## 3.1 Why this angle?

Chosen angle:

```text
Reliable Incident Triage Pipeline with Alert Storm Control and AI Call Gating
```

Điểm khác biệt chính của thiết kế này không chỉ nằm ở việc chọn EKS. EKS là runtime foundation. Giá trị thật của kiến trúc nằm ở cách CDO biến các alert nhiễu, lặp và phân mảnh thành incident-level trigger đáng tin cậy trước khi gọi AI Engine.

TF1 Triage Hub không chỉ là bài toán host container. Đây là bài toán xây một nền tảng AIOps incident triage, nơi CDO cần kết nối workload runtime, observability, alerting, deployment metadata, incident state và human integration thành một flow nhất quán.

Trong incident thật, một root cause có thể tạo ra nhiều alert ở nhiều service khác nhau:

```text
redis RedisTimeout
payment-api HighLatency
payment-api High5xx
checkout-api Timeout
frontend ErrorRateHigh
```

Nếu thiết kế đơn giản theo kiểu gửi từng alert trực tiếp sang AI Engine:

```text
Alert
→ AI Engine
→ Jira/Slack
```

thì hệ thống có nhiều rủi ro:

```text
- AI Engine bị gọi quá nhiều lần cho cùng một incident
- Jira ticket có thể bị tạo trùng
- Slack channel có thể bị spam
- RCA bị phân mảnh theo từng alert
- operator có thể hiểu nhầm symptom là incident riêng
- cost và latency tăng không cần thiết
```

Thiết kế CDO đề xuất thêm một reliable incident pipeline trước AI processing:

```text
Main incident flow:
PrometheusRule
→ Alertmanager
→ Ingest Lambda
→ SQS FIFO Raw Alert Queue
→ CDO Incident Correlator Worker
→ AI Engine only when needed
→ Integration Lambda / CDO Integration Layer
→ Jira/Slack
```

DynamoDB và S3 không nằm tuyến tính trong main flow. Chúng là shared stores được nhiều component đọc/ghi:

```text
Side stores:
- DynamoDB incident_state:
  workflow state, idempotency, retry status, current step, Jira/Slack IDs, S3 URI pointers

- S3 audit/evidence store:
  raw alert payload, grouped alerts, AI request/response, RCA evidence, Jira/Slack payloads, replay material
```

Thiết kế này có ba lớp bảo vệ chính:

```text
1. Alertmanager giảm noise cơ bản trước ingestion.
2. SQS FIFO bảo vệ alert delivery bằng durable buffering, retry và FIFO DLQ.
3. CDO Correlator + DynamoDB deduplicate alert, gom alert liên quan thành incident và tránh duplicate Jira/Slack.
```

Core statement:

```text
SQS FIFO protects alert delivery.
DynamoDB protects workflow state and idempotency.
S3 preserves audit evidence and replay material.
The CDO Correlator protects the AI Engine from alert storms.
EKS provides the ecosystem where these platform components can run close to the workload.
```

---

## 3.2 Why not Lambda or ECS as the main platform?

### Why not Lambda as the main compute?

Lambda phù hợp cho short-lived event handling, nhưng TF1 Triage Hub không chỉ là một API hoặc một simple event processor.

Nền tảng này cần chạy nhiều thành phần có tính platform và long-running:

```text
- demo app workloads
- CDO Incident Correlator Worker
- Prometheus
- Loki
- Grafana
- Alertmanager
- GitOps-managed deployment context
- Kubernetes metadata quanh workload
```

Nếu dùng Lambda làm compute chính, team vẫn cần một runtime khác để chạy observability stack và worker-like components. Điều đó làm hệ thống bị chia thành nhiều execution model khác nhau:

```text
- Lambda cho alert/API
- một runtime khác cho app
- một runtime khác cho observability
- một cách khác để quản lý deployment metadata
```

Kết quả là RCA context khó nhất quán hơn. AI Engine cần biết alert liên quan tới service nào, pod/task nào, deployment version nào, namespace nào, tenant nào và logs/metrics nào trong cùng time window. Lambda không cung cấp một workload metadata ecosystem đủ tự nhiên cho bài toán này.

Vì vậy, Lambda vẫn được dùng, nhưng chỉ là thin adapter:

```text
Alertmanager
→ Ingest Lambda
→ SQS FIFO
```

Lambda chỉ làm:

```text
- receive webhook
- validate alert payload
- normalize alert event
- send message to SQS FIFO
- optionally write initial ingest state or raw payload evidence
```

Lambda không làm:

```text
- main runtime
- observability platform
- long-running worker
- incident correlation sâu
- RCA
```

Decision:

```text
Use Lambda only for lightweight alert ingestion.
Do not use Lambda as the main compute platform.
```

---

### Why not ECS Fargate?

ECS Fargate chạy container tốt, đơn giản hơn EKS và thường rẻ hơn cho bài toán host service thông thường.

Lý do không chọn ECS không phải vì ECS không làm được. ECS vẫn có thể chạy demo app, worker và expose service qua ALB.

Nhưng TF1 cần nhiều hơn container hosting. TF1 cần một ecosystem thống nhất cho:

```text
- workload runtime
- observability
- alerting
- deployment evidence
- security boundary
- incident metadata
- bounded RCA query access
```

Với ECS, các context cần cho RCA thường nằm rải ở nhiều nơi:

```text
- ECS service/task metadata
- CloudWatch metrics/logs
- EventBridge deployment events
- ALB target group
- CI/CD pipeline records
- AWS resource tags
- custom naming convention
```

Ví dụ khi alert `High5xx` xảy ra ở `checkout-api`, AIOps cần biết:

```text
- tenant nào bị ảnh hưởng
- env nào bị ảnh hưởng
- service nào lỗi
- task/pod nào unhealthy
- version nào đang chạy
- có rollout nào vừa xảy ra không
- metrics/logs nào thuộc cùng time window
- alert này liên quan tới service group nào
```

Với ECS, các thông tin này có thể lấy được, nhưng CDO phải viết thêm glue logic để nối ECS metadata, CloudWatch, EventBridge, ALB, CI/CD records và tags thành một incident context thống nhất.

Với EKS, nhiều thông tin này nằm tự nhiên trong Kubernetes workload model:

```text
- namespace
- pod
- deployment
- service
- labels
- annotations
- rollout state
- NetworkPolicy
- RBAC
- ServiceAccount
```

Cùng một label model có thể đi xuyên suốt:

```text
Kubernetes workload
→ Prometheus metrics
→ Loki logs
→ Alertmanager alert labels
→ ArgoCD deployment history
→ CDO Correlator incident_state
→ AI Engine bounded query contract
```

Vì vậy, ECS là lựa chọn tốt nếu mục tiêu là chạy container đơn giản, chi phí thấp. Nhưng với TF1, mục tiêu là xây một AIOps-ready incident platform có metadata nhất quán quanh workload.

Decision:

```text
Do not choose ECS as the main platform for TF1 MVP.
Choose EKS because the project benefits more from Kubernetes-native observability,
alerting, GitOps evidence, security boundary, and workload metadata consistency.
```

---

## 3.3 Why EKS still matters in this angle

EKS phù hợp hơn không phải vì ECS không chạy được container. ECS hoàn toàn có thể chạy service ổn, rẻ hơn và đơn giản hơn trong nhiều trường hợp.

Điểm khác biệt là TF1 Triage Hub không chỉ cần một nơi để host container. TF1 cần một hệ sinh thái vận hành đủ mạnh để gom runtime state, observability data, alerting, deployment evidence, security boundary và tenant metadata về cùng một mô hình nhất quán cho incident triage.

EKS phù hợp hơn vì Kubernetes cung cấp một ecosystem thống nhất quanh workload:

```text
1. Workload runtime ecosystem
   - Pod
   - Deployment
   - Service
   - Namespace
   - Labels
   - Annotations
   - ReplicaSet / rollout state

2. Observability ecosystem
   - Prometheus
   - ServiceMonitor / PodMonitor
   - Loki
   - Grafana
   - Alertmanager
   - Kubernetes events
   - app/workload labels attached to metrics and logs

3. Alerting ecosystem
   - PrometheusRule
   - Alertmanager grouping
   - inhibition
   - silence
   - repeat interval
   - alert labels such as tenant_id, service, env, severity

4. GitOps and deployment evidence ecosystem
   - Argo CD
   - Helm / Kustomize
   - deployment diff
   - rollout history
   - rollback evidence
   - Git commit / image version mapping

5. Security and isolation ecosystem
   - Namespace
   - RBAC
   - ServiceAccount
   - IRSA / EKS Pod Identity
   - NetworkPolicy
   - Secret integration
   - workload-level access boundary

6. Platform metadata ecosystem
   - tenant_id
   - service
   - env
   - namespace
   - pod
   - deployment
   - version
   - owner
   - service_group
```

Các phần này không đứng rời rạc. Chúng xoay quanh cùng một Kubernetes workload model.

Ví dụ một service `checkout-api` có thể có metadata:

```text
tenant_id = tenant-a
service = checkout-api
env = prod
namespace = tenant-a-prod
deployment = checkout-api
pod = checkout-api-7c8d9f
version = v1.4.2
owner = checkout-team
service_group = checkout-stack
```

Metadata này có thể xuất hiện xuyên suốt trong:

```text
- Kubernetes Deployment labels
- Pod labels
- Prometheus metrics labels
- Loki log labels
- Alertmanager alert labels
- Argo CD deployment history
- NetworkPolicy/RBAC boundary
- CDO Correlator incident_state
- AI Engine bounded query contract
```

Khi alert `High5xx` xảy ra ở `checkout-api`, hệ thống không chỉ biết “service này lỗi”. Hệ thống có thể nối alert đó với:

```text
alert
→ tenant
→ environment
→ service
→ namespace
→ pod
→ deployment version
→ recent rollout
→ metrics window
→ logs window
→ related alerts
→ incident trigger
```

Đây là điểm quan trọng cho AIOps/RCA. AI Engine cần query đúng metric/log theo tenant, service, env và time window. CDO cần đảm bảo dữ liệu đó có metadata nhất quán từ lúc workload chạy, sinh metric/log, tạo alert, đi qua correlator, rồi thành incident trigger.

Nếu dùng ECS, hệ thống vẫn làm được, nhưng context thường nằm rải ở nhiều nơi:

```text
- ECS task/service metadata
- CloudWatch metrics/logs
- EventBridge deployment events
- ALB target group
- CI/CD pipeline records
- AWS resource tags
- custom naming convention
```

CDO sẽ phải viết thêm glue logic để nối các nguồn này thành một incident context thống nhất. Với EKS, nhiều phần context đã nằm tự nhiên trong Kubernetes ecosystem thông qua namespace, labels, annotations, service discovery, rollout state và observability labels.

Vì vậy, lý do chọn EKS không phải là “EKS chạy container tốt hơn ECS”. Lý do là:

```text
EKS giúp CDO xây một AIOps-ready operational platform,
nơi runtime, observability, alerting, GitOps evidence,
security boundary và incident metadata dùng chung một workload model.
```

---

## 3.4 Architectural advantages

Không claim benchmark numbers trong phần này. So sánh dưới đây dựa trên capability kiến trúc.

|Axis|Proposed design|Simple direct-alert design|
|---|---|---|
|Alert durability|Alert event được lưu trong SQS FIFO, có retry và FIFO DLQ.|Alert có thể fail nếu downstream service unavailable.|
|Alert storm handling|Alertmanager + Correlator giảm noise trước khi gọi AI.|Mỗi alert có thể gọi AI riêng.|
|Duplicate prevention|DynamoDB lưu fingerprint/state và ngăn duplicate side effects.|Retry có thể tạo duplicate Jira/Slack.|
|Incident correlation|Nhiều alert liên quan có thể được gom thành một incident.|Mỗi alert có thể bị xem là một incident riêng.|
|AI protection|AI chỉ nhận incident-level trigger khi cần.|AI nhận raw alert spam.|
|Recovery|Worker retry từ SQS FIFO và reuse DynamoDB state.|Stateless retry có thể lặp lại step đã hoàn tất.|
|Debug/replay|SQS FIFO DLQ + S3 audit cung cấp evidence và replay material.|Khó inspect/replay failed alert hơn.|
|Ops visibility|Quan sát được SQS FIFO backlog, FIFO DLQ, Lambda errors, DynamoDB errors và CloudWatch logs.|Khó xác định failure point hơn.|
|Metadata consistency|EKS cung cấp metadata nhất quán quanh namespace, pod, service, deployment, version, tenant_id, env.|ECS vẫn làm được nhưng thường cần nhiều custom glue giữa service/task metadata, CloudWatch, EventBridge, ALB, CI/CD records và resource tags.|

---

## 3.5 Weakness accepted

Thiết kế này phức tạp hơn direct webhook-to-AI.

Nó thêm:

```text
- EKS cluster operation
- Alertmanager configuration
- Ingest Lambda
- SQS FIFO + FIFO DLQ
- CDO Correlator Worker
- DynamoDB incident_state
- S3 audit store
- IAM/IRSA permissions
- CloudWatch monitoring for pipeline components
```

Team chấp nhận trade-off này vì mục tiêu không chỉ là demo happy path. Mục tiêu là xây một reliable incident triage pipeline có thể survive retry, giảm alert storm, tránh duplicate Jira/Slack và cung cấp audit evidence.

MVP limitation:

```text
Correlation is rule-based.
It is not yet topology-aware, trace-aware, or AI-assisted.
```

Future improvements có thể thêm:

```text
- service dependency graph
- topology-aware correlation
- OpenTelemetry tracing
- adaptive time windows
- AI-assisted correlation
- human feedback loop
```

Final takeaway:

```text
Nếu mục tiêu chỉ là chạy container rẻ và đơn giản, ECS là lựa chọn tốt hơn.

Nếu mục tiêu là xây một incident triage platform cần metadata nhất quán,
observability gần workload, GitOps evidence, alert correlation,
bounded RCA query access và reliable incident workflow,
EKS + SQS FIFO + DynamoDB + Correlator là hướng phù hợp hơn.
```

---

# 4. Multi-tenant approach

## 4.1 Tenant model

In the MVP, multi-tenancy is handled mainly through metadata, not a full SaaS tenant lifecycle.

Required metadata:

```text
tenant_id
service
env
namespace
workload
timestamp
alertname
severity
```

Example tenant IDs for demo:

```text
tenant-a
tenant-b
```

Production can use UUID v4, but the MVP does not claim full production tenant onboarding.

---

## 4.2 Isolation pattern

Data isolation uses a pooled model by metadata.

```text
Prometheus labels include tenant_id, service, env.
Loki labels include tenant_id, service, env, namespace, pod.
DynamoDB keys include tenant_id, service, incident_id, and correlation_key.
S3 audit prefix includes tenant_id/service/incident_id.
```

Compute isolation uses a shared EKS cluster.

```text
Demo app workloads can be separated by namespace.
CDO pipeline components run in platform/ops namespace.
AIOps/AI Engine can run in its own namespace or external runtime.
```

This pattern is suitable for capstone scope because the target is to prove reliable alert handling and incident correlation, not to implement full SaaS tenant isolation with per-tenant accounts or clusters.

---

## 4.3 Bounded access for AI Engine

CDO must not give the AI Engine unrestricted access to the entire monitoring stack.

Access should be bounded by:

```text
tenant_id
env
service or service_group
time window
read-only permission
internal network path
```

Possible enforcement mechanisms:

```text
- internal query gateway/API
- read-only service account or token
- namespace and NetworkPolicy boundary
- IAM/RBAC boundary if AWS-side access is needed
- query convention requiring tenant_id/service/env/window
- audit logging of AI queries
- scoped S3 prefix if AI writes RCA artifacts
```

Important note:

```text
Prometheus/Loki labels alone are not strong tenant isolation.
For MVP, they are acceptable as metadata-based scoping.
For production, a query gateway or stronger access-control layer should be added.
```

---

## 4.4 Tenant onboarding flow

MVP onboarding:

```text
1. Create tenant_id or service label in config.
2. Attach tenant_id/service/env to metrics, logs, and alert labels.
3. Create namespace if workload separation is needed.
4. Configure Alertmanager grouping by tenant/env/service/severity.
5. Verify alert payload has required metadata.
6. Verify AI Engine can query bounded data by tenant/service/env/window.
7. Verify DynamoDB keys and S3 prefixes include tenant/service/incident identity.
```

Future production onboarding:

```text
POST /platform/v1/tenants
→ Terraform/Step Function provisions namespace/config/IAM
→ create tenant-scoped observability labels
→ create tenant-scoped S3 prefix and access policy
→ create secret and access policy
→ smoke test
→ tenant ready callback
```

Do not claim this full lifecycle is implemented in the MVP unless it is actually built.

---

## 4.5 Noisy neighbor mitigation

MVP controls:

```text
- ResourceQuota and LimitRange per namespace if multiple tenants are simulated
- Alertmanager grouping to reduce alert spam before Lambda/SQS FIFO
- SQS FIFO backlog visibility to detect high alert volume
- Correlator gating to avoid repeated AI calls
- bounded observability queries by tenant/service/env/time window
- DynamoDB idempotency keys to prevent duplicate side effects
- S3 prefix organization for tenant/service/incident artifacts
```

Avoid claiming exact quota numbers unless tested.

---

# 5. Key design decisions / alternatives considered

## 5.1 Why Amazon EKS?

Alternatives:

```text
Option A: Lambda + API Gateway
Option B: ECS Fargate + ALB
Option C: Amazon EKS
```

Lambda is good for short-lived event handling, but TF1 is not only an API or simple event processor. The platform needs to run demo workloads, worker processes, observability stack, Alertmanager, Grafana, Loki, Prometheus, and Kubernetes-style metadata around workloads.

Lambda is still used, but only as lightweight alert ingestion and integration components.

ECS can run containers well and is often simpler and cheaper than EKS. However, this project benefits from Kubernetes-native concepts:

```text
- namespace
- labels
- annotations
- service discovery
- NetworkPolicy
- GitOps
- rollout metadata
- pod/deployment identity
- observability close to workload
```

EKS gives one consistent metadata model around:

```text
tenant_id
service
env
namespace
pod
deployment
version
```

This metadata can be used across runtime, metrics, logs, alerts, deployment history, and bounded query access for AIOps.

Decision:

```text
Choose EKS because TF1 is an AIOps-ready incident triage platform,
not only a cheap container hosting problem.
```

---

## 5.2 Why AWS Load Balancer Controller + ALB?

Alternatives:

```text
Option A: NodePort
Option B: NGINX Ingress only
Option C: API Gateway
Option D: AWS Load Balancer Controller + ALB
```

The demo app and possible API entrypoints run inside EKS. AWS Load Balancer Controller allows Kubernetes Ingress to manage ALB automatically.

Benefits:

```text
- Kubernetes-native ingress management
- no manual ALB/target group management
- works naturally with EKS service discovery
- supports path-based and host-based routing
- fits GitOps workflow because ingress config lives in Kubernetes manifests
```

API Gateway is useful for managed API auth/throttling, but this MVP mainly exposes containerized workloads inside EKS. ALB is simpler and more natural for HTTP ingress into Kubernetes workloads.

Decision:

```text
Use ALB + AWS Load Balancer Controller for public app/API entry into EKS.
```

---

## 5.3 Why Ingest Lambda before SQS FIFO?

Alternatives:

```text
Option A: Alertmanager sends directly to SQS FIFO
Option B: Alertmanager sends directly to Worker/API
Option C: Alertmanager sends to Ingest Lambda, then Lambda sends to SQS FIFO
```

Alertmanager webhook payload may need validation and normalization before becoming an internal alert event.

Ingest Lambda performs:

```text
- receive webhook
- validate required fields
- normalize payload
- attach tenant/service/env/window metadata
- generate idempotency key or correlation fields if needed
- optionally store raw/normalized alert payload in S3
- optionally write ingest and queue state to DynamoDB
- send message to SQS FIFO
```

It is intentionally lightweight.

It does not:

```text
- perform RCA
- deeply query metrics/logs
- correlate incidents
- call AI Engine for RCA
- create Jira/Slack
```

Decision:

```text
Use Ingest Lambda as a thin adapter between Alertmanager webhook and SQS FIFO.
```

---

## 5.4 Why SQS FIFO + FIFO DLQ?

Alternatives:

```text
Option A: Direct webhook to AI Engine
Option B: Lambda retry only
Option C: SQS FIFO + FIFO DLQ
```

Alert event is a critical incident trigger. If the alert is lost, the triage workflow may never start.

SQS FIFO provides:

```text
- durable alert buffer
- retry through visibility timeout
- FIFO DLQ for poison messages
- backlog visibility
- decoupling between monitoring and downstream processing
- replay/debug capability
```

Lambda retry only protects function execution in some cases. SQS FIFO protects the incident event lifecycle more explicitly.

SQS FIFO is at-least-once delivery, so duplicate processing is possible. DynamoDB is required for idempotency and workflow state.

Decision:

```text
Use SQS FIFO for alert events only.
Do not use SQS FIFO for metric/log raw data.
```

---

## 5.5 Why DynamoDB for incident_state?

Alternatives:

```text
Option A: No database
Option B: RDS/Aurora
Option C: DynamoDB
```

State is needed because the workflow has retries and external side effects.

Example:

```text
Worker receives alert
→ AI RCA completes
→ Integration Lambda creates Jira successfully
→ Integration Lambda crashes before Slack
→ retry happens
```

Without state, the system may create duplicate Jira tickets or duplicate Slack messages.

DynamoDB stores compact workflow state:

```text
- incident_id
- correlation_key
- alert_fingerprint
- status
- current_step
- retry_count
- last_error
- jira_ticket_id
- slack_thread_id
- S3 URI pointers
- created_at
- updated_at
```

Decision:

```text
Use DynamoDB as incident state store, idempotency store, workflow progress store, and pointer index for S3 artifacts.
```

---

## 5.6 Why S3 Audit Store?

Alternatives:

```text
Option A: Store everything in DynamoDB
Option B: Store audit evidence in S3
```

DynamoDB should store current state, not large evidence objects.

S3 can store:

```text
- original alert payload
- normalized alert payload
- grouped alert payload
- incident trigger sent to AI
- AI request
- AI response
- context used by AI
- evidence used by AI
- RCA report
- Jira request/response
- Slack request/response
- replay/debug material
```

This helps answer:

```text
What did the system receive?
What did the AI receive?
What context and evidence did AI use?
Can we replay/debug this incident?
What exactly was sent to Jira/Slack?
```

Decision:

```text
Use DynamoDB for current state and S3 pointers.
Use S3 for detailed audit evidence and replay material.
```

---

## 5.7 Why Prometheus/Loki + CloudWatch split?

CloudWatch is strong for AWS managed services, but Kubernetes workload metrics/logs are easier to work with through Kubernetes-native labels.

Prometheus/Loki fit EKS workloads because they can use labels such as:

```text
namespace
pod
container
service
tenant_id
env
```

CloudWatch is still needed for AWS-side services:

```text
- Lambda logs/errors/duration
- SQS FIFO backlog and FIFO DLQ metrics
- DynamoDB throttles/errors
- S3 request/error metrics if enabled
- AWS integration logs
```

Decision:

```text
Prometheus = EKS/app metrics.
Loki = EKS/app logs.
Grafana = dashboard/investigation UI.
CloudWatch = AWS-side pipeline monitoring.
S3 = audit/evidence store.
```

---

## 5.8 Why Alertmanager + CDO Correlator, not Alertmanager only?

Alertmanager is good for basic noise control:

```text
- grouping
- inhibition
- silence
- repeat interval
```

But Alertmanager does not fully understand:

```text
- incident workflow state
- Jira/Slack side effects
- AI call gating
- cross-service incident correlation
- S3 artifact pointers
- replay state
```

The CDO Correlator handles:

```text
- alert_fingerprint
- correlation_key
- incident_state
- AI call decision
- duplicate prevention
- workflow resume
- S3 artifact tracking
```

Decision:

```text
Use Alertmanager as Layer 1 noise control.
Use CDO Correlator + DynamoDB as Layer 2 incident correlation and idempotency control.
```

---

# 6. Scaling strategy

## 6.1 Vertical scaling

Increase CPU/memory for:

```text
- Demo App pods
- CDO Correlator Worker pod
- Prometheus
- Loki
- Grafana
- Alertmanager
```

Use this when one component is resource constrained but not horizontally bottlenecked.

---

## 6.2 Horizontal scaling

Scale out:

```text
Demo App:
- by CPU/memory or request traffic

CDO Correlator Worker:
- by SQS FIFO visible messages
- by age of oldest message
- by worker error rate

Integration Lambda:
- naturally scales by invocation volume
- should still protect Jira/Slack with retry and rate-limit logic

Observability stack:
- start with MVP sizing
- increase replicas/storage only if needed

AI Engine:
- owned by AIOps team
- CDO protects it by reducing repeated calls
```

For MVP, fixed replicas are acceptable. HPA/KEDA can be added if there is enough time.

---

## 6.3 Scaling triggers

Recommended triggers:

```text
- CPU usage
- memory usage
- SQS FIFO ApproximateNumberOfMessagesVisible
- SQS FIFO ApproximateAgeOfOldestMessage
- worker error rate
- Lambda error rate
- DynamoDB throttle/error rate
- S3 put/read error rate
- AI Engine latency/error rate
- Jira/Slack integration error rate
```

Do not claim exact thresholds unless measured.

---

## 6.4 AI call control

The Correlator should not call AI for every alert.

Call AI only when:

```text
- new incident is created
- severity increases
- new important alert type appears
- incident lasts longer than a threshold
- previous RCA confidence is low
- human requests re-analysis
```

Skip AI call when:

```text
- alert is duplicate
- alert belongs to existing incident
- only alert_count or last_seen_at changes
- message is only SQS FIFO retry
```

This protects AI cost and avoids repeated RCA.

---

## 7. Failure modes + recovery

| Failure | Detection | Recovery | RTO/RPO |
|---|---|---|---|
|Demo app pod crash|Kubernetes events, Prometheus target down|Kubernetes restarts/reschedules pod|RTO: <1 min / RPO: 0 (stateless app)|
|Prometheus unavailable|Grafana/Prometheus health, scrape failure|Restart pod, restore config/storage if needed|RTO: <5 min / RPO: Metrics gap during outage|
|Loki unavailable|Grafana Explore error, Loki pod health|Restart Loki/agent, inspect storage|RTO: <5 min / RPO: Logs gap during outage|
|Alert storm|Alert volume spike, Alertmanager dashboard, SQS FIFO backlog|Alertmanager grouping/inhibition + Correlator gating|RTO: N/A (throttled) / RPO: 0 (events buffered in SQS FIFO)|
|Ingest Lambda error|CloudWatch Lambda error/duration|Fix schema/config and replay if source supports retry|RTO: <5 min (auto) / RPO: Potential loss if source does not retry|
|SQS FIFO backlog high|CloudWatch SQS FIFO visible messages / age|Scale worker, inspect downstream latency/errors|RTO: <10 min (scale) / RPO: 0 (retained in queue)|
|Worker crash|Pod restart, worker logs, SQS FIFO message visible again|SQS FIFO retries message; worker resumes using DynamoDB state|RTO: <2 min / RPO: 0 (state in DynamoDB)|
|Duplicate alert|Same alert_fingerprint|Update count/last_seen_at, skip new incident|RTO: 0 / RPO: 0|
|Related alerts|Same correlation_key|Append to existing incident and update state|RTO: 0 / RPO: 0|
|AI Engine returns 400 (Bad Request / Tenant mismatch)|HTTP 400 response from /v1/triage|CDO Worker logs error, marks state FAILED_INVALID in DynamoDB, stops retrying to prevent loop, alerts operator|RTO: N/A / RPO: 0|
|AI Engine returns 401 (Auth failed)|HTTP 401 response from /v1/triage|CDO Worker refreshes credentials/token from Secrets Manager, retries once. If failure persists, marks state AUTH_FAILED|RTO: <2 min / RPO: 0|
|AI Engine returns 429 (Rate limited)|HTTP 429 response from /v1/triage|CDO Worker sends message back to SQS FIFO, performs exponential backoff retry|RTO: <10 min / RPO: 0|
|AI Engine returns 500 (Unexpected error)|HTTP 500 response from /v1/triage|CDO Worker uses local rule-based fallback, creates fallback ticket with raw alert context, marks incident DIAGNOSED_FALLBACK|RTO: <5 min / RPO: 0|
|AI Engine returns 503 / Timeout (AI unavailable)|HTTP 503 response or connection timeout|Retries via SQS FIFO. If outage exceeds timeout limit, falls back to rule-based triage to prevent pipeline block|RTO: <10 min / RPO: 0|
|AI Engine S3 write failure|AI error, missing artifact URI|AI retries or returns artifact to Worker for storage|RTO: <5 min / RPO: Incomplete audit evidence|
|Jira created but Integration Lambda crashes before Slack|DynamoDB has jira_ticket_id and current_step|On retry, skip Jira and continue Slack|RTO: <5 min / RPO: 0|
|Slack failure|Integration Lambda error and last_error in DynamoDB|Retry Slack update using existing incident state|RTO: <5 min / RPO: 0|
|DynamoDB throttle/error|CloudWatch DynamoDB metrics|Retry with backoff; tune capacity/on-demand|RTO: <5 min (backoff) / RPO: 0|
|S3 write failure|Worker/Lambda logs, CloudWatch error|Retry audit write; keep minimal state in DynamoDB|RTO: <5 min / RPO: Incomplete audit evidence|
|FIFO DLQ has messages|CloudWatch FIFO DLQ message count|Inspect, fix bug, replay manually|RTO: Manual / RPO: 0 (retention 14 days)|
|CloudWatch logging issue|Missing logs/metric ingestion|Check log group/retention/IAM|RTO: <15 min / RPO: Logs gap|
|AZ/node failure|EKS node events, pod rescheduling|Multi-AZ node group if configured|RTO: <5 min / RPO: 0 (Managed services)|
|Region outage|External monitor/manual detection|Out of MVP scope; future DR plan|RTO: TBD / RPO: TBD (Out of MVP scope)|

---

# 8. Security and access notes

Detailed security design belongs in `03_security_design.md`, but the infrastructure design assumes these controls:

```text
- private EKS worker nodes where possible
- ALB only for public app/API entry
- AI Engine endpoint not exposed publicly unless explicitly required
- IAM least privilege for Lambda, Worker, and Integration Lambda
- IRSA or EKS Pod Identity for pod access to AWS services
- Secrets Manager/SSM for Jira, Slack, and AI Engine credentials
- NetworkPolicy to restrict namespace-to-namespace traffic
- read-only bounded access for AI Engine to observability data
- scoped S3 write access for AI Engine if AI writes context/evidence artifacts
- S3 bucket policy and encryption for audit evidence
- DynamoDB encryption and least-privilege access
- CloudWatch log retention policy
```

Example Ingest Lambda permissions:

```text
sqs:SendMessage
dynamodb:PutItem
dynamodb:UpdateItem
s3:PutObject
logs:CreateLogStream
logs:PutLogEvents
```

Example Correlator Worker permissions:

```text
sqs:ReceiveMessage
sqs:DeleteMessage
sqs:ChangeMessageVisibility
dynamodb:GetItem
dynamodb:PutItem
dynamodb:UpdateItem
s3:PutObject
s3:GetObject
secretsmanager:GetSecretValue
```

Example AI Engine permissions if it writes S3 artifacts:

```text
s3:PutObject on s3://incident-artifacts/{tenant_id}/{service}/{incident_id}/ai/*
s3:GetObject only if AI needs to read approved incident artifacts
```

Example Integration Lambda permissions:

```text
dynamodb:GetItem
dynamodb:UpdateItem
s3:GetObject
s3:PutObject
secretsmanager:GetSecretValue
logs:CreateLogStream
logs:PutLogEvents
```

Important security boundary:

```text
AI Engine should not have broad write access to DynamoDB incident_state.
Workflow state should remain controlled by CDO pipeline components.
```

---

# 9. MVP scope

The MVP should implement:

```text
- EKS runtime for demo app and CDO worker
- ALB ingress to demo app
- Prometheus + Grafana + Alertmanager
- Loki for Kubernetes application logs
- Ingest Lambda
- SQS FIFO Raw Alert Queue + FIFO DLQ
- CDO Incident Correlator Worker
- DynamoDB incident_state table
- S3 incident artifact store
- rule-based alert_fingerprint
- rule-based correlation_key
- AI Engine API contract
- AI artifact contract if AI writes context/evidence to S3
- Jira/Slack integration if owned by CDO
- CloudWatch monitoring for Lambda/SQS FIFO/FIFO DLQ/DynamoDB/S3
```

Do not overclaim:

```text
- no full SaaS tenant lifecycle unless implemented
- no benchmark numbers unless measured
- no topology-aware correlation in MVP unless built
- no strong tenant isolation through labels alone
- no claim that CDO performs RCA
- no claim that SQS FIFO stores metrics/logs
- no claim that DynamoDB stores full reports or raw logs
```

---

# 10. Future improvements

Possible future work:

```text
1. Impact Graph
   Store service dependency metadata to improve correlation and blast-radius analysis.

2. Topology-aware correlation
   Understand upstream/downstream impact, for example Redis → payment-api → checkout-api → frontend.

3. OpenTelemetry tracing
   Add distributed tracing through OpenTelemetry Collector and Tempo or AWS X-Ray.

4. Adaptive time windows
   Replace fixed 5-minute buckets with dynamic incident windows.

5. AI-assisted correlation
   Let AI suggest whether alerts belong to the same incident, while deterministic rules remain the safety layer.

6. Human feedback loop
   Allow SRE/admin to mark alerts as related or unrelated and improve future correlation.

7. Query gateway for observability access
   Enforce tenant/service/env/window restriction before AI queries Prometheus/Loki.

8. Stronger artifact governance
   Add S3 object tagging, retention policy, lifecycle rules, and artifact schema validation.

9. Event replay UI
   Build a controlled replay tool for FIFO DLQ messages and stored incident artifacts.
```

---

# 11. Final takeaway

The architecture separates observability data from incident triggers.

```text
Metrics/logs stay in the observability stack.
Alert events go through the reliable incident pipeline.
DynamoDB tracks workflow state and idempotency.
S3 stores incident artifacts and evidence.
```

CDO does not send every raw alert directly to AI Engine. CDO first reduces noise through Alertmanager, stores alert events safely in SQS FIFO, deduplicates repeated alerts, correlates related alerts into incident-level triggers, stores workflow state in DynamoDB, stores artifacts in S3, and only calls AI Engine when an incident is new or meaningfully updated.

AI Engine owns RCA. It receives incident-level input, queries Prometheus/Loki through bounded access, builds the context, analyzes metrics/logs, and returns root cause, confidence, evidence, and suggested actions. If scoped S3 access is granted, AI Engine may also store the exact context and evidence it used for analysis.

Integration Lambda or the CDO Integration Layer owns external side effects. It creates or updates Jira/Slack, stores request/response audit artifacts in S3, and updates DynamoDB with integration status.

Final statement:

```text
CDO builds the reliable EKS-native incident pipeline.
DynamoDB is the shared state store.
S3 is the shared artifact and evidence store.
AIOps builds the RCA intelligence.
Together, the system turns noisy alerts into bounded, auditable, AI-ready incident workflows.
```

---

# Related documents

- `01_requirements_analysis.md` — explains the problem, NFRs, and why CDO chooses the EKS/K8s-heavy direction.
    
- `03_security_design.md` — expands IAM, RBAC, NetworkPolicy, Secrets Manager, encryption, and audit security.
    
- `04_deployment_design.md` — describes Terraform, GitOps, CI/CD, rollout, rollback, and environment strategy.
    
- `05_cost_analysis.md` — estimates cost for EKS, ALB, SQS FIFO, DynamoDB, S3, CloudWatch, and observability retention.
    
- `07_test_eval_report.md` — records load test, failure test, alert storm test, FIFO DLQ test, and recovery evidence.
    
- `08_adrs.md` — stores decisions such as EKS over ECS, SQS FIFO for alert events, DynamoDB for idempotency, and S3 for audit.