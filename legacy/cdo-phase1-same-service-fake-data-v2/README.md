# CDO Phase 1 Same-Service Multi-Signal Fake Data v2

## Purpose

This dataset is for testing the CDO Phase 1 pipeline:

```text
fake alerts
→ ingest lambda
→ normalized alerts
→ same-service correlator
→ incident.json
→ evidence builder
→ evidence_bundle.json
→ triage_context.json with evidence_uri
→ mock AIO /v1/triage
```

## Main scenario

`book-service` fails and multiple signals are emitted from different sources:

- High 5xx rate
- High latency
- Healthcheck failed
- Pod CrashLoopBackOff
- Container restart high
- `order-service` timeout when calling `book-service`

These alerts should be grouped into **one incident** because they share:

```text
tenant_id=tenant-a
environment=prod
cluster=eks-prod
namespace=bookhub-prod
service=book-service
correlation_window≈10 minutes
```

## Timeline

```text
09:45–09:55 = baseline normal
09:59       = degradation starts / healthcheck fails
10:00       = 5xx + latency alerts fire
10:01–10:05 = pod restart, CrashLoopBackOff, timeout from order-service
```

Evidence window:

```text
2026-06-29T09:45:00Z → 2026-06-29T10:05:00Z
```

## Files

```text
alerts/
  case-01-book-service-multisignal-flat.json
  case-01-book-service-multisignal-alertmanager.json
  case-02-missing-metadata-flat.json
  case-03-duplicate-alerts-flat.json

evidence/
  metrics/book-service-metrics-window.json
  logs/book-service-logs-window.json
  traces/book-service-trace-summary-window.json
  k8s-events/book-service-k8s-events-window.json
  deploys/recent-deploys.json
  ownership/service-ownership.json
  evidence_bundle_case_01.json

expected-output/
  expected-incident-case-01.json
  expected-evidence-bundle-case-01.json
  expected-triage-context-s3-pointer-case-01.json

docs/
  correlate-logic-notes.md
```

## Recommended test order

1. Send `alerts/case-01-book-service-multisignal-flat.json` to your ingest lambda.
2. Check ingest output: every alert should be VALID.
3. Feed normalized alerts to correlator.
4. Correlator should produce an incident similar to `expected-output/expected-incident-case-01.json`.
5. Evidence builder should produce a bundle similar to `expected-output/expected-evidence-bundle-case-01.json`.
6. Final request to AIO should match `expected-output/expected-triage-context-s3-pointer-case-01.json`.

## Negative tests

- `case-02-missing-metadata-flat.json`: ingest should reject or mark INVALID_ALERT.
- `case-03-duplicate-alerts-flat.json`: correlator should dedup repeated alerts in the same service/time window.
