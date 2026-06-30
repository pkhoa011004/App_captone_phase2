# Correlator Logic Notes for Codex

## Scope

Implement same-service multi-signal correlation only.

Do not implement:
- full dependency impact graph
- RCA
- confidence score
- rollback decision
- AI recommendation logic

## Input

The correlator receives normalized alerts from Ingest Lambda.

Minimum required fields per alert:

```text
alert_id
source
service
severity
title
started_at
labels.tenant_id
labels.environment
labels.cluster
labels.namespace
```

Recommended fields:

```text
labels.pod
labels.deployment
labels.container
labels.signal
labels.metric_names
labels.trace_id
labels.jira_project
labels.jira_component
```

## Correlation key

Use:

```text
tenant_id + environment + cluster + namespace + service + time_bucket
```

For this dataset:

```text
tenant-a|prod|eks-prod|bookhub-prod|book-service|2026-06-29T10:00
```

## Correlation window

Recommended:

```text
10 minutes
```

Group alerts into one incident if:

```text
same tenant_id
same environment
same cluster
same namespace
same service
started_at within correlation window
```

## Dedup key

Use:

```text
tenant_id + environment + cluster + namespace + service + title/alertname + pod/deployment + time_bucket
```

If duplicate alert arrives in same window:
- Do not create a new incident.
- Append only if alert_id not seen.
- Track duplicate_count or ignored_duplicates if helpful.

## Severity aggregation

Suggested order:

```text
critical > warning > info
```

Incident severity is max severity among grouped alerts.

## Incident output

The incident should contain:

```text
incident_id
correlation_id
tenant_id
environment
cluster
namespace
service
severity
status
correlation_type
signals
alert_ids
source_alerts
primary_entity
related_entities
time_window
correlation_reason
```

## Evidence window

Use contract-style bounded evidence window:

```text
evidence_start = first_alert_started_at - 15 minutes
evidence_end   = last_alert_started_at + 5 minutes
```

For this dataset:

```text
evidence_start = 2026-06-29T09:45:00Z
evidence_end   = 2026-06-29T10:05:00Z
```

## Output example

See:

```text
expected-output/expected-incident-case-01.json
```
