# Security Design - TF1 Triage Hub · CDO-05

**Owner:** CDO-05  
**Team phối hợp:** AIO-01  
**Scope:** IAM, secrets, network, audit, tenant isolation, compliance touch, threat model và incident response cho kiến trúc TF1 Triage Hub.  
**Nguồn căn cứ:** `01_requirements_analysis.md`, `02_infra_design.md`, AIOps contracts/handoff trong `temp/aiops/xBrain-capstone2`, và `CAPSTONE_EVIDENCE_PACK_FORMAT.md`.

## 0. Security Context

TF1 Triage Hub là nền tảng nhận alert từ hệ thống observability, gom nhóm alert thành incident, gọi AI Engine để RCA, sau đó tạo/update Slack và Jira. Với vai trò CDO-05, mục tiêu security không chỉ là "chặn hacker", mà còn phải bảo vệ các điểm dễ sai trong incident workflow:

- Không để tenant A đọc metrics/logs/evidence của tenant B.
- Không để alert critical bị mất hoặc retry tạo trùng Jira/Slack.
- Không để AI Engine hoặc LLM có credential trực tiếp vào Prometheus/Loki/CloudWatch.
- Không để raw logs/metrics unbounded đi vào AI context.
- Không để pod trong EKS có quyền AWS quá rộng.
- Không để Jira/Slack/Bedrock/API token xuất hiện trong Git, log, S3 evidence hoặc dashboard.
- Không để public endpoint bị spam làm tăng cost hoặc tạo incident giả.

Security posture của CDO-05:

```text
private-by-default network
+ least-privilege IAM/IRSA
+ namespace/RBAC/NetworkPolicy isolation
+ bounded evidence access for AI
+ SQS FIFO + DLQ alert reliability
+ DynamoDB idempotency state
+ S3 immutable audit evidence
+ human-in-the-loop, no auto-remediation
```

Quan trọng: trong tài liệu này, "worker" được tách rõ thành 3 vai trò khác nhau:

| Tên | Runtime | Vai trò |
|---|---|---|
| Ingest Lambda | AWS Lambda | Nhận Alertmanager webhook, validate/normalize, gửi alert event vào SQS FIFO. |
| CDO Correlator Worker | EKS pod trong namespace `aiops` | Consume SQS FIFO, deduplicate/correlate, update DynamoDB/S3, gọi AI Engine khi cần. |
| Integration Lambda / CDO Integration Layer | Lambda hoặc pod | Tạo/update Jira và Slack, lưu audit integration. |

AI Engine là service riêng trong namespace `ai-engine`, thuộc logic AIOps. AI Engine không sở hữu SQS retry, DynamoDB workflow state, Jira/Slack side-effect hoặc quyền remediation.

---

## 1. IAM model

### 1.1 Nguyên tắc chung

Mô hình IAM dùng **least privilege theo workload**, không dùng một role chung cho tất cả pod/Lambda. Mỗi component chỉ được quyền đọc/ghi đúng service cần thiết trong flow:

```text
Alertmanager
-> Ingest Lambda
-> SQS FIFO Raw Alert Queue
-> CDO Correlator Worker on EKS
-> AI Engine / RCA
-> Integration Lambda / CDO Integration Layer
-> Slack / Jira
```

IAM rule:

- Không dùng long-lived AWS access keys trong pod/container.
- Lambda dùng execution role riêng.
- EKS pod dùng IRSA hoặc EKS Pod Identity theo từng Kubernetes ServiceAccount.
- Không cấp `AdministratorAccess`, `s3:*`, `dynamodb:*`, `sqs:*`, `secretsmanager:*`.
- Với audit/evidence bucket, ưu tiên SSE-KMS để khớp với production design trong `02_infra_design.md`; runtime role chỉ được `kms:Decrypt`/`kms:GenerateDataKey` trên đúng key liên quan.
- Tách quyền "read evidence" khỏi quyền "write workflow state".

### 1.2 Role matrix

| Principal / Role | Runtime | Allowed actions | Không được phép |
|---|---|---|---|
| `tf1-ingest-lambda-role` | Ingest Lambda | `sqs:SendMessage` vào SQS FIFO; optional `dynamodb:PutItem/UpdateItem` để ghi ingest state; optional `s3:PutObject` raw alert snapshot; `secretsmanager:GetSecretValue` cho webhook signing key; CloudWatch Logs. | Không gọi AI Engine, Bedrock, Jira, Slack; không đọc Prometheus/Loki; không consume SQS. |
| `tf1-correlator-worker-role` | EKS pod qua IRSA | `sqs:ReceiveMessage/DeleteMessage/ChangeMessageVisibility/GetQueueAttributes`; `dynamodb:GetItem/PutItem/UpdateItem/Query`; `s3:GetObject/PutObject/ListBucket` theo prefix incident; `secretsmanager:GetSecretValue` cho service auth token; optional KMS; CloudWatch/OTel log export. | Không `cluster-admin`; không `dynamodb:DeleteTable`; không broad observability admin; không tự remediation; không gọi Jira/Slack nếu Integration Layer tách riêng. |
| `tf1-ai-engine-role` | EKS pod qua IRSA hoặc ECS task role | Optional `s3:GetObject` evidence bundle đã duyệt; optional `s3:PutObject` vào prefix `ai/`; optional `bedrock:InvokeModel` nếu bật Bedrock; `secretsmanager:GetSecretValue` cho service/evidence auth; CloudWatch Logs. | Không write rộng vào DynamoDB `incident_state`; không consume/delete SQS; không giữ Jira/Slack token nếu CDO owns integration; không quyền scale/restart/rollback workload. |
| `tf1-integration-role` | Lambda hoặc EKS pod | `dynamodb:GetItem/UpdateItem`; `s3:GetObject/PutObject`; `secretsmanager:GetSecretValue` cho Jira/Slack token; call public Jira/Slack endpoints; CloudWatch Logs. | Không query Prometheus/Loki; không chạy RCA; không tạo issue mới nếu idempotency state đã có ticket. |
| `tf1-observability-query-role` | Evidence proxy nếu có | Read-only query Prometheus/Loki/CloudWatch/trace backend theo tenant/service/env/window; write audit query log. | Không expose raw backend credentials cho AI; không cho arbitrary PromQL/LogQL từ LLM. |
| CI/CD deploy role | GitHub Actions/Terraform/ArgoCD | Deploy IaC/manifests theo environment; read image digest; update cluster resources theo namespace. | Không dùng chung với runtime role; không giữ production secret plaintext trong pipeline. |
| Break-glass admin | Human/admin | Emergency only, MFA, time-boxed. | Không dùng cho daily deploy/debug. |

### 1.3 IRSA/RBAC cho CDO Correlator Worker

CDO Correlator Worker là component quan trọng nhất về quyền AWS. Đây là worker pod trên EKS, không phải Ingest Lambda. Worker được bind với Kubernetes ServiceAccount riêng:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: cdo-correlator-worker
  namespace: aiops
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::<account-id>:role/tf1-correlator-worker-role
```

Quyền AWS tối thiểu:

| AWS resource | Actions | Scope |
|---|---|---|
| SQS FIFO Raw Alert Queue | `ReceiveMessage`, `DeleteMessage`, `ChangeMessageVisibility`, `GetQueueAttributes`, `GetQueueUrl` | Chỉ raw alert queue của TF1. |
| SQS FIFO DLQ | `GetQueueAttributes`, optional `ReceiveMessage` cho manual replay tool | Không auto redrive nếu chưa có approval/runbook. |
| DynamoDB `incident_state` | `GetItem`, `PutItem`, `UpdateItem`, `Query`, optional `DescribeTable` | Chỉ table/index của TF1; dùng conditional write cho idempotency. |
| S3 Incident Artifact Store | `GetObject`, `PutObject`, `ListBucket` với prefix condition | Prefix `{tenant_id}/{service}/{incident_id}/...`; không list toàn bucket nếu có thể tránh. |
| Secrets Manager | `GetSecretValue` | Chỉ service token gọi AI Engine hoặc evidence proxy. Jira/Slack token chỉ cấp nếu Worker thực sự kiêm Integration Layer. |
| KMS | `Decrypt`, `GenerateDataKey` | Chỉ KMS key dùng cho queue/bucket/secret liên quan. |
| CloudWatch Logs / OTel | log write/export | Không log secret/raw token. |

Kubernetes RBAC tối thiểu cho worker:

```text
namespace: aiops
verbs: get/list/watch pods only if needed for self-observability
no permission: secrets get/list, pods/exec, pods/portforward, clusterroles, nodes
```

Nếu worker cần đọc service metadata trong Kubernetes, chỉ cấp read-only trên namespace liên quan. Không cấp `cluster-admin` hoặc quyền đọc tất cả Kubernetes Secrets.

### 1.4 Quyền của AI Engine đối với telemetry

AI Engine cần context để RCA, nhưng quyền telemetry phải bị giới hạn nghiêm ngặt. Theo AIOps handoff, AI Engine không được nhận credential trực tiếp để tự query toàn bộ observability backend. CDO nên expose một trong hai mô hình:

| Pattern | Khi dùng | Security boundary |
|---|---|---|
| Precomputed evidence bundle | MVP/W11/W12 demo ổn định | CDO lưu bounded JSON bundle trong S3 theo `tenant_id/incident_id`; AI chỉ đọc đúng object/prefix được chỉ định. |
| Read-only evidence proxy | Prod-like / cần live query | AI gọi proxy nội bộ; proxy validate tenant/service/env/window, limit, timeout, redact, audit. |

AI Engine chỉ được đọc telemetry qua scope:

```text
tenant_id + service + environment + time_window
```

Giới hạn khuyến nghị:

- Default window: 15 phút trước alert + 5 phút sau alert.
- Extended window tối đa: 60 phút nếu được approve.
- Log snippets: tối đa 50 dòng/service/incident.
- Trace: trả summary/span highlights, không full trace dump.
- Query operations allowlist: `get_metric_window`, `get_log_snippets`, `get_trace_summary`, `get_deploy_events`, `get_ownership`, `get_jira_history`.
- Reject query thiếu `tenant_id`, `service`, `environment`, `start_time/end_time`.
- Không cho LLM tự sinh arbitrary PromQL/LogQL.
- Audit mọi evidence query với `tenant_id`, `incident_id`, `query_scope`, `result_count`, `caller`, `correlation_id`.

AI Engine có thể write S3 artifact nếu cần audit chính xác context đã dùng:

```text
s3://tf1-audit/{tenant_id}/{service}/{incident_id}/ai/context.json
s3://tf1-audit/{tenant_id}/{service}/{incident_id}/ai/ai-response.json
```

AI Engine không nên có quyền write rộng vào DynamoDB `incident_state`. Workflow state, idempotency, Jira/Slack status vẫn do CDO pipeline kiểm soát.

### 1.5 Service-to-service auth

| Flow | Auth control |
|---|---|
| Alertmanager -> Ingest Lambda | HMAC/shared secret header, timestamp/nonce chống replay, schema validation. |
| CDO Worker -> AI Engine `/v1/triage` | Private service DNS + IAM SigV4 hoặc service-to-service JWT. Capstone fallback: scoped bearer token trong Secrets Manager. |
| AI Engine -> Evidence Proxy | IAM SigV4/JWT/service token, bắt buộc `X-Tenant-Id` và `X-Correlation-Id`. |
| Slack callbacks nếu bật | Verify `X-Slack-Signature` và `X-Slack-Request-Timestamp`. |
| CI/CD -> AWS | OIDC assume role; không lưu AWS key dài hạn trong GitHub secrets nếu có thể. |

API contract yêu cầu `X-Tenant-Id` header phải match body `tenant_id`, và `X-Correlation-Id` header phải match body `correlation_id`. Tenant mismatch trả `400` và không retry vô hạn.

### 1.6 Cross-account assume-role pattern

MVP có thể cùng một AWS account. Nếu production tách account theo `platform`, `prod`, `audit` hoặc theo tenant lớn:

- CI/CD dùng OIDC assume deploy role theo environment.
- Runtime cross-account chỉ dùng khi thật cần, ví dụ CDO platform account đọc evidence bucket ở audit account.
- Assume role phải có external ID hoặc session tags như `tenant_id`, `environment`, `component`.
- Permission boundary giới hạn role tenant không thể truy cập prefix/table/key ngoài tenant.
- Không dùng cross-account role để bypass tenant isolation ở app/query layer.

### 1.7 Per-tenant IAM role + permission boundary

Thiết kế hiện tại là pooled multi-tenant platform: nhiều tenant dùng chung EKS/SQS/DynamoDB/S3, cô lập bằng metadata, keys/prefix, IAM condition, bounded query và audit. Với production tenant tier cao hoặc compliance mạnh hơn, có thể nâng cấp:

| Tier | Isolation | IAM pattern |
|---|---|---|
| Standard | Shared platform, tenant prefix/key | Shared workload role + app-level tenant enforcement + S3/DynamoDB condition. |
| Enterprise | Dedicated namespace/evidence prefix/KMS key | Per-tenant IAM role với permission boundary. |
| Regulated | Dedicated account/VPC/cluster nếu cần | Cross-account assume role, SCP, dedicated audit bucket. |

Trong mọi tier, `tenant_id` trong payload không được tin mù quáng. Nó phải được kiểm tra với auth principal, namespace/service mapping, S3 prefix, DynamoDB key và evidence query scope.

---

## 2. Secrets management

### 2.1 Secret inventory

| Secret | Store | Consumer | Rotation |
|---|---|---|---|
| Alertmanager webhook signing secret | Secrets Manager / SSM SecureString | Ingest Lambda | Rotate mỗi 60-90 ngày hoặc khi lộ. |
| AI Engine service auth token | Secrets Manager | CDO Worker và AI Engine validator | Demo fallback; prod ưu tiên JWT/SigV4. |
| Evidence API auth secret | Secrets Manager | AI Engine / context tools | Rotate 60-90 ngày. |
| Jira API token | Secrets Manager | Integration Lambda/Layer | Rotate theo policy Jira; không cấp cho AI Engine nếu CDO owns integration. |
| Slack bot/webhook/signing secret | Secrets Manager | Integration Layer / Slack endpoints | Rotate khi member/offboarding hoặc lộ. |
| Bedrock/model config | SSM Parameter Store hoặc env config | AI Engine | Không phải secret nếu chỉ là model ID; budget/cap đặt trong config. |
| KMS keys | AWS KMS | S3/SQS/DynamoDB/Secrets | Key rotation enabled nếu dùng CMK. |

### 2.2 Rules

- Không commit secret trong Git, Terraform state plaintext, Helm values, Docker image, screenshots hoặc sample JSON.
- Với Kubernetes, dùng External Secrets Operator hoặc CSI driver để sync từ AWS Secrets Manager; tránh tạo Kubernetes Secret thủ công chứa token thật.
- Secret chỉ mount vào workload cần dùng. Ví dụ AI Engine không cần Jira token nếu Integration Lambda mới là bên tạo Jira.
- Log redaction bắt buộc cho headers `Authorization`, webhook URL, API token, cookie, Slack/Jira token.
- Terraform state phải đặt remote backend có encryption + access control; không output secret value.
- Khi secret rotate, phải có runbook update pod/Lambda và smoke test `/healthz`, `/v1/triage`, Jira/Slack integration.

### 2.3 Cost-aware choice

Secrets Manager có cost theo secret/tháng, nhưng đáng dùng cho secret thật như Jira/Slack/service token. Với non-secret config như log level, max window, model ID, có thể dùng SSM Parameter Store hoặc environment variables để giảm cost.

---

## 3. Network policy

### 3.1 VPC topology

Production baseline:

```text
Public subnets:
  - Public ALB only if demo/public API is needed
  - NAT Gateway only if required for external Jira/Slack egress

Private subnets:
  - EKS node groups
  - AI Engine internal service
  - CDO Correlator Worker
  - Observability stack
  - Lambda ENI if Lambda runs inside VPC

AWS managed services:
  - SQS FIFO + DLQ
  - DynamoDB
  - S3 audit/evidence bucket
  - Secrets Manager
  - CloudWatch
  - Bedrock optional
```

VPC endpoints nên dùng cho S3, DynamoDB, SQS, ECR, CloudWatch Logs, STS, Secrets Manager và Bedrock nếu bật. Điều này giảm public egress, giảm phụ thuộc NAT và hỗ trợ cost/security tốt hơn.

### 3.2 Network segmentation

| Segment | Inbound allowed | Outbound allowed |
|---|---|---|
| Public ALB | Internet/VPN vào 443 | Demo app service trong namespace `app`. Không route AI Engine. |
| Namespace `app` | ALB/Ingress | Emit metrics/logs/traces đến observability; không gọi DynamoDB/SQS/S3 trực tiếp nếu không cần. |
| Namespace `observability` | Metrics/log agents, Grafana internal users | Prometheus/Loki/OTel storage; không public unauthenticated. |
| Namespace `aiops` | Không public | SQS/DynamoDB/S3/Secrets qua AWS endpoints; AI Engine internal service; optional Integration Layer. |
| Namespace `ai-engine` | Chỉ CDO Worker/Integration Layer nội bộ | Evidence proxy/S3 evidence/Bedrock optional/CloudWatch Logs. |
| Integration Layer | Internal trigger hoặc queue | Jira/Slack endpoints; DynamoDB/S3/Secrets. |

### 3.3 Security group baseline

Security Group không phải lớp bảo vệ duy nhất, nhưng là lớp chặn network cấp VPC quan trọng nhất. Rule nên viết theo nguyên tắc allowlist, không mở rộng `0.0.0.0/0` trừ public ALB port 443.

| Security group | Inbound | Outbound | Notes |
|---|---|---|---|
| `tf1-public-alb-sg` | `443` từ internet hoặc allowlisted CIDR; optional `80` chỉ redirect sang HTTPS | Chỉ tới EKS node/pod target SG trên app port | Không route tới AI Engine, Prometheus, Loki, Grafana admin hoặc internal service. |
| `tf1-eks-node-sg` | Từ ALB SG tới NodePort/target port nếu dùng ALB target; từ control plane SG theo EKS requirement; node-to-node nội bộ | VPC endpoints, internal services, required image pull/observability endpoints | Không dùng node SG làm "mở tất cả". Pod-level isolation vẫn cần NetworkPolicy. |
| `tf1-app-pod-sg` nếu dùng Security Groups for Pods | Từ ALB SG hoặc internal namespace cần thiết | Observability ingest/scrape path; không cần SQS/DynamoDB/S3 trực tiếp nếu app chỉ emit telemetry | Dùng khi muốn cô lập app public khỏi worker/AI namespace ở mức ENI/pod. |
| `tf1-ai-engine-sg` | Chỉ từ `tf1-aiops-worker-sg` hoặc internal service mesh/ingress SG tới port AI API | Evidence proxy/S3 endpoint/Bedrock endpoint/CloudWatch Logs endpoint | Không có inbound từ internet. Không cho app namespace gọi trực tiếp nếu không phải approved caller. |
| `tf1-aiops-worker-sg` | Không cần public inbound; optional health/metrics từ observability namespace | SQS endpoint, DynamoDB endpoint, S3 endpoint, Secrets Manager endpoint, AI Engine internal service | Worker là consumer, nên inbound rất hẹp. Quyền AWS vẫn do IRSA quyết định, SG chỉ kiểm soát đường mạng. |
| `tf1-integration-sg` | Internal trigger hoặc queue consumer only | Jira/Slack qua NAT/egress proxy; DynamoDB/S3/Secrets endpoints | Nếu Jira/Slack public internet, outbound phải đi qua NAT/egress proxy và có retry/rate limit. |
| `tf1-observability-sg` | Scrape/ingest từ app/workload SG; Grafana UI chỉ từ VPN/admin CIDR nếu expose | Internal storage/backend; CloudWatch/S3 nếu export | Prometheus/Loki/Grafana không public unauthenticated. |
| `tf1-vpc-endpoint-sg` | `443` từ EKS/Lambda SG cần gọi AWS APIs | AWS service endpoint | Áp dụng cho interface endpoints như SQS, Secrets Manager, CloudWatch Logs, STS, ECR, Bedrock nếu dùng. |
| `tf1-lambda-sg` nếu Lambda trong VPC | Không cần inbound public | SQS endpoint, DynamoDB endpoint, S3 endpoint, Secrets Manager endpoint | Ingest Lambda nhận event qua Lambda service/API integration; không cần mở inbound trong VPC. |

Rule cụ thể nên được encode bằng Terraform variables/module, ví dụ:

```text
allow internet -> public ALB:443
allow public ALB SG -> app target port
allow aiops worker SG -> ai-engine SG:8080
allow ai-engine SG -> evidence proxy SG:8080
allow app/observability SG -> observability scrape/ingest ports
allow workload SGs -> VPC endpoint SG:443
deny public -> ai-engine/prometheus/loki/grafana/worker
```

Không nên rely vào Security Group để enforce tenant isolation một mình. Tenant isolation phải kết hợp `tenant_id` trong payload, query scope, DynamoDB key, S3 prefix, IAM condition, NetworkPolicy và test cross-tenant.

### 3.4 Kubernetes NetworkPolicy

Nếu CNI hỗ trợ NetworkPolicy (AWS VPC CNI network policy, Calico hoặc Cilium), bật default deny cho namespace nhạy cảm:

```text
default deny ingress + egress:
  - aiops
  - ai-engine
  - observability
```

Allowlist:

- `aiops` -> `ai-engine` trên port API.
- `ai-engine` -> evidence proxy hoặc observability query gateway.
- `app` -> observability ingest/scrape path.
- `observability` -> scrape target theo namespace/label được duyệt.
- Integration Layer -> Jira/Slack egress qua NAT/egress proxy nếu cần.

Inter-tenant communication blocked:

- Tenant context phải có `tenant_id`, `service`, `environment`, `namespace`.
- Production có thể dùng namespace theo tenant/env hoặc service group nếu tenant isolation cần mạnh.
- NetworkPolicy không đủ để chống data leak nếu backend query trả sai dữ liệu; phải kết hợp query gateway, DynamoDB key design, S3 prefix, IAM condition và test cross-tenant.

### 3.5 VPC endpoint and egress policy

Các service AWS nên được gọi qua VPC endpoints khi có thể, nhất là từ private subnets:

| Endpoint | Dùng bởi | Policy direction |
|---|---|---|
| SQS endpoint | Ingest Lambda, CDO Worker | Chỉ cho queue ARN của TF1; Ingest chỉ `SendMessage`, Worker chỉ receive/delete/change visibility. |
| DynamoDB gateway endpoint | Ingest/Worker/Integration | Chỉ table `incident_state`; ưu tiên IAM condition và table/index scope. |
| S3 gateway endpoint | Ingest/Worker/AI/Integration | Chỉ bucket audit/evidence; deny public; prefix theo `{tenant_id}/{service}/{incident_id}`. |
| Secrets Manager endpoint | Lambda/Worker/AI/Integration | Chỉ secret ARN cần thiết cho từng role. |
| CloudWatch Logs endpoint | Lambda/pods nếu export trực tiếp | Chỉ log groups của TF1; retention policy bắt buộc. |
| STS endpoint | IRSA / Pod Identity | Cần cho assume role; restrict bằng IAM trust policy. |
| ECR endpoints | EKS nodes/pods | Pull image từ ECR private repo. |
| Bedrock endpoint nếu bật | AI Engine | Chỉ model allowlist và region approved. |

Outbound internet rule:

- App/demo public traffic đi qua ALB inbound, không cần app mở outbound rộng nếu chỉ emit telemetry nội bộ.
- Jira/Slack là external SaaS nên Integration Layer có thể cần NAT Gateway hoặc egress proxy.
- AI Engine không nên có outbound internet tự do. Nếu cần Bedrock, dùng AWS endpoint. Nếu cần evidence, gọi internal evidence proxy.
- Nếu dùng NAT, tách route table/private subnet theo workload nhạy cảm để tránh mọi pod đều có public egress.

### 3.6 Resource policy controls beyond SG

Một số rủi ro không giải quyết bằng Security Group được, nên cần resource policy/IAM condition:

| Resource | Required controls |
|---|---|
| S3 audit/evidence bucket | Block Public Access, deny non-TLS, SSE-KMS, lifecycle, optional Object Lock, prefix convention theo tenant/service/incident, IAM role chỉ truy cập prefix cần thiết. |
| SQS FIFO queue | SSE enabled, redrive policy tới FIFO DLQ, queue policy chỉ cho Ingest Lambda send và Worker consume, alarm on DLQ > 0. |
| DynamoDB `incident_state` | Encryption, PITR nếu budget cho phép, TTL, conditional write, IAM scope theo table/index, không lưu raw logs/full report. |
| Secrets Manager | Secret resource policy nếu cross-account; rotation; no wildcard read; audit secret read spike. |
| KMS key | Key policy chỉ cho workload roles liên quan; enable rotation; không dùng một CMK chung cho toàn bộ account nếu tách environment. |
| CloudWatch Logs | Retention 7-14 ngày demo hoặc policy prod; redact token; không log raw Authorization header. |

### 3.7 Edge protection: WAF / Shield / ALB

Nếu có public ALB:

- Bắt buộc HTTPS với ACM certificate và TLS policy hiện đại.
- Security group inbound chỉ mở 443.
- Bật ALB access logs nếu endpoint dùng thật.
- AWS Shield Standard mặc định bảo vệ L3/L4.
- AWS WAF dùng khi public endpoint nhận traffic không tin cậy: rate-based rule, AWS Managed Rules cơ bản, request size limit.
- Không expose Grafana/Prometheus/Alertmanager/AI Engine public unauthenticated.

Cost note: WAF và VPC endpoints có cost. Với MVP, chỉ bật WAF cho public endpoint thực sự được dùng; còn internal-only path nên ưu tiên private networking và auth.

---

## 4. Audit trail

### 4.1 Audit goals

Audit trail phải trả lời được:

- Alert nào đã vào hệ thống?
- Ai/component nào đã đọc evidence nào, trong tenant/window nào?
- Vì sao Worker gọi hoặc skip AI?
- AI đã nhận context gì và trả RCA gì?
- Jira/Slack đã tạo/update object nào?
- Retry nào xảy ra, có tạo duplicate side effect không?
- Có tenant mismatch, invalid schema, auth failure hoặc cross-tenant query attempt không?

### 4.2 JSON audit schema

Mỗi event nên log JSON structured:

```json
{
  "schema_version": "tf1.audit.v1",
  "timestamp": "2026-06-26T10:00:00Z",
  "tenant_id": "tenant-a",
  "service": "checkout-api",
  "environment": "prod",
  "incident_id": "inc-001",
  "correlation_id": "corr-001",
  "trace_id": "trace-123",
  "idempotency_key": "tenant-a#checkout-api#HighLatency#20260626T1000",
  "component": "cdo-correlator-worker",
  "actor": "irsa:tf1-correlator-worker-role",
  "event_type": "AI_CALL_REQUESTED",
  "result": "SUCCESS",
  "reason": "new_incident",
  "evidence_scope": {
    "tenant_id": "tenant-a",
    "service": "checkout-api",
    "environment": "prod",
    "start_time": "2026-06-26T09:45:00Z",
    "end_time": "2026-06-26T10:05:00Z",
    "limits": {"logs": 50}
  },
  "artifact_uri": "s3://tf1-audit/tenant-a/checkout-api/inc-001/ai/ai-request.json",
  "jira_ticket_id": "PAY-123",
  "slack_thread_ts": "1719000000.123",
  "latency_ms": 842,
  "error_code": null
}
```

Sensitive fields như token, full Authorization header, webhook secret, PII/raw payload lớn không được log trực tiếp. Nếu cần debug, lưu artifact đã redact trong S3 và link bằng `artifact_uri`.

### 4.3 Storage

| Data | Storage | Retention |
|---|---|---:|
| Workflow state/current status | DynamoDB `incident_state` | 30-90 ngày bằng TTL tùy phase. |
| Audit evidence/artifacts | S3 `tf1-audit` bucket | 90+ ngày cho security baseline. |
| Runtime logs | CloudWatch Logs / Loki | 7-14 ngày demo; prod theo policy. |
| CloudTrail/EKS audit | CloudTrail/S3/CloudWatch | Ít nhất 90 ngày nếu budget cho phép. |

S3 audit bucket controls:

- S3 Block Public Access.
- Bucket policy deny non-TLS (`aws:SecureTransport=false`).
- SSE-KMS cho audit/evidence bucket trong production; SSE-S3 chỉ dùng cho dev/demo không chứa dữ liệu nhạy cảm.
- Object key theo `{tenant_id}/{service}/{incident_id}/...`.
- Lifecycle policy để giảm cost sau retention target.
- S3 Object Lock retention 90+ ngày nếu cần immutable audit chống sửa/xóa. Nếu chưa bật trong MVP, ghi rõ đây là production target và không claim đã enabled.

DynamoDB chỉ lưu state/pointer, không lưu raw logs/full reports:

```text
DynamoDB = current_step, status, retry_count, jira_ticket_id, slack_thread_ts, S3 URI pointers.
S3 = alert payload, evidence bundle, AI request/response, RCA report, Jira/Slack request/response.
```

### 4.4 Query interface

MVP:

- Query DynamoDB theo `incident_id`, `idempotency_key`, `tenant_id`.
- Query S3 theo prefix `{tenant_id}/{service}/{incident_id}/`.
- Dashboard CloudWatch/Grafana cho pipeline health.

Production:

- Glue/Athena table trên S3 audit events.
- Internal Audit API: `GET /v1/audit/{audit_id}` với auth + tenant isolation.
- CloudTrail Lake/Security Hub/GuardDuty integration nếu cần forensic mạnh hơn.

---

## 5. Compliance touch

Capstone không phải compliance audit đầy đủ. Mục này map các control vào chuẩn phổ biến để reviewer thấy design có hướng production.

### 5.1 SOC2-style controls

| SOC2 concern | Control trong TF1 |
|---|---|
| Logical access | IAM least privilege, IRSA per workload, Kubernetes RBAC theo namespace, no default cluster-admin. |
| Change management | Terraform/GitOps/CI-CD, immutable image tag/digest, approval gate cho prod, deployment audit. |
| Monitoring | CloudWatch alarms cho Lambda/SQS/DLQ/DynamoDB/S3/AI/integration; EKS audit/control plane logs nếu bật. |
| Incident management | SQS FIFO retry, DLQ, DynamoDB idempotency, runbook, post-mortem fields. |
| Data protection | Encryption at rest/in transit, tenant-scoped prefix/key, bounded evidence, redaction. |
| Availability | EKS replicas/HPA, queue buffering, fallback ticket khi AI unavailable, no alert loss target. |

### 5.2 Data residency

Current capstone region trong AIOps contract dùng `us-east-1`; nếu CDO infra chọn region khác cần ghi rõ trong `02/04/05` và không trộn dữ liệu không kiểm soát giữa regions.

Production data residency rule:

- Tenant metadata có `region`.
- Evidence/audit của tenant lưu trong approved region.
- Cross-region replication chỉ bật khi có yêu cầu DR/compliance.
- Bedrock/model region phải khớp policy dữ liệu nếu bật AI synthesis thật.
- Không đưa raw telemetry sang public demo endpoint nếu tenant data production.

### 5.3 GDPR-style deletion + retention

Thiết kế cần hỗ trợ xóa dữ liệu tenant khi hết retention hoặc khi tenant offboard:

| Data | Deletion mechanism |
|---|---|
| DynamoDB incident state | TTL + tenant deletion job theo `tenant_id`. |
| S3 evidence/audit | Delete/lifecycle theo prefix tenant; nếu Object Lock còn retention thì chỉ delete sau retention. |
| CloudWatch/Loki logs | Retention policy; không giữ log vô hạn. |
| Secrets | Delete/rotate tenant-specific tokens khi offboard. |
| Evidence proxy cache | TTL ngắn, purge theo tenant. |
| Jira/Slack | Theo policy external system; CDO lưu pointer/audit, không coi Slack/Jira là source of truth cho dữ liệu cần xóa. |

Retention policy phải cân bằng audit và quyền xóa: immutable audit 90+ ngày dùng cho security/replay; sau thời hạn đó lifecycle/purge giảm rủi ro và cost.

### 5.4 Tenant onboarding security gate

Vì `02_infra_design.md` đã bổ sung tenant onboarding flow, mỗi tenant mới chỉ được coi là ready khi qua các bước kiểm tra bảo mật tối thiểu:

- `tenant_id` được gắn vào metric, log, alert, DynamoDB key và S3 prefix.
- Alertmanager grouping có `tenant_id/service/env/severity` để giảm alert noise theo tenant.
- Evidence query thử nghiệm chỉ trả dữ liệu của tenant vừa onboarding.
- S3 prefix và DynamoDB item mẫu không đọc/ghi chéo sang tenant khác.
- Quota/rate limit hoặc ResourceQuota/LimitRange được áp dụng nếu tenant chạy trong namespace riêng.
- Một smoke test tenant mismatch phải bị reject trước khi tenant được mark `READY`.

### 5.5 Out of scope

- PCI-DSS nếu không xử lý card data.
- HIPAA/PHI nếu telemetry không chứa medical data.
- Full SIEM/SOC operation.
- Auto-remediation security approval, vì TF1 không tự rollback/restart/scale.

---

## 6. Threat model (STRIDE)

| Threat | Component | Attack / Failure scenario | Mitigation |
|---|---|---|---|
| Spoofing | Alertmanager -> Ingest Lambda | Kẻ tấn công gửi webhook giả để tạo incident/Jira spam. | HMAC/shared secret, timestamp/nonce, schema validation, payload size limit, WAF/rate limit nếu public. |
| Spoofing | CDO Worker -> AI Engine | Caller giả gọi `/v1/triage`. | Private service, SigV4/JWT/bearer fallback, validate `X-Tenant-Id` và `X-Correlation-Id`. |
| Spoofing | Slack callbacks | Fake Slack command/action. | Verify Slack signature + timestamp; allowlist channel/user group. |
| Tampering | SQS message | Alert event bị sửa hoặc replay. | SQS SSE, IAM send/receive split, message schema version, idempotency key, audit message hash. |
| Tampering | DynamoDB state | Duplicate Jira/Slack hoặc sửa status incident. | Least privilege, conditional writes, PITR, audit state transitions. |
| Tampering | S3 audit evidence | Evidence bị sửa/xóa sau incident. | S3 Object Lock 90+ ngày nếu cần, versioning, Block Public Access, deny non-TLS, CloudTrail data events nếu budget cho phép. |
| Repudiation | AI decision | Không chứng minh được AI đã dùng evidence nào. | Audit `ai-request`, `ai-response`, `evidence_scope`, `audit_id`, `correlation_id`, S3 artifact pointer. |
| Repudiation | Jira/Slack side effects | Không biết ai/component tạo ticket/message. | Integration audit event, idempotency key, ticket/thread pointer, CloudWatch logs đã redact. |
| Information disclosure | AI telemetry access | AI đọc logs/metrics của tenant khác hoặc quá rộng. | Evidence bundle/proxy, scope tenant/service/env/window, max 60m, log limit 50, no arbitrary PromQL/LogQL, audit query. |
| Information disclosure | Secrets | Jira/Slack token xuất hiện trong logs/S3/Git. | Secrets Manager, redaction, secret scan, no secret in sample payload, restricted access. |
| Information disclosure | Grafana/Prometheus/Loki | UI/backend observability public unauthenticated. | Internal access, SSO/RBAC/VPN, NetworkPolicy, no admin API public. |
| Denial of Service | Public ALB/API | Burst traffic làm quá tải app hoặc tăng cost. | WAF/rate limit, HPA, request size limit, CloudWatch alarms. |
| Denial of Service | Alert storm | Hàng loạt alert gọi AI/Jira/Slack quá nhiều. | Alertmanager grouping/inhibition, SQS FIFO buffer, Correlator gating, per-tenant quota, AI call budget. |
| Denial of Service | Poison message | Message lỗi retry mãi gây backlog. | Visibility timeout, max receive count, FIFO DLQ, DLQ alarm, replay runbook. |
| Denial of Service | Bedrock/model | LLM throttling/cost spike. | Timeout, max token/context size, call cap, budget alarm, fallback rule-based triage. |
| Elevation of privilege | EKS pod | Pod đọc node metadata hoặc Kubernetes secrets. | IRSA, restrict IMDS, no privileged/hostPath, Pod Security restricted, RBAC least privilege. |
| Elevation of privilege | CI/CD | Pipeline deploy vượt quyền prod. | OIDC deploy role per env, approval gate, Terraform plan review, no static keys. |
| Elevation of privilege | AI Engine | AI trả action nguy hiểm hoặc gọi remediation. | Action catalog allowlist, no auto-remediation, no AWS write/remediation permissions, human review required. |

---

## 7. Incident response runbook (high-level)

### 7.1 Detection

Signals cần monitor:

- Lambda errors/duration/throttles.
- SQS FIFO visible messages, in-flight messages, oldest message age.
- FIFO DLQ message count > 0.
- CDO Worker error rate, processing latency, AI call skip/call count.
- AI Engine 4xx/5xx/timeout/latency.
- DynamoDB throttles/errors/conditional check failures.
- S3 put/get errors.
- Jira/Slack API failures/rate limits.
- Tenant mismatch / invalid auth / oversized payload.
- CloudTrail IAM/S3/Security Group changes bất thường.
- Secret read spike từ Secrets Manager.
- Cross-tenant query rejection count.

### 7.2 Containment

Theo loại incident:

| Incident | Containment |
|---|---|
| Public API spam | Bật/tighten WAF rate rule, tạm giảm ingress, kiểm tra ALB logs. |
| Webhook spoofing | Rotate Alertmanager signing secret, reject invalid timestamp/nonce, tạm block source. |
| AI Engine abuse/cost spike | Disable Bedrock/hybrid mode, switch `AI_MODE=rules`, tighten AI call quota. |
| Cross-tenant leak suspicion | Freeze evidence proxy, revoke AI evidence token, inspect audit query logs, disable affected tenant path. |
| Secret leak | Rotate secret ngay, invalidate token ở Jira/Slack, scan logs/S3/Git, redeploy workloads. |
| Poison SQS message | Stop redrive, isolate DLQ message, patch parser/schema, replay only after approval. |
| Compromised pod | Scale to zero affected deployment, revoke IRSA role session if possible, rotate secrets, inspect EKS audit. |

### 7.3 Eradication

- Patch vulnerable image/config/IAM policy.
- Remove broad IAM actions hoặc Kubernetes RBAC không cần thiết.
- Fix schema validation, tenant check, query bounds hoặc redaction bug.
- Rebuild image với immutable tag/digest.
- Apply Terraform/GitOps change qua normal pipeline, không hotfix thủ công nếu tránh được.

### 7.4 Recovery

- Redeploy/canary workload đã fix.
- Re-enable queue consumption từ SQS FIFO.
- Replay DLQ message theo runbook và kiểm tra idempotency không tạo duplicate Jira/Slack.
- Smoke test:
  - `/healthz` AI Engine.
  - one valid `/v1/triage`.
  - tenant mismatch returns 400.
  - missing auth returns 401/403.
  - evidence query bounded by tenant/service/window.
  - Slack/Jira integration idempotent.
- Confirm CloudWatch/Grafana alarms trở lại healthy.

### 7.5 Post-mortem

Post-mortem record cần có:

- `incident_id`, `correlation_id`, `tenant_id`, affected service.
- Timeline: detect, contain, fix, recover.
- Root cause.
- Blast radius: tenant nào, data nào, ticket/message nào bị ảnh hưởng.
- Audit artifacts: S3 URI, CloudWatch log group, Jira/Slack pointers.
- Preventive action: IAM tighten, NetworkPolicy, query bound, secret rotation, test mới.
- Owner + deadline.

---

## 8. Security Evidence Checklist

Các evidence nên chuẩn bị cho `07_test_eval_report.md` hoặc buổi defense:

| Test | Expected result |
|---|---|
| Tenant mismatch header/body | AI Engine hoặc Worker reject `400`, không gọi RCA. |
| Missing auth to AI Engine | `401/403`, không xử lý request. |
| Cross-tenant evidence query | Query tenant A không trả data tenant B. |
| Oversized/unbounded logs | Evidence proxy reject hoặc clamp theo limit. |
| SQS retry | Worker fail một lần, message quay lại sau visibility timeout. |
| DLQ path | Poison message vào FIFO DLQ sau max receive count, alarm visible. |
| Idempotency | Retry cùng incident không tạo duplicate Jira/Slack. |
| Secret leak scan | Không có token/webhook/API key trong logs/S3/Git. |
| Public AI endpoint | AI Engine không reachable từ internet. |
| Pod security | Pod không privileged, không hostPath, non-root/read-only filesystem nếu app hỗ trợ. |
| IRSA check | Worker pod dùng đúng AWS role, không dùng node role broad access. |
| Object storage check | S3 Block Public Access enabled; deny non-TLS; Object Lock nếu claim immutable. |

Commands tham khảo:

```powershell
kubectl get sa -n aiops -o yaml
kubectl get role,rolebinding -n aiops
kubectl get networkpolicy -A
kubectl get pods -A -o wide
aws sqs get-queue-attributes --queue-url <raw-alert-fifo-url> --attribute-names All
aws dynamodb describe-table --table-name <incident-state-table>
aws s3api get-public-access-block --bucket <audit-bucket>
aws secretsmanager describe-secret --secret-id <secret-id>
```

---

## 9. Open Questions

| ID | Question | Owner | Target |
|---|---|---|---|
| SQ-01 | Final auth giữa CDO Worker và AI Engine là SigV4, JWT hay bearer fallback? | CDO-05 + AIO-01 | Before W12 integration |
| SQ-02 | Evidence path cuối cùng là S3 bundle, read-only evidence proxy hay cả hai? | CDO-05 + AIO-01 | Before demo |
| SQ-03 | CNI nào enforce NetworkPolicy: AWS VPC CNI policy, Calico hay Cilium? | CDO-05 | Before security evidence |
| SQ-04 | S3 Object Lock có bật thật trong environment không, hay chỉ là production target? | CDO-05 | Before final claim |
| SQ-05 | Jira/Slack integration là live hay dry-run payload? | CDO-05 + AIO-01 | Before demo |
| SQ-06 | Bedrock có bật thật không? Nếu bật, model, region và budget cap là gì? | AIO-01 + CDO-05 | Before cost final |

---

## 10. Related Documents

- [`01_requirements_analysis.md`](01_requirements_analysis.md) - NFR, tenant isolation, auditability, no auto-remediation.
- [`02_infra_design.md`](02_infra_design.md) - source of truth cho EKS, SQS FIFO, DynamoDB, S3, AI/Integration flow.
- [`04_deployment_design.md`](04_deployment_design.md) - CI/CD, GitOps, rollout/rollback, pipeline secret handling.
- [`05_cost_analysis.md`](05_cost_analysis.md) - trade-off cost của WAF, VPC endpoints, CloudWatch retention, Bedrock cap.
- [`07_test_eval_report.md`](07_test_eval_report.md) - nơi ghi evidence test tenant isolation, DLQ, idempotency, auth.
- [`08_adrs.md`](08_adrs.md) - ADR cho EKS, SQS FIFO, DynamoDB idempotency, S3 audit, bounded evidence access.

---

## 11. Defense Summary

```text
CDO-05 không đưa raw logs/metrics vào SQS. SQS FIFO chỉ bảo vệ alert event.
```

```text
CDO Correlator Worker dùng IRSA để thao tác SQS, DynamoDB, S3 và Secrets Manager theo least privilege.
```

```text
AI Engine chỉ được đọc bounded evidence theo tenant/service/env/window, không có arbitrary PromQL/LogQL hoặc observability credential trực tiếp.
```

```text
DynamoDB lưu workflow state và idempotency; S3 lưu audit evidence; Prometheus/Loki/CloudWatch vẫn là nguồn raw telemetry.
```

```text
No auto-remediation: AI chỉ đưa recommendation, CDO workflow và con người kiểm soát Jira/Slack/assignment.
```
