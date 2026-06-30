# CDO Local Pipeline

Local Python implementation of a fake CDO alert pipeline. The repository keeps
source code, fixtures, tests, and generated sample outputs together so the
pipeline can be run end to end on a developer machine.

## What Is Inside

```text
src/      Python packages and CLIs
tests/    pytest suite
data/     fake alerts, evidence, and shared fixtures
outputs/  generated sample outputs used by local demos/tests
legacy/   archived pre-restructure artifacts
```

The pipeline has three local phases:

1. `cdo-ingest`: validates and normalizes fake alert JSON.
2. `cdo-correlate`: groups valid same-service alerts into an incident.
3. `cdo-build-evidence`: builds an evidence bundle for the incident.

## Requirements

- Python 3.12+
- `pip`

## Setup

Create a virtual environment and install the package with test dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

This installs the local CLI commands:

```text
cdo-ingest
cdo-correlate
cdo-build-evidence
```

If you do not install the package, you can still run modules by prefixing
commands with `PYTHONPATH=src`.

## Run Tests

```bash
python -m pytest -q
```

The tests cover:

- Phase 1 alert validation, enrichment, and Lambda-style handler input.
- Phase 2 same-service correlation, dedupe, state updates, and unsupported groups.
- Phase 3 evidence bundle generation, filtering, context quality, and validation.

## Run The Local Pipeline

All commands below use fake data committed under `data/` and write local output
under `outputs/`.

### Phase 1: Ingest Alerts

```bash
cdo-ingest \
  --input data/fake/phase1-ingest/alerts \
  --output outputs/phase1-ingest/normalized-alerts \
  --service-catalog data/shared/service-catalog/service-catalog.yaml \
  --received-at 2026-06-29T10:01:00Z
```

Expected output files are written to:

```text
outputs/phase1-ingest/normalized-alerts/
```

### Phase 2: Correlate Alerts

For a repeatable demo run, remove the local state file first. If the file does
not exist, the correlator starts with an empty state automatically.

```bash
rm -f outputs/phase2-correlator/state/open-incidents.json

cdo-correlate \
  --input data/fake/phase2-correlator/input/case-01-book-service-multisignal-normalized-wrappers.json \
  --state outputs/phase2-correlator/state/open-incidents.json \
  --output outputs/phase2-correlator/incident.json
```

Expected output:

```text
outputs/phase2-correlator/incident.json
outputs/phase2-correlator/state/open-incidents.json
```

### Phase 3: Build Evidence Bundle

```bash
cdo-build-evidence \
  --incident outputs/phase2-correlator/incident.json \
  --evidence-root data/fake/phase3-evidence/evidence \
  --output outputs/phase3-evidence-builder/evidence_bundle.json
```

Expected output:

```text
outputs/phase3-evidence-builder/evidence_bundle.json
```

## Run Without Installing

Use the module entry points directly:

```bash
PYTHONPATH=src python -m cdo_ingest.cli --help
PYTHONPATH=src python -m cdo_correlator.cli --help
PYTHONPATH=src python -m cdo_evidence_builder.cli --help
```

## Data Notes

- `data/fake/phase1-ingest/alerts/` contains raw fake alerts.
- `data/fake/phase1-ingest/expected-output/` contains expected normalized alert fixtures.
- `data/fake/phase2-correlator/input/` contains normalized alert wrappers for correlation tests.
- `data/fake/phase3-evidence/evidence/` contains metrics, logs, traces, Kubernetes events, deploys, and ownership evidence.
- `data/shared/service-catalog/` contains enrichment metadata used by ingest.

## Boundary

This is a local fake-data pipeline. It does not perform RCA, call external AIO
services, create tickets, or mutate infrastructure.
