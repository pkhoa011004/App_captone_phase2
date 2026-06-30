# CDO Phase 1 Fake Data

Mục tiêu:
- Dùng fake data để test pipeline CDO trước khi có app thật hoặc AIO image thật.
- Flow cần test: raw alert -> ingest -> normalized alert -> correlator -> incident -> evidence builder -> triage_context.json.

Thứ tự code đề xuất:
1. Ingest local/Lambda-compatible handler
   - input: fake-data/alerts/*.json
   - output: normalized alert hoặc INVALID_ALERT.
   - không RCA, không build evidence.
   - service-catalog/service-catalog.yaml chỉ dùng để enrich optional labels nếu có sẵn.

2. Correlator
   - input: normalized alert(s) + service-map/service-map.yaml
   - output: incident.json.

3. Evidence Builder
   - input: incident.json
   - đọc metrics/logs/traces/deploys/ownership
   - output: evidence_bundle.json + triage_context.json.

4. Mock AIO
   - input: expected-output/expected-triage-context-s3-pointer.json hoặc inline.
   - endpoint giả: POST /v1/triage.

Các case:
- case-01-book-service-multisignal-flat.json: alert book-service dạng flat, dùng trước để test Ingest metadata/labels.
- case-01-complete-alert.json: alert đủ metadata.
- case-02-missing-metadata-alert.json: thiếu tenant_id/environment để test reject.
- case-03-duplicate-alerts.json: test dedup.
- case-04-impact-alerts.json: test dependency-aware grouping.
- case-05-recent-deploy-alert.json: test deploy context.

Ghi chú:
- Alert không chứa metric/log raw.
- Evidence đầy đủ nằm trong evidence_bundle.json và có thể lưu S3.
- triage_context_s3_pointer có metrics/logs/traces empty inline nhưng alert.labels.evidence_uri trỏ tới evidence bundle.

Chạy local Phase 1:
```bash
PYTHONPATH=src python -m cdo_ingest.cli \
  --input cdo-phase1-fake-data/alerts \
  --output output/normalized-alerts \
  --service-catalog cdo-phase1-fake-data/service-catalog/service-catalog.yaml
```
