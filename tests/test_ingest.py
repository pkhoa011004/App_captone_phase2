from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from cdo_ingest.handler import lambda_handler
from cdo_ingest.ingest import ingest_alert, ingest_payload, load_service_catalog

ROOT = Path(__file__).resolve().parents[1]
PHASE1_DATA = ROOT / "data" / "fake" / "phase1-ingest"
ALERTS = PHASE1_DATA / "alerts"
EXPECTED = PHASE1_DATA / "expected-output"
SERVICE_CATALOG = ROOT / "data" / "shared" / "service-catalog" / "service-catalog.yaml"
RECEIVED_AT = "2026-06-29T10:01:00Z"


def test_case_01_complete_alert_is_valid() -> None:
    alert = _load_json(ALERTS / "case-01-complete-alert.json")
    expected = _load_json(EXPECTED / "expected-normalized-alert.json")

    result = ingest_alert(
        alert,
        received_at=RECEIVED_AT,
        ingest_id="ingest-20260629-100001",
    )

    assert result == expected


def test_case_01_book_service_multisignal_flat_is_valid() -> None:
    alert = _load_json(ALERTS / "case-01-book-service-multisignal-flat.json")
    expected = _load_json(
        EXPECTED / "expected-book-service-multisignal-flat-normalized-alert.json"
    )

    result = ingest_alert(
        alert,
        received_at=RECEIVED_AT,
        ingest_id="ingest-20260629-100006",
    )

    normalized_alert = result["normalized_alert"]
    assert result == expected
    assert normalized_alert["tenant_id"] == "tenant-a"
    assert normalized_alert["environment"] == "prod"
    assert normalized_alert["cluster"] == "eks-prod"
    assert normalized_alert["namespace"] == "bookhub-prod"
    assert set(normalized_alert["labels"]) == {
        "pod",
        "deployment",
        "container",
        "metric_names",
        "trace_id",
        "status_code",
        "reason",
        "runbook_url",
        "jira_project",
        "jira_component",
    }
    assert "incident_id" not in result
    assert "correlation_id" not in result


def test_case_02_missing_required_metadata_is_invalid() -> None:
    alert = _load_json(ALERTS / "case-02-missing-metadata-alert.json")
    expected = _load_json(EXPECTED / "expected-invalid-alert.json")

    result = ingest_alert(
        alert,
        received_at=RECEIVED_AT,
        ingest_id="ingest-20260629-100002",
    )

    assert result == expected


def test_top_level_tenant_environment_take_precedence_over_labels() -> None:
    alert = _load_json(ALERTS / "case-01-complete-alert.json")
    alert["tenant_id"] = "tenant-top"
    alert["environment"] = "staging"
    alert["cluster"] = "eks-staging"
    alert["namespace"] = "bookhub-staging"

    result = ingest_alert(alert, received_at=RECEIVED_AT)
    normalized_alert = result["normalized_alert"]

    assert result["validation"]["status"] == "VALID"
    assert normalized_alert["tenant_id"] == "tenant-top"
    assert normalized_alert["environment"] == "staging"
    assert normalized_alert["cluster"] == "eks-staging"
    assert normalized_alert["namespace"] == "bookhub-staging"
    for promoted_field in ("tenant_id", "environment", "cluster", "namespace"):
        assert promoted_field not in normalized_alert["labels"]


def test_missing_cluster_namespace_is_rejected() -> None:
    alert = _load_json(ALERTS / "case-01-complete-alert.json")
    alert["labels"].pop("cluster")
    alert["labels"].pop("namespace")

    result = ingest_alert(alert, received_at=RECEIVED_AT)

    assert result["validation"]["status"] == "INVALID_ALERT"
    assert result["validation"]["missing_fields"] == ["cluster", "namespace"]
    assert result["normalized_alert"] is None


def test_invalid_environment_is_rejected() -> None:
    alert = _load_json(ALERTS / "case-01-complete-alert.json")
    alert["labels"]["environment"] = "dev"

    result = ingest_alert(alert, received_at=RECEIVED_AT)

    assert result["validation"]["status"] == "INVALID_ALERT"
    assert result["validation"]["missing_fields"] == ["environment"]
    assert result["normalized_alert"] is None


def test_missing_optional_without_catalog_returns_warning() -> None:
    alert = _warning_alert()
    expected = _load_json(EXPECTED / "expected-warning-alert.json")

    result = ingest_alert(
        alert,
        service_catalog={},
        received_at=RECEIVED_AT,
        ingest_id="ingest-20260629-100003",
    )

    assert result == expected


def test_missing_optional_catalog_fields_are_enriched() -> None:
    alert = _load_json(ALERTS / "case-01-complete-alert.json")
    expected = _load_json(EXPECTED / "expected-enriched-alert.json")
    service_catalog = load_service_catalog(SERVICE_CATALOG)

    for field in ("jira_project", "jira_component", "runbook_url"):
        alert["labels"].pop(field)

    result = ingest_alert(
        alert,
        service_catalog=service_catalog,
        received_at=RECEIVED_AT,
        ingest_id="ingest-20260629-100004",
    )

    assert result == expected


def test_case_03_duplicate_alerts_are_not_deduplicated() -> None:
    alerts = _load_json(ALERTS / "case-03-duplicate-alerts.json")

    result = ingest_payload(alerts, received_at=RECEIVED_AT)

    assert isinstance(result, list)
    assert len(result) == 2
    assert [item["validation"]["status"] for item in result] == ["VALID", "VALID"]
    assert [
        item["normalized_alert"]["alert_id"] for item in result
    ] == [
        "alert-book-service-5xx-001",
        "alert-book-service-5xx-001-duplicate",
    ]


def test_case_04_impact_alerts_are_not_grouped() -> None:
    alerts = _load_json(ALERTS / "case-04-impact-alerts.json")

    result = ingest_payload(alerts, received_at=RECEIVED_AT)

    assert isinstance(result, list)
    assert len(result) == 3
    assert {item["validation"]["status"] for item in result} == {"VALID"}
    assert all("incident_id" not in item for item in result)
    assert all("correlation_id" not in item for item in result)
    assert [
        item["normalized_alert"]["service"] for item in result
    ] == [
        "book-service",
        "order-service",
        "frontend",
    ]


def test_case_05_preserves_deploy_labels() -> None:
    alert = _load_json(ALERTS / "case-05-recent-deploy-alert.json")

    result = ingest_alert(alert, received_at=RECEIVED_AT)

    labels = result["normalized_alert"]["labels"]
    assert result["validation"]["status"] == "VALID"
    assert labels["image_digest"] == "sha256:new-bad-version"
    assert labels["git_sha"] == "a1b2c3d"
    assert labels["deployment_version"] == "v2"


def test_lambda_handler_accepts_api_gateway_body() -> None:
    alert = _load_json(ALERTS / "case-01-complete-alert.json")

    result = lambda_handler({"body": json.dumps(alert)}, None)

    assert result["validation"]["status"] == "VALID"
    assert result["normalized_alert"]["alert_id"] == "alert-book-service-5xx-001"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _warning_alert() -> dict:
    alert = deepcopy(_load_json(ALERTS / "case-01-complete-alert.json"))
    alert["labels"] = {
        "tenant_id": "tenant-a",
        "environment": "prod",
        "cluster": "eks-prod",
        "namespace": "bookhub-prod",
    }
    return alert
