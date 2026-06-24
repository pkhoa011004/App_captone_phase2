# Requirements Analysis - Task Force 1 · CDO-05

## 1. Đề tài context

Task Force 1 xây dựng **Triage Hub** cho một SaaS B2B có khoảng 20k user và khoảng 50 microservice. Hiện tại on-call team có 8 engineer, chịu hơn 50 alert mỗi tuần, dễ bị alert fatigue và MTTR tăng. Mục tiêu của Triage Hub là biến alert thô thành incident có context rõ ràng: hệ thống nhận alert, lấy dữ liệu vận hành liên quan, AIOps/AI phân tích RCA, trả confidence/evidence/suggested actions, sau đó tạo Jira payload và Slack payload để CDO/integration layer gửi cho người trực. Hệ thống chỉ hỗ trợ **human-in-the-loop**, không auto-remediation.

Flow tổng quát:

```text
service metrics/logs
→ CDO observability stack
→ AIOps query data theo tenant/service/env/window
→ AIOps normalize + window + baseline + detect anomaly
→ AIOps RCA/confidence/evidence
→ AI trả jira_payload/slack_payload
→ CDO integration layer gửi Jira/Slack thật
→ lưu audit/state
```

Boundary chính:

```text
CDO owns standardized raw observability data + bounded access + deployment/integration.
AIOps owns interpretation + anomaly detection + RCA + confidence + payload generation.
```

---

## 2. Infra non-functional requirements

|NFR|Target|Justification|
|---|---|---|
|Multi-tenant scale|≥ 50 tenant|Production target của đề bài; dữ liệu observability phải gắn `tenant_id` để tránh leak giữa tenant.|
|SLO p99 latency|< 1000ms cho AI API response path|Theo AI API contract; triage response cần đủ nhanh để hỗ trợ on-call.|
|Availability|≥ 99.5%|Subscription SLA; incident triage pipeline không được chết âm thầm khi có alert quan trọng.|
|Error rate|< 0.5% cho triage API/integration path|Customer trust; lỗi trong pipeline có thể làm mất hoặc chậm xử lý incident.|
|Cost per tenant/month|TBD trong `05_cost_analysis.md`|Chưa có số thật trước khi build. CDO-05 sẽ đo sau khi có EKS/observability stack và traffic demo.|
|Onboarding SLA|< 30 min / tenant|Tenant mới cần có namespace/label/metadata/query scope nhanh để sales/demo không bị chậm.|
|Security baseline|IAM least-privilege + audit 90d|Compliance và tenant isolation; mọi query observability phải bounded theo tenant/service/env/window.|
|Observability retention|Demo: 7–14 ngày; Audit: 90 ngày metadata|Giữ đủ dữ liệu cho RCA/evidence nhưng tránh cost cao do raw log/metric retention dài.|
|Data contract completeness|100% log/metric có `tenant_id`, `service`, `env`, `timestamp`, `signal_type`|Nếu thiếu metadata, AIOps không thể query/analyze đúng phạm vi.|
|No auto-remediation|100% human-reviewed|TF1 chỉ triage/RCA/suggested actions, không tự sửa hệ thống.|

---

## 3. Differentiation angle

### Angle chọn

**K8s-heavy / EKS-native**

CDO-05 chọn hướng **K8s-heavy / EKS-native** vì TF1 Triage Hub không chỉ là bài toán host container. Đây là bài toán xây một nền tảng **AIOps incident triage** cần gom metric, log, alert, deployment metadata, runtime state và tenant/service/env metadata về một mô hình nhất quán để AI có thể phân tích RCA.

CDO-05 không chọn EKS vì ECS không làm được. ECS hoàn toàn có thể chạy container với chi phí thấp hơn và vận hành đơn giản hơn trong nhiều trường hợp. Tuy nhiên, với bài toán TF1, điểm quan trọng không chỉ là chạy service rẻ, mà là xây được một ecosystem quan sát và phân tích incident đủ rõ cho AIOps.

EKS phù hợp hơn vì Kubernetes cung cấp một ecosystem thống nhất cho các thành phần này:

```text
workload runtime
observability
alerting
GitOps
service discovery
ingress
RBAC
NetworkPolicy
namespace
label/annotation metadata
```

Với EKS, CDO có thể chuẩn hóa dữ liệu vận hành quanh cùng một metadata model như:

```text
tenant_id
service
env
namespace
pod
deployment
version
timestamp
```

Metadata này có thể được dùng xuyên suốt từ app workload, metric/log, alert rule, deployment state đến bounded query access cho AIOps.

---

### Why this angle

CDO-05 chọn **K8s-heavy / EKS-native** dựa trên 2 trục chính:

```text
Ecosystem + Observability
```

#### 1. Ecosystem thống nhất hơn cho AIOps RCA

TF1 Triage Hub cần nhiều loại context để phân tích incident:

```text
metric trend
log pattern
alert signal
runtime state
deployment metadata
tenant/service/env metadata
```

Trên EKS, các thành phần này nằm tự nhiên trong cùng Kubernetes ecosystem:

```text
- Prometheus Operator / ServiceMonitor / PrometheusRule để thu metric và tạo alert.
- Alertmanager để phát alert/anomaly signal.
- Argo CD / GitOps để quản lý deployment và recent change metadata.
- AWS Load Balancer Controller để expose workload bằng Ingress/ALB theo cloud-native style.
- Namespace / label / annotation để gắn tenant, service, env metadata.
- RBAC / NetworkPolicy để kiểm soát quyền và isolation.
- Deployment / ReplicaSet / Pod / Event để cung cấp runtime context cho RCA.
```

Điểm thuyết phục nhất là **metadata consistency**. Cùng một bộ metadata như `tenant_id`, `service`, `env`, `namespace`, `deployment`, `version` có thể được dùng xuyên suốt nhiều lớp: workload, metric, log, alert, deployment và runtime context.

ECS vẫn có thể làm được các phần tương tự, nhưng thường phải ghép nhiều mặt phẳng riêng như:

```text
ECS service/task metadata
CloudWatch metrics/logs
EventBridge events
ALB target group
CI/CD metadata
tagging convention
custom mapping layer
```

Điều đó làm tăng phần custom glue khi cần tạo RCA context nhất quán cho AIOps.

#### 2. Observability gần workload hơn

Vì app chạy trên Kubernetes, metric/log/runtime state có thể gắn trực tiếp với workload metadata.

AIOps có thể query dữ liệu theo phạm vi rõ ràng:

```text
tenant_id + service + env + time_window
```

Đây là requirement quan trọng của TF1, vì AI/AIOps không được query toàn hệ thống không kiểm soát. CDO cần expose dữ liệu observability theo bounded access, còn AIOps dùng dữ liệu đó để normalize, window, baseline, detect anomaly và RCA.

EKS giúp việc chuẩn hóa observability theo workload tự nhiên hơn nhờ namespace, label, annotation, service discovery, deployment state và monitoring CRD.

---

### Why EKS over ECS

CDO-05 không phủ nhận ECS rẻ hơn và đơn giản hơn cho container hosting. Nếu mục tiêu chỉ là chạy container với chi phí thấp, ECS là lựa chọn tốt.

Tuy nhiên, TF1 không chỉ cần container hosting. TF1 cần một nền tảng phục vụ **AI incident triage**, nơi metric, log, alert, runtime state và deployment context phải liên kết được với nhau bằng metadata nhất quán.

Vì vậy, CDO-05 chọn EKS vì:

```text
- Kubernetes có ecosystem observability mạnh hơn cho bài toán microservice RCA.
- Metadata model bằng namespace/label/annotation rõ ràng và nhất quán hơn.
- PrometheusRule, ServiceMonitor, Alertmanager phù hợp với alerting flow.
- Argo CD/GitOps cung cấp recent deployment/change context tự nhiên hơn.
- K8s object model cung cấp runtime evidence như Pod, Deployment, ReplicaSet, Event.
- Bounded query access theo tenant/service/env/window dễ thiết kế hơn quanh Kubernetes metadata.
```

Câu chốt:

```text
ECS wins on cost and operational simplicity.
EKS wins on ecosystem, metadata consistency, observability, GitOps context, and production-like RCA evidence.
```

Vì win axis của CDO-05 là **AIOps-ready observability platform**, không phải cheapest container hosting, EKS là lựa chọn phù hợp hơn.

---

### Axis chính

```text
Ecosystem + Observability + Production Realism
```

- **Ecosystem:** tận dụng Prometheus stack, Alertmanager, Argo CD, AWS Load Balancer Controller, RBAC, NetworkPolicy, namespace/label/annotation.
    
- **Observability:** metric/log dễ gắn với tenant, service, env, namespace, pod, endpoint và timestamp.
    
- **Production realism:** mô hình sát production microservice hơn, phù hợp để demo incident triage end-to-end.
    

---

### Trade-off chấp nhận

CDO-05 chấp nhận **chi phí và độ phức tạp vận hành cao hơn ECS/serverless-first**.

Cụ thể:

```text
- Cần setup và quản lý EKS.
- Cần node group hoặc compute profile.
- Cần ingress/LB integration.
- Cần RBAC, namespace, NetworkPolicy.
- Cần monitoring stack như Prometheus/Grafana/Loki/Alertmanager.
- Baseline cost cao hơn ECS hoặc Lambda/serverless-only.
```

Nhưng trade-off này hợp lý vì TF1 cần chứng minh năng lực CDO trong việc xây nền tảng:

```text
runtime platform
observability stack
tenant-aware telemetry
bounded data access
incident workflow
AI integration
```

---

### Không chọn ECS/serverless-first làm angle chính vì

ECS/serverless-first phù hợp nếu mục tiêu chính là tối ưu cost, giảm ops complexity và chạy container/workflow nhanh. Tuy nhiên, với TF1, trọng tâm là xây một nền tảng AIOps incident triage cần nhiều runtime context và metadata nhất quán.

ECS vẫn có thể làm được, nhưng CDO phải tự chuẩn hóa nhiều mapping giữa service, task, log group, alarm, target group, deployment event, tenant metadata và incident context. Điều này làm tăng custom glue cho RCA pipeline.

Serverless cũng phù hợp cho các phần phụ trợ như alert ingestion, workflow orchestration, retry, notification và audit/state. Tuy nhiên, serverless-only không thể hiện rõ hệ sinh thái runtime của microservice như pod status, deployment rollout, service metadata, namespace isolation, PrometheusRule, Kubernetes-native alerting và runtime labels/annotations.

Vì vậy, CDO-05 chọn **K8s-heavy / EKS-native** làm angle chính. ECS/serverless vẫn có thể được dùng như lớp phụ trợ cho workflow incident nếu cần, nhưng không phải differentiation angle chính.

---

### Locked T3 W11

**Locked T3 W11:** 24/06/2026 — fastest-commit wins enforcement.

---

## 4. Comparison với nhóm cùng task force

| Aspect          | CDO-05 angle                                                                                                                                                                                                                                                                                                                                                                            | Nhóm CDO khác                                                                                                                               |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Compute pattern | **K8s-heavy / EKS-native**. App, observability stack, alert rule và runtime metadata chạy quanh Kubernetes ecosystem. Serverless chỉ dùng phụ trợ nếu cần cho workflow notification/audit.                                                                                                                                                                                              | **Serverless-first / managed-first**. Ưu tiên Lambda, managed workflow, managed observability, giảm vận hành cluster.                       |
| Storage         | Metrics lưu trong Prometheus/Prometheus-compatible backend; logs lưu trong CloudWatch Logs hoặc Loki. DynamoDB chỉ dùng cho incident state/idempotency như `RECEIVED`, `AI_ANALYZED`, `JIRA_CREATED`, `SLACK_SENT`, `FAILED`. Audit evidence như alert payload, context/evidence package và AI response để TBD, ưu tiên S3 nếu cần lưu dài hạn. Không dump raw metric/log vào DB riêng. | Ưu tiên managed storage như CloudWatch Logs, DynamoDB/S3 cho audit/state, ít vận hành storage trong cluster.                                |
| Cost profile    | Baseline cost cao hơn vì có EKS/node/monitoring stack chạy liên tục. Bù lại phù hợp demo microservice platform và observability thực tế.                                                                                                                                                                                                                                                | Cost có thể thấp hơn nếu workload ít và event-driven. Pay-per-use tốt hơn, nhưng có thể khó thể hiện full runtime context của K8s workload. |
| Ops complexity  | Cao hơn: cần quản lý EKS, node group, ingress, RBAC, NetworkPolicy, monitoring stack, GitOps.                                                                                                                                                                                                                                                                                           | Thấp hơn: ít thành phần runtime tự quản hơn, chủ yếu cấu hình managed services.                                                             |
| Latency profile | App/collector/monitoring nằm gần workload nên lấy K8s context, pod status, service metadata và alert rule tự nhiên hơn.                                                                                                                                                                                                                                                                 | Event-driven có thể có cold start/async delay nhỏ, nhưng phù hợp cho ingestion/notification/audit.                                          |
| **Win axis**    | **Ecosystem + observability + production realism**. Tận dụng Kubernetes ecosystem để build AI incident triage gần production.                                                                                                                                                                                                                                                           | **Cost + ops simplicity + managed reliability**. Tối ưu tốc độ build, giảm vận hành, tận dụng managed services.                             |

### Summary

CDO-05 chọn K8s-heavy vì TF1 cần dữ liệu vận hành sát workload thật:

```text
metric
log
pod state
deployment metadata
service label
tenant/env metadata
alert rule
```

Điểm mạnh chính là tận dụng hệ sinh thái Kubernetes/EKS để tạo observability và bounded data access cho AIOps.

---

## 5. Constraints

- **AWS only:** không multi-cloud trong phase này.
    
- **Region:** `ap-southeast-1` mặc định. Có thể đổi nếu task force thống nhất region khác, nhưng nên giữ cùng region giữa CDO và AI để giảm network/cost/latency.
    
- **Budget:** dự kiến `$100–150 / 2 tuần build` cho môi trường demo. Số chính thức sẽ cập nhật trong `05_cost_analysis.md`.
    
- **Code freeze:** T4 W12 18h.
    
- **Scope:** không build production-grade platform đầy đủ; chỉ build đủ để chứng minh flow TF1 end-to-end.
    
- **AI boundary:** LLM/Bedrock không được query trực tiếp Prometheus/CloudWatch/Loki/Kubernetes API.
    
- **AIOps query boundary:** AIOps backend chỉ được query dữ liệu bounded theo `tenant_id`, `service`, `env`, `time_window`.
    
- **Data constraint:** metric/log phải có metadata tối thiểu: `schema_version`, `tenant_id`, `service`, `env`, `timestamp`, `signal_type`.
    
- **Storage boundary:** metrics nằm trong Prometheus/Prometheus-compatible backend; logs nằm trong CloudWatch Logs hoặc Loki. DynamoDB chỉ lưu incident state/idempotency. Audit evidence để TBD, ưu tiên S3 nếu cần lưu context/evidence package và AI response.
    
- **No raw observability DB:** không tạo database riêng để dump toàn bộ raw metric/log, vì sẽ tăng cost và duplicate dữ liệu đã có trong observability backend.
    
- **Security:** không hardcode secret Jira/Slack/AI key. Secret phải đi qua cơ chế an toàn như Secrets Manager, SSM Parameter Store, Kubernetes Secret hoặc External Secrets.
    
- **Reliability:** incident event không được mất âm thầm; cần retry, audit, incident state, idempotency key và failure handling.
    
- **No auto-remediation:** AI chỉ trả RCA, confidence, evidence, suggested actions, Jira payload và Slack payload. Human/operator vẫn là bên review và quyết định hành động.
    

End-to-end scope cần chứng minh:

```text
app traffic
→ metrics/logs
→ alert/anomaly
→ AIOps query bounded data
→ RCA/confidence
→ Jira/Slack payload
→ CDO gửi notification thật
→ audit/state
```

### Storage boundary detail

CDO-05 không lưu toàn bộ raw metric/log vào một database riêng. Metric/log phải nằm trong đúng observability backend của nó, còn database chỉ dùng cho state/audit của incident.

```text
Metrics
→ Prometheus / Prometheus-compatible backend

Logs
→ CloudWatch Logs hoặc Loki

Incident state
→ DynamoDB

Audit evidence
→ TBD, ưu tiên S3 nếu cần lưu context/evidence package và AI response
```

|Thành phần|Vai trò|
|---|---|
|Prometheus / Prometheus-compatible backend|Lưu và query metrics như request rate, latency, error rate, pod restart, resource usage.|
|CloudWatch Logs / Loki|Lưu logs của app, container, pipeline hoặc error pattern.|
|DynamoDB|Lưu trạng thái xử lý incident như `RECEIVED`, `AI_ANALYZED`, `JIRA_CREATED`, `SLACK_SENT`, `FAILED`. Đồng thời dùng cho idempotency để tránh tạo ticket/message trùng.|
|S3|Có thể dùng để lưu audit evidence dài hơn như alert payload, context/evidence package đã dùng cho RCA, AI response, Jira/Slack payload. Phần này để TBD nếu chưa chốt.|

---

## 6. Open questions

-  **Q1: AI/AIOps cần raw data mức nào?**  
    Các option: raw log/metric đã chuẩn hóa cơ bản, window summary, hoặc hybrid.  
    CDO-05 đề xuất: **raw bounded data có schema chuẩn**. CDO đảm bảo dữ liệu có đủ `tenant_id`, `service`, `env`, `timestamp`, `signal_type`; AIOps tự normalize sâu hơn, window, baseline, trend, evidence và RCA.  
    _To resolve with Nhóm AI by T4 W11._
    
-  **Q2: AI/AIOps sẽ query trực tiếp observability backend hay thông qua bounded query/export API?**  
    Option A: AIOps query trực tiếp Prometheus/Loki/CloudWatch với quyền giới hạn.  
    Option B: CDO expose một bounded query/export API để AIOps gọi.  
    Rule bắt buộc: không query unbounded toàn hệ thống, không cho LLM/Bedrock query trực tiếp.  
    _To resolve with Nhóm AI by T4 W11._
    
-  **Q3: Metadata bắt buộc cuối cùng gồm những field nào?**  
    Đề xuất tối thiểu: `schema_version`, `tenant_id`, `env`, `service`, `timestamp`, `signal_type`.  
    Đề xuất mở rộng cho log: `level`, `endpoint`, `method`, `status_code`, `latency_ms`, `message`, `error_type`, `trace_id`, `request_id`, `pod_name`, `namespace`.  
    Đề xuất mở rộng cho metric: `metric_name`, `value`, `unit`, `window`, `labels`.  
    Đề xuất mở rộng cho deploy metadata: `version`, `image`, `commit_sha`, `deployed_at`, `deployed_by`, `status`.  
    _To resolve with Nhóm AI by T4 W11._
    
-  **Q4: Window mặc định cho query là bao nhiêu?**  
    Đề xuất: current window `last_5m` hoặc `last_10m`, baseline window `last_1h`, recent deploy window `last_15m` hoặc `last_30m`.  
    Cần AI confirm vì window ảnh hưởng trực tiếp tới RCA và cost query.  
    _To resolve with Nhóm AI by T4 W11._
    
-  **Q5: Jira/Slack ai gửi thật?**  
    CDO-05 đề xuất: AI trả `jira_payload` và `slack_payload`; CDO/integration layer gửi Jira/Slack thật.  
    Lý do: AI không cần giữ secret Jira/Slack, dễ retry, dễ audit, dễ tránh gửi trùng và boundary rõ hơn.  
    _To resolve with Nhóm AI by T4 W11._
    
-  **Q6: Ba incident scenario demo chính là gì?**  
    Đề xuất 3 scenario: latency spike, 5xx spike, Redis/dependency timeout.  
    Mỗi scenario cần có sample metric, sample log, alert condition, expected RCA, expected confidence behavior và expected Jira/Slack payload.  
    _To resolve with Nhóm AI by T4 W11._
    
-  **Q7: Audit evidence lưu ở đâu?**  
    Metrics sẽ nằm trong Prometheus/Prometheus-compatible backend, logs nằm trong CloudWatch Logs hoặc Loki, DynamoDB chỉ lưu incident state/idempotency. Phần audit evidence như alert payload, context/evidence package, AI response, Jira/Slack payload cần chốt lưu ở S3 hay audit store khác. CDO-05 đề xuất ưu tiên S3 nếu cần lưu payload dài hạn.  
    _To resolve with Nhóm CDO by T4 W11._
    

---

## Final Position

CDO-05 chọn **K8s-heavy / EKS-native** vì hệ sinh thái Kubernetes/EKS giúp build nền tảng incident triage sát production hơn.

Câu chốt:

```text
CDO-05 provides standardized raw observability data and bounded query access.
AIOps owns data interpretation, anomaly detection, RCA, confidence, and Jira/Slack payload generation.
CDO/integration layer sends Jira/Slack for real and owns audit/state/retry.
```