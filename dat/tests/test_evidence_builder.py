from __future__ import annotations

import json
from pathlib import Path

import pytest

from cdo_evidence_builder.builder import EvidenceBuilderError, build_evidence_bundle
from cdo_evidence_builder.models import FORBIDDEN_RCA_FIELDS

ROOT = Path(__file__).resolve().parents[1]
INCIDENT = ROOT / "outputs" / "phase2-correlator" / "incident.json"
EVIDENCE_ROOT = ROOT / "data" / "fake" / "phase3-evidence" / "evidence"


def test_builds_complete_evidence_bundle() -> None:
    incident = _load_json(INCIDENT)

    bundle = build_evidence_bundle(incident, evidence_root=EVIDENCE_ROOT)

    assert bundle["schema_version"] == "cdo.evidence.v1"
    assert bundle["incident_id"] == incident["incident_id"]
    assert bundle["correlation_id"] == incident["correlation_id"]
    assert bundle["service"] == "book-service"
    assert bundle["evidence_window"] == {
        "start": "2026-06-29T09:45:00Z",
        "end": "2026-06-29T10:10:00Z",
    }
    assert bundle["context_quality"] == "COMPLETE"
    assert bundle["missing_context"] == []
    assert bundle["optional_missing_context"] == []
    assert bundle["metrics"]
    assert bundle["logs"]
    assert bundle["traces"]
    assert bundle["k8s_events"]
    assert bundle["recent_deploys"]
    assert bundle["ownership"]["service"] == "book-service"
    for field in FORBIDDEN_RCA_FIELDS:
        assert field not in bundle


def test_metrics_points_are_filtered_by_evidence_window() -> None:
    incident = _load_json(INCIDENT)

    bundle = build_evidence_bundle(incident, evidence_root=EVIDENCE_ROOT)

    for metric in bundle["metrics"]:
        if "points" not in metric:
            continue
        assert metric["points"]
        for point in metric["points"]:
            timestamp = point.get("timestamp") or point.get("ts")
            assert "2026-06-29T09:45:00Z" <= timestamp <= "2026-06-29T10:10:00Z"


def test_k8s_events_match_incident_entities() -> None:
    incident = _load_json(INCIDENT)

    bundle = build_evidence_bundle(incident, evidence_root=EVIDENCE_ROOT)

    assert {event["reason"] for event in bundle["k8s_events"]} == {
        "Unhealthy",
        "Killing",
        "BackOff",
        "CrashLoopBackOff",
    }
    for event in bundle["k8s_events"]:
        assert event["cluster"] == "eks-prod"
        assert event["namespace"] == "bookhub-prod"
        assert event["pod"] == "book-service-7d9f6c8d9f-abcd1"
        assert event["container"] == "book-service"


def test_missing_required_groups_sets_partial_quality(tmp_path: Path) -> None:
    incident = _load_json(INCIDENT)
    root = tmp_path / "evidence"
    (root / "metrics").mkdir(parents=True)
    (root / "logs").mkdir()
    (root / "k8s-events").mkdir()
    (root / "ownership").mkdir()
    (root / "logs" / "logs.json").write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-06-29T10:00:00Z",
                    "service": "book-service",
                    "message": "one useful line",
                }
            ]
        ),
        encoding="utf-8",
    )

    bundle = build_evidence_bundle(incident, evidence_root=root)

    assert bundle["context_quality"] == "PARTIAL"
    assert bundle["missing_context"] == ["metrics", "k8s_events", "ownership"]
    assert "traces" in bundle["optional_missing_context"]
    assert "recent_deploys" in bundle["optional_missing_context"]


def test_empty_core_evidence_sets_insufficient_quality(tmp_path: Path) -> None:
    incident = _load_json(INCIDENT)
    root = tmp_path / "evidence"
    root.mkdir()

    bundle = build_evidence_bundle(incident, evidence_root=root)

    assert bundle["context_quality"] == "INSUFFICIENT"
    assert bundle["missing_context"] == [
        "metrics",
        "logs",
        "k8s_events",
        "ownership",
    ]


def test_invalid_incident_fails_validation() -> None:
    incident = _load_json(INCIDENT)
    del incident["time_window"]["evidence_start"]

    with pytest.raises(EvidenceBuilderError):
        build_evidence_bundle(incident, evidence_root=EVIDENCE_ROOT)


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
