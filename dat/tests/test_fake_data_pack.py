from __future__ import annotations

import json
from pathlib import Path
import pytest

from cdo_correlator.correlate import correlate_payload
from cdo_evidence_builder.builder import build_evidence_bundle

ROOT = Path(__file__).resolve().parents[2]
FAKE_DATA_DIR = ROOT / "Xbrain_fake_data" / "fake-data"
CORRELATOR_INPUT_DIR = FAKE_DATA_DIR / "correlator-input"
EXPECTED_INCIDENT_DIR = FAKE_DATA_DIR / "expected-incident"
EVIDENCE_ROOT = FAKE_DATA_DIR / "evidence"


def get_all_scenarios() -> list[str]:
    """Get the base names of all scenario json files."""
    if not CORRELATOR_INPUT_DIR.exists():
        return []
    return sorted([p.stem for p in CORRELATOR_INPUT_DIR.glob("*.json")])


@pytest.mark.parametrize("scenario_name", get_all_scenarios())
def test_scenario_correlator(scenario_name: str) -> None:
    input_path = CORRELATOR_INPUT_DIR / f"{scenario_name}.json"
    expected_path = EXPECTED_INCIDENT_DIR / f"{scenario_name}_incident.json"

    assert input_path.exists(), f"Input path not found: {input_path}"
    assert expected_path.exists(), f"Expected path not found: {expected_path}"

    with input_path.open(encoding="utf-8") as f:
        payload = json.load(f)
    with expected_path.open(encoding="utf-8") as f:
        expected = json.load(f)

    # Run correlation
    output, state = correlate_payload(payload)

    expected_status = expected.get("status")

    if expected_status == "CORRELATED":
        # The correlator returns the incident dict directly on success.
        expected_incident = expected["incident"]
        assert output["incident_id"] == expected_incident["incident_id"]
        assert output["correlation_id"] == expected_incident["correlation_id"]
        assert output["tenant_id"] == expected_incident["tenant_id"]
        assert output["environment"] == expected_incident["environment"]
        assert output["cluster"] == expected_incident["cluster"]
        assert output["namespace"] == expected_incident["namespace"]
        assert output["service"] == expected_incident["service"]
        assert output["severity"] == expected_incident["severity"]

        # Check signals and alerts lists
        assert set(output["signals"]) == set(expected_incident["signals"])
        assert set(output["alert_ids"]) == set(expected_incident["alert_ids"])

        # Check related entities
        if "related_entities" in expected_incident:
            for entity_type, entity_list in expected_incident["related_entities"].items():
                assert set(output["related_entities"].get(entity_type, [])) == set(entity_list)

        # Test phase 3: build evidence bundle on the correlated incident
        bundle = build_evidence_bundle(output, evidence_root=EVIDENCE_ROOT)
        assert bundle["schema_version"] == "cdo.evidence.v1"
        assert bundle["incident_id"] == output["incident_id"]
        assert bundle["service"] == output["service"]
        assert bundle["tenant_id"] == output["tenant_id"]
        assert bundle["environment"] == output["environment"]

        # For OOMKilled and CPU Throttling, context quality should be COMPLETE
        if scenario_name in ("13_container_oomkilled", "14_cpu_throttling", "01_main_scenario"):
            assert bundle["context_quality"] == "COMPLETE"
            assert bundle["metrics"]
            assert bundle["logs"]
            assert bundle["k8s_events"]
            assert bundle["ownership"]

            # Scenario 2 specific check: make sure metrics and logs contain OOMKilled/thread logs
            if scenario_name == "13_container_oomkilled":
                assert any(m["metric_name"] == "memory_usage_mb" for m in bundle["metrics"])
                assert any("unable to create new native thread" in log["message"] for log in bundle["logs"])
                assert any(e["reason"] == "OOMKilled" for e in bundle["k8s_events"])

            # Scenario 6 specific check: make sure metrics and logs contain CPU/throttling info
            if scenario_name == "14_cpu_throttling":
                assert any(m["metric_name"] == "cpu_throttling_percent" for m in bundle["metrics"])
                assert any("ThreadPoolExecutor" in log["message"] for log in bundle["logs"])

    elif expected_status == "MULTIPLE_GROUPS_UNSUPPORTED":
        # The correlator returns a dict with status and skipped details.
        assert output["status"] == "MULTIPLE_GROUPS_UNSUPPORTED"
        output_keys = {
            f"{g['tenant_id']}:{g['environment']}:{g['cluster']}:{g['namespace']}:{g['service']}:{g['time_bucket']}"
            for g in output["group_keys"]
        }
        assert output_keys == set(expected["group_keys"])
    else:
        # Fallback or other status comparison
        assert output["status"] == expected_status
