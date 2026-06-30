from __future__ import annotations

import copy
import json
from pathlib import Path

from cdo_correlator.correlate import correlate_payload
from cdo_correlator.models import (
    FORBIDDEN_RCA_FIELDS,
    STATUS_MULTIPLE_GROUPS_UNSUPPORTED,
    STATUS_NO_VALID_ALERTS,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "fake" / "phase2-correlator" / "input"


def test_single_valid_alert_creates_incident() -> None:
    payload = [_load_wrappers()[0]]

    output, state = correlate_payload(payload)

    assert output["status"] == "OPEN"
    assert output["service"] == "book-service"
    assert output["next_step"] == "BUILD_EVIDENCE"
    assert output["incident_id"] == "inc-tenant-a-prod-book-service-202606291000"
    assert output["correlation_id"] == "corr-tenant-a-prod-book-service-202606291000"
    assert output["alert_ids"] == ["alert-book-service-5xx-001"]
    assert output["signals"] == ["http_5xx_high"]
    assert len(state["open_incidents"]) == 1


def test_invalid_alert_returns_no_valid_alerts() -> None:
    wrapper = copy.deepcopy(_load_wrappers()[0])
    wrapper["validation"]["status"] = "INVALID_ALERT"
    wrapper["normalized_alert"] = None

    output, state = correlate_payload(wrapper)

    assert output == {
        "status": STATUS_NO_VALID_ALERTS,
        "incident": None,
        "skipped_count": 1,
    }
    assert state == {"open_incidents": {}}


def test_duplicate_alert_is_deduped() -> None:
    first = _load_wrappers()[0]
    duplicate = copy.deepcopy(first)
    duplicate["ingest_id"] = "ingest-20260629-100100-9999"
    duplicate["normalized_alert"]["alert_id"] = "alert-book-service-5xx-duplicate-001"
    duplicate["received_at"] = "2026-06-29T10:02:00Z"

    output, _state = correlate_payload([first, duplicate])

    assert output["alert_ids"] == ["alert-book-service-5xx-001"]
    assert output["deduped_alert_ids"] == ["alert-book-service-5xx-duplicate-001"]
    assert output["signals"] == ["http_5xx_high"]
    assert len(output["alerts"]) == 1


def test_multi_signal_same_service_alerts_create_one_incident() -> None:
    output, _state = correlate_payload(_load_wrappers())

    assert output["correlation"]["type"] == "same_service_multi_signal"
    assert output["severity"] == "critical"
    assert output["alert_ids"] == [
        "alert-book-service-5xx-001",
        "alert-book-service-latency-001",
        "alert-book-service-healthcheck-001",
        "alert-book-service-crashloop-001",
        "alert-book-service-restart-001",
    ]
    assert output["signals"] == [
        "http_5xx_high",
        "latency_high",
        "healthcheck_failed",
        "pod_crashloop",
        "container_restart",
    ]
    assert output["related_entities"] == {
        "pods": ["book-service-7d9f6c8d9f-abcd1"],
        "deployments": ["book-service"],
        "containers": ["book-service"],
    }
    assert output["time_window"] == {
        "alert_start": "2026-06-29T10:00:00Z",
        "alert_end": "2026-06-29T10:05:00Z",
        "evidence_start": "2026-06-29T09:45:00Z",
        "evidence_end": "2026-06-29T10:10:00Z",
    }
    for field in FORBIDDEN_RCA_FIELDS:
        assert field not in output


def test_multiple_groups_are_unsupported_for_mvp() -> None:
    wrappers = _load_wrappers()[:2]
    other_group = copy.deepcopy(wrappers[1])
    other_group["normalized_alert"]["service"] = "order-service"
    other_group["normalized_alert"]["alert_id"] = "alert-order-service-latency-001"

    output, _state = correlate_payload([wrappers[0], other_group])

    assert output["status"] == STATUS_MULTIPLE_GROUPS_UNSUPPORTED
    assert output["incident"] is None
    assert output["group_keys"] == [
        {
            "tenant_id": "tenant-a",
            "environment": "prod",
            "cluster": "eks-prod",
            "namespace": "bookhub-prod",
            "service": "book-service",
            "time_bucket": "202606291000",
        },
        {
            "tenant_id": "tenant-a",
            "environment": "prod",
            "cluster": "eks-prod",
            "namespace": "bookhub-prod",
            "service": "order-service",
            "time_bucket": "202606291000",
        },
    ]


def test_existing_open_incident_is_updated_from_state() -> None:
    wrappers = _load_wrappers()
    first_output, state = correlate_payload(wrappers[:2])

    second_output, updated_state = correlate_payload(wrappers[2:], state=state)

    assert second_output["incident_id"] == first_output["incident_id"]
    assert second_output["correlation_id"] == first_output["correlation_id"]
    assert second_output["alert_ids"] == [
        "alert-book-service-5xx-001",
        "alert-book-service-latency-001",
        "alert-book-service-healthcheck-001",
        "alert-book-service-crashloop-001",
        "alert-book-service-restart-001",
    ]
    assert second_output["signals"] == [
        "http_5xx_high",
        "latency_high",
        "healthcheck_failed",
        "pod_crashloop",
        "container_restart",
    ]
    state_entry = next(iter(updated_state["open_incidents"].values()))
    assert state_entry["updated_at"] == "2026-06-29T10:06:00Z"


def _load_wrappers() -> list[dict]:
    path = FIXTURES / "case-01-book-service-multisignal-normalized-wrappers.json"
    return json.loads(path.read_text(encoding="utf-8"))
