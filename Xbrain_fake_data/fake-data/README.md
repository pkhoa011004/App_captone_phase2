# CDO Ingest and Same-Service Correlator Fake Data Pack

This data pack contains test scenarios and datasets designed to validate the CDO alert ingestion pipeline and the same-service alert correlation mechanism for Phase 2 MVP.

## Directory Structure
- `alerts/`: Contains raw alert manager alerts.
  - `raw/`: Raw alerts directly from Prometheus or Kubernetes.
- `ingest-output/`: Expected output wrappers produced by the Ingest Lambda.
- `correlator-input/`: Groups of ingest wrappers used as inputs to the Correlator service.
- `expected-incident/`: Expected correlation outputs.
- `evidence/`: Fixtures representing raw metrics, logs, traces, Kubernetes events, and deployments for future Evidence Builder validation.
- `expected-evidence-bundle/`: Fully assembled expected evidence bundle.
- `expected-triage-context/`: Expected final triage context (with `evidence_uri` S3 pointer).

## Test Scenarios
### Passing Scenarios (Correlated as One Incident)
1. **Main Same-Service Correlation (`correlator-input/scenario-main-same-service.json`)**: 
   - 5 alerts (5xx, Latency, Healthcheck, Crashloop, Restart) firing on `book-service` within a 10-minute window.
   - Expected Output: `expected-incident/incident-main-same-service.json` (severity: `critical`, next_step: `BUILD_EVIDENCE`).

2. **Deduplication (`correlator-input/scenario-duplicates.json`)**:
   - Replayed duplicates of the same alert should be deduplicated inside the same time bucket.

### Failing/Unsupported Scenarios (Rejected or Multi-Incident)
1. **Multiple Groups (`correlator-input/scenario-multiple-groups.json`)**:
   - Contains alerts for both `book-service` and `order-service`.
   - Expected Output: `status: MULTIPLE_GROUPS_UNSUPPORTED` since the Phase 2 MVP only supports processing a single same-service group per run.
2. **Different Namespace (`correlator-input/scenario-diff-namespace.json`)**:
   - Alerts with different namespace labels will not be grouped together.
3. **Invalid Alert (`ingest-output/ingest-book-service-invalid.json`)**:
   - Wrapper showing `status: INVALID_ALERT` because it lacks mandatory envelope fields like `tenant_id` and `environment`.
