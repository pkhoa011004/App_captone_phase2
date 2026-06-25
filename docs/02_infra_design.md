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
SQS Raw Alert Queue
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

Amazon EKS is the core compute platform, hosting the Demo App, Correlator Worker, and Prometheus/Loki/Grafana. Users access workloads through an ALB. 

PrometheusRules send alerts to Alertmanager when metrics breach thresholds. Alertmanager groups and suppresses alert noise before calling Ingest Lambda. Lambda validates metadata, logs raw events to S3, updates DynamoDB queue states, and routes messages to SQS.

The Correlator Worker polls SQS, verifies idempotency against DynamoDB, deduplicates/groups alerts into single incidents, saves correlation payloads to S3, and calls the AI Engine. The AI Engine queries Prometheus/Loki within bounded limits to run RCA. Finally, Integration Lambda triggers Slack/Jira notifications, writes logs to S3, and updates DynamoDB. CloudWatch monitors serverless AWS services.

## 1.4 Data ownership boundary

- **Normal observability flow**: App $\rightarrow$ Prometheus/Loki/Grafana. AI Engine queries telemetry via bounded read-only APIs. Raw metrics/logs remain in the monitoring stack and do not enter SQS.
- **Alert incident flow**: PrometheusRule $\rightarrow$ Alertmanager $\rightarrow$ Lambda $\rightarrow$ SQS $\rightarrow$ Correlator $\rightarrow$ AI $\rightarrow$ Integration $\rightarrow$ Slack/Jira. This pipeline carries only trigger events and state changes.

## 1.5 Responsibility boundary: CDO vs AIOps / AI Engine

- **CDO (Platform) owns**: EKS runtime, monitoring stack, ingestion/integration Lambdas, SQS/DLQ, Correlator Worker, DynamoDB states, S3 audit store, NetworkPolicies, IAM roles, and CloudWatch.
- **AI Engine owns**: Incident triggers, querying Prometheus/Loki, building telemetry contexts, executing RCA, and generating Slack/Jira payloads.

# 2. Component table

|Component|AWS Service / Tool|Reason|Cost note|
|---|---|---|---|
|Compute|Amazon EKS|Main runtime for demo app, CDO Correlator Worker, and observability stack. Chosen because Kubernetes gives consistent workload metadata, namespace, labels, service discovery, NetworkPolicy, and GitOps-friendly deployment context.|Higher fixed cost than ECS/Lambda because of EKS control plane and worker nodes. Accepted for Kubernetes-native design.|
|API entry|ALB + AWS Load Balancer Controller|Public entry point for user/load generator traffic into demo app on EKS. Managed through Kubernetes Ingress.|ALB has hourly and traffic-based cost. Keep one shared ALB for MVP.|
|Metrics|Prometheus|Stores application and Kubernetes metrics, evaluates PrometheusRule, and provides query source for SRE/AIOps.|Runs inside EKS, consumes node CPU/memory/storage. Retention should be limited for MVP.|
|Logs|Loki|Stores Kubernetes workload logs and supports label-based query by namespace, pod, service, tenant_id, env, and time window.|Runs inside EKS. Cost depends on log volume and retention.|
|Dashboard|Grafana|Dashboard and investigation UI for metrics, logs, and alert status.|Runs inside EKS. Low MVP footprint.|
|Alert noise control|Alertmanager|First-layer alert noise control: grouping, inhibition, silence, group_wait, repeat_interval.|Runs as part of monitoring stack.|
|Alert ingestion|Ingest Lambda|Receives Alertmanager webhook, validates required fields, normalizes alert payload, optionally writes raw evidence, and sends message to SQS.|Low cost for MVP because alert volume is small.|
|Event queue|SQS Raw Alert Queue + DLQ|Durable alert buffer, retry, visibility timeout, backlog visibility, DLQ for failed alerts. Decouples monitoring from downstream processing.|Low for capstone traffic. Must monitor backlog and DLQ.|
|Incident worker|CDO Incident Correlator Worker on EKS|Polls SQS, deduplicates alerts, correlates related alerts, updates DynamoDB, writes S3 artifacts, and calls AI Engine when needed.|Runs on EKS worker nodes. Can scale by backlog.|
|Incident state|DynamoDB|Stores incident_state, alert_fingerprint, correlation_key, workflow progress, retry_count, Jira ticket ID, Slack thread ID, last_error, and S3 URI pointers. Enables idempotency.|Low for MVP. On-demand mode is simpler for unpredictable demo traffic.|
|Artifact storage|S3|Stores original alert payload, grouped alerts, AI request/response, AI context/evidence, RCA report, Jira/Slack payloads, and replay/debug material.|Low cost. Can use lifecycle policy to move older evidence to cheaper tier.|
|RCA engine|AI Engine|Performs RCA by querying Prometheus/Loki and analyzing incident context.|Owned by AIOps team. Cost depends on model/runtime.|
|External integration|Integration Lambda / CDO Integration Layer + Jira + Slack|Creates/updates Jira and Slack. One incident should map to one Jira ticket and one Slack thread.|External service cost depends on account/license, not core AWS infra.|
|AWS-side monitoring|CloudWatch|Monitors Lambda logs, SQS backlog, DLQ count, DynamoDB errors/throttles, S3 errors, and AWS integration logs.|Cost depends on log volume and retention. Set retention policy.|
|Secret management|Secrets Manager / SSM|Stores Jira token, Slack token/webhook, AI Engine API key, and runtime secrets.|Low if secret count is small.|
|Pod AWS access|IAM + IRSA / EKS Pod Identity|Allows EKS pods to access SQS, DynamoDB, S3, and Secrets Manager with least privilege.|No major direct cost, but important for security.|

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
|Ingest Lambda|Validates and normalizes alert webhook, optionally stores raw alert artifact, writes initial ingest/queue state, pushes alert to SQS.|Does not do RCA, does not deeply query metrics/logs, does not call AI Engine for RCA, does not create Jira/Slack.|
|SQS|Stores alert event durably and supports retry/DLQ.|Does not store metric/log raw and does not write to DynamoDB/S3 by itself.|
|SQS DLQ|Stores messages that fail too many times.|Does not fix failed messages automatically.|
|CDO Correlator Worker|Polls SQS, deduplicates alerts, correlates related alerts, updates DynamoDB, writes S3 artifacts, decides whether to call AI Engine.|Does not own RCA reasoning, baseline calculation, anomaly interpretation, or deep log analysis.|
|DynamoDB|Stores incident state, idempotency keys, workflow progress, Jira/Slack IDs, and pointers to S3 artifacts.|Does not store raw logs, full metric windows, or large AI evidence.|
|S3 Artifact Store|Stores audit evidence, AI request/response, payload snapshots, RCA reports, and replay/debug material.|Does not track live workflow state and does not serve as the state machine.|
|AI Engine|Queries observability data, builds RCA context, performs reasoning, optionally writes AI artifacts to S3, returns RCA/confidence/suggested actions.|Does not own alert durability, SQS retry, pipeline state, or Jira/Slack side-effect control.|
|Integration Lambda / CDO Integration Layer|Creates/updates Jira and Slack, writes request/response audit artifacts, updates DynamoDB.|Does not perform RCA.|
|Jira/Slack|Human-facing incident tracking and notification.|Does not act as source of truth for workflow state.|
|CloudWatch|Monitors AWS-side pipeline components.|Does not replace Loki for Kubernetes application logs.|

---

# 3. Differentiation angle deep-dive

- **Selected Angle**: Reliable Incident Triage Pipeline with Alert Storm Control and AI Call Gating.
- **Rationale**: EKS provides the runtime, but the core innovation is the pre-AI pipeline. By buffering alerts in SQS and correlating them in the CDO Worker via DynamoDB state, we prevent alert storms from spamming Slack/Jira and block duplicate, costly AI Engine calls.

## 3.1 Why this angle?
Single root-cause failures trigger cascading alerts across downstream services (e.g., DB timeouts). Sending each alert directly to the AI Engine wastes compute, spams Slack, and duplicates tickets. The CDO pipeline groups related alerts in a 5-minute window using DynamoDB state, invoking the AI Engine once per incident.

## 3.2 Why not Lambda or ECS as the main platform?
- **Why not Lambda?**: Lambda is unsuitable for running long-lived monitoring stacks or workloads and lacks K8s-native metadata for workload identification. It serves only as a lightweight webhook ingestion adapter.
- **Why not ECS Fargate?**: ECS lacks K8s-native features (namespaces, pod labels, ArgoCD). Finding RCA context on ECS requires complex custom glue code to map tasks, CloudWatch logs, ALB targets, and CI/CD events.

## 3.3 Why EKS still matters in this angle
EKS provides a unified metadata model (`tenant_id`, `service`, `env`, `namespace`, `pod`, `deployment`, `version`) across workloads, metrics, logs, alerts, and GitOps rollout history. This consistent label set allows the AI Engine to query telemetry without custom mapping.

## 3.4 Architectural advantages
- **Reliability**: SQS prevents alert loss; DLQ isolates poison messages.
- **Idempotency**: DynamoDB checks prevent duplicate AI calls and tickets.
- **Replayability**: S3 stores full request/response contexts for debugging.
- **Metadata Consistency**: Shared labels unify runtime, metrics, logs, and alerts.

## 3.5 Weakness accepted
Increased operational overhead due to managing EKS, Prometheus, Loki, SQS, DynamoDB, and S3. The MVP correlation is rule-based and not yet topology-aware or trace-aware.

# 4. Multi-tenant approach

- **Tenant Model**: Pooled resource model separated logically by metadata (`tenant_id`, `service`, `env`).
- **Isolation**:
  - *Data*: Metrics, logs, DynamoDB records, and S3 paths are partitioned by tenant labels.
  - *Compute*: K8s namespaces, NetworkPolicies, and ResourceQuotas isolate workloads in the EKS cluster.
- **Bounded Access**: AI Engine queries Prometheus/Loki via an internal gateway scoped strictly by tenant, service, and window.
- **Onboarding Flow**: Developers tag configurations with tenant labels, configure namespace boundaries, and set Alertmanager grouping rules.
- **Noisy Neighbors**: Controlled via ResourceQuotas, Alertmanager grouping, and SQS visibility monitoring.

# 5. Key design decisions / alternatives considered

- **Compute**: EKS chosen over ECS/Lambda for native K8s metadata consistency and Prometheus/Loki operator integration.
- **Ingress**: ALB + AWS Load Balancer Controller selected over API Gateway for native Kubernetes ingress management.
- **Ingestion**: Ingest Lambda selected to validate and normalise Alertmanager alert webhooks before queueing in SQS.
- **Queueing**: SQS + DLQ chosen over direct AI webhook to handle alert bursts and guarantee message durability.
- **State Store**: DynamoDB on-demand chosen over RDS for low costs and native conditional writes for idempotency.
- **Audit Store**: S3 chosen over DynamoDB for low-cost, long-term retention of raw alert payloads and AI contexts.
- **Observability**: Prometheus/Loki handle EKS workload metrics and logs; CloudWatch monitors serverless AWS services.
- **Noise Control**: Layer 1 noise is handled by Alertmanager (grouping); Layer 2 gating is handled by CDO Correlator + DynamoDB.

# 6. Scaling strategy

- **Vertical**: Scale EKS node instance types, Prometheus, or Loki CPU/memory when bottlenecks occur.
- **Horizontal**: Auto-scale app and Correlator Worker pods based on CPU/memory and SQS queue depth (messages visible and age).
- **AI Call Control**: Call AI only for new incidents, severity upgrades, or manual re-analysis; skip for duplicates to protect LLM budget.

# 7. Failure modes and recovery

|Failure|Detection|Recovery|Data loss expectation|
|---|---|---|---|
|Demo app pod crash|Kubernetes events, Prometheus target down|Kubernetes restarts/reschedules pod|No incident state loss if app is stateless|
|Prometheus unavailable|Grafana/Prometheus health, scrape failure|Restart pod, restore config/storage if needed|Metrics gap possible during outage|
|Loki unavailable|Grafana Explore error, Loki pod health|Restart Loki/agent, inspect storage|Logs gap possible during outage|
|Alert storm|Alert volume spike, Alertmanager dashboard, SQS backlog|Alertmanager grouping/inhibition + Correlator gating|Alert event retained if sent to SQS|
|Ingest Lambda error|CloudWatch Lambda error/duration|Fix schema/config and replay if source supports retry|Possible alert loss before SQS if source does not retry|
|SQS backlog high|CloudWatch SQS visible messages / age|Scale worker, inspect downstream latency/errors|No loss while messages remain in queue|
|Worker crash|Pod restart, worker logs, SQS message visible again|SQS retries message; worker resumes using DynamoDB state|No loss if message not deleted|
|Duplicate alert|Same alert_fingerprint|Update count/last_seen_at, skip new incident|No duplicate incident expected|
|Related alerts|Same correlation_key|Append to existing incident and update state|No duplicate Jira/Slack expected|
|AI Engine unavailable|Worker call error, timeout|Do not mark AI step complete; retry/backoff; keep state in DynamoDB|Alert state preserved|
|AI Engine S3 write failure|AI error, missing artifact URI|AI retries or returns artifact to Worker for storage|RCA may continue, but audit evidence may be incomplete|
|Jira created but Integration Lambda crashes before Slack|DynamoDB has jira_ticket_id and current_step|On retry, skip Jira and continue Slack|No duplicate Jira expected|
|Slack failure|Integration Lambda error and last_error in DynamoDB|Retry Slack update using existing incident state|No duplicate Jira expected|
|DynamoDB throttle/error|CloudWatch DynamoDB metrics|Retry with backoff; tune capacity/on-demand|State write may fail until retry succeeds|
|S3 write failure|Worker/Lambda logs, CloudWatch error|Retry audit write; keep minimal state in DynamoDB|Audit evidence may be incomplete if not retried|
|DLQ has messages|CloudWatch DLQ message count|Inspect, fix bug, replay manually|No loss if DLQ retention is sufficient|
|CloudWatch logging issue|Missing logs/metric ingestion|Check log group/retention/IAM|Pipeline may still run but debugging is harder|
|AZ/node failure|EKS node events, pod rescheduling|Multi-AZ node group if configured|Managed services retain queue/state|
|Region outage|External monitor/manual detection|Out of MVP scope; future DR plan|TBD|

---

# 8. Security and access notes

- **Network Security**: EKS workers run in private subnets; public ingress is restricted through ALB. Namespace NetworkPolicies block unauthorized inter-pod traffic.
- **Access Control**: IRSA grants pods least-privilege IAM roles to access SQS, DynamoDB, S3, and Secrets Manager.
- **Data Protection**: S3 audit buckets use KMS encryption and bucket policies. Observability queries by the AI Engine are strictly read-only and scoped to the tenant/service/window context.

# 9. MVP scope

- **Included**: EKS runtime, ALB ingress, Prometheus/Loki/Grafana stack, Ingest Lambda, SQS alert queue, CDO Correlator, DynamoDB incident state, S3 audit store, and Jira/Slack integration.
- **Excluded**: Automated SaaS tenant provisioning lifecycle, topology-aware trace correlation, and auto-remediation.

# 10. Future improvements

- **Dependency Graph**: Store service dependency topology to improve cascading alert correlation.
- **OTel Tracing**: Add distributed tracing with OpenTelemetry Collector and Grafana Tempo.
- **AI-assisted Correlation**: Allow AI to suggest alert relationships under rule-based guardrails.

# 11. Final takeaway

CDO builds the EKS runtime, alert pipeline, and state storage. The AI Engine queries this telemetry within bounded limits to perform RCA. This clean division of concerns protects the AI Engine from storm overhead while providing rich context for triage.

# Related documents

- `01_requirements_analysis.md` — Problem statement, NFRs, and compute rationale.
- `03_security_design.md` — IAM, RBAC, NetworkPolicy, and Secrets Manager.
- `04_deployment_design.md` — IaC (Terraform) and ArgoCD GitOps deployment design.
- `05_cost_analysis.md` — Cost model and actual capstone spend.
- `07_test_eval_report.md` — Load test, failure test, and storm recovery reports.