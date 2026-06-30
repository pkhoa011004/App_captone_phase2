# CDO Phase 3 Evidence Data

This folder contains local fake evidence for the Evidence Builder MVP.

Input incident:

```text
cdo-phase2-correlator-results/incident.json
```

Evidence root:

```text
cdo-phase3-evidence-data/evidence/
```

Run:

```bash
PYTHONPATH=src python -m cdo_evidence_builder.cli \
  --incident cdo-phase2-correlator-results/incident.json \
  --evidence-root cdo-phase3-evidence-data/evidence \
  --output cdo-phase3-evidence-results/evidence_bundle.json
```

Boundary: this stage only packages bounded evidence. It does not perform RCA, call AIO, create tickets, or build the final triage request.
