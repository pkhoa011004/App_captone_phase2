"""Validate, normalize, and lightly enrich raw CDO alerts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .models import (
    ALLOWED_ENVIRONMENTS,
    CATALOG_ENRICHABLE_LABELS,
    ENRICHMENT_ENRICHED,
    ENRICHMENT_NOT_AVAILABLE,
    ENRICHMENT_NOT_NEEDED,
    REQUIRED_FIELDS,
    SCHEMA_VERSION,
    STATUS_INVALID_ALERT,
    STATUS_VALID,
    STATUS_VALID_WITH_WARNINGS,
    WARNING_OPTIONAL_LABELS,
)

JsonMap = dict[str, Any]
ServiceCatalog = Mapping[str, Mapping[str, Any]]


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_ingest_id(received_at: str | None = None, sequence: int | None = None) -> str:
    timestamp = received_at or utc_now_iso()
    compact = (
        timestamp.replace("-", "")
        .replace(":", "")
        .replace("T", "-")
        .replace("Z", "")
        .split(".")[0]
    )
    ingest_id = f"ingest-{compact}"
    if sequence is not None:
        ingest_id = f"{ingest_id}-{sequence:04d}"
    return ingest_id


def load_service_catalog(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}

    catalog_path = Path(path)
    if not catalog_path.exists():
        raise FileNotFoundError(f"service catalog not found: {catalog_path}")

    with catalog_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    if not isinstance(data, dict):
        raise ValueError("service catalog must be a mapping of service name to metadata")

    return {
        str(service): metadata
        for service, metadata in data.items()
        if isinstance(metadata, dict)
    }


def ingest_payload(
    payload: JsonMap | Sequence[JsonMap],
    *,
    service_catalog: ServiceCatalog | None = None,
    received_at: str | None = None,
    ingest_id: str | None = None,
) -> JsonMap | list[JsonMap]:
    """Process one alert object or a list of alert objects."""

    if isinstance(payload, list):
        return [
            ingest_alert(
                alert,
                service_catalog=service_catalog,
                received_at=received_at,
                ingest_id=None if ingest_id is None else f"{ingest_id}-{index + 1:04d}",
                sequence=index + 1 if ingest_id is None else None,
            )
            for index, alert in enumerate(payload)
        ]

    return ingest_alert(
        payload,
        service_catalog=service_catalog,
        received_at=received_at,
        ingest_id=ingest_id,
    )


def ingest_alert(
    raw_alert: JsonMap,
    *,
    service_catalog: ServiceCatalog | None = None,
    received_at: str | None = None,
    ingest_id: str | None = None,
    sequence: int | None = None,
) -> JsonMap:
    """Validate and normalize one raw alert according to the Phase 1 spec."""

    effective_received_at = received_at or utc_now_iso()
    effective_ingest_id = ingest_id or make_ingest_id(effective_received_at, sequence)
    labels = raw_alert.get("labels")
    label_map = labels if isinstance(labels, dict) else {}
    tenant_id = _resolve_alert_field(raw_alert, label_map, "tenant_id")
    environment = _resolve_alert_field(raw_alert, label_map, "environment")
    cluster = _resolve_alert_field(raw_alert, label_map, "cluster")
    namespace = _resolve_alert_field(raw_alert, label_map, "namespace")

    missing_fields = _missing_required_fields(
        raw_alert,
        tenant_id=tenant_id,
        environment=environment,
        cluster=cluster,
        namespace=namespace,
    )
    raw_source = raw_alert.get("source")

    if missing_fields:
        return {
            "ingest_id": effective_ingest_id,
            "schema_version": SCHEMA_VERSION,
            "received_at": effective_received_at,
            "raw_source": raw_source,
            "normalized_alert": None,
            "validation": {
                "status": STATUS_INVALID_ALERT,
                "missing_fields": missing_fields,
                "missing_optional_fields": [],
            },
        }

    normalized_labels = deepcopy(label_map)
    for promoted_field in ("tenant_id", "environment", "cluster", "namespace"):
        normalized_labels.pop(promoted_field, None)
    enriched_fields = _enrich_labels(
        normalized_labels,
        service=str(raw_alert["service"]),
        service_catalog=service_catalog or {},
    )

    missing_optional_fields = _missing_warning_optional_fields(normalized_labels)
    validation_status = (
        STATUS_VALID_WITH_WARNINGS if missing_optional_fields else STATUS_VALID
    )

    return {
        "ingest_id": effective_ingest_id,
        "schema_version": SCHEMA_VERSION,
        "received_at": effective_received_at,
        "raw_source": raw_source,
        "normalized_alert": _normalize_alert(
            raw_alert,
            tenant_id=tenant_id,
            environment=environment,
            cluster=cluster,
            namespace=namespace,
            labels=normalized_labels,
        ),
        "validation": {
            "status": validation_status,
            "missing_fields": [],
            "missing_optional_fields": missing_optional_fields,
        },
        "enrichment": _enrichment_result(enriched_fields, missing_optional_fields),
    }


def read_alert_file(path: str | Path) -> JsonMap | list[JsonMap]:
    with Path(path).open(encoding="utf-8") as fh:
        payload = json.load(fh)

    if not isinstance(payload, (dict, list)):
        raise ValueError(f"alert payload must be an object or list: {path}")

    return payload


def write_json(path: str | Path, payload: Any) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")


def _missing_required_fields(
    raw_alert: JsonMap,
    *,
    tenant_id: Any,
    environment: Any,
    cluster: Any,
    namespace: Any,
) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_FIELDS:
        if field == "tenant_id":
            if _is_missing(tenant_id):
                missing.append(field)
        elif field == "environment":
            if _is_missing(environment):
                missing.append(field)
        elif field == "cluster":
            if _is_missing(cluster):
                missing.append(field)
        elif field == "namespace":
            if _is_missing(namespace):
                missing.append(field)
        elif _is_missing(raw_alert.get(field)):
            missing.append(field)

    if "environment" not in missing and environment not in ALLOWED_ENVIRONMENTS:
        missing.append("environment")

    return missing


def _missing_warning_optional_fields(labels: Mapping[str, Any]) -> list[str]:
    return [
        f"labels.{label}"
        for label in WARNING_OPTIONAL_LABELS
        if _is_missing(labels.get(label))
    ]


def _enrich_labels(
    labels: JsonMap,
    *,
    service: str,
    service_catalog: ServiceCatalog,
) -> list[str]:
    service_metadata = service_catalog.get(service) or {}
    enriched_fields: list[str] = []

    for field in CATALOG_ENRICHABLE_LABELS:
        if not _is_missing(labels.get(field)):
            continue
        catalog_value = service_metadata.get(field)
        if _is_missing(catalog_value):
            continue
        labels[field] = deepcopy(catalog_value)
        enriched_fields.append(field)

    return enriched_fields


def _normalize_alert(
    raw_alert: JsonMap,
    *,
    tenant_id: Any,
    environment: Any,
    cluster: Any,
    namespace: Any,
    labels: JsonMap,
) -> JsonMap:
    normalized: JsonMap = {
        "alert_id": raw_alert["alert_id"],
        "tenant_id": tenant_id,
        "environment": environment,
        "cluster": cluster,
        "namespace": namespace,
        "source": raw_alert["source"],
        "service": raw_alert["service"],
        "severity": raw_alert["severity"],
        "title": raw_alert["title"],
    }

    if not _is_missing(raw_alert.get("description")):
        normalized["description"] = raw_alert["description"]

    normalized["started_at"] = raw_alert["started_at"]
    normalized["labels"] = labels

    return normalized


def _resolve_alert_field(
    raw_alert: Mapping[str, Any],
    labels: Mapping[str, Any],
    field: str,
) -> Any:
    raw_value = raw_alert.get(field)
    if not _is_missing(raw_value):
        return raw_value
    return labels.get(field)


def _enrichment_result(
    enriched_fields: Sequence[str],
    missing_optional_fields: Sequence[str],
) -> JsonMap:
    if enriched_fields:
        return {
            "status": ENRICHMENT_ENRICHED,
            "source": "service-catalog",
            "enriched_fields": list(enriched_fields),
        }

    if missing_optional_fields:
        return {
            "status": ENRICHMENT_NOT_AVAILABLE,
            "source": "service-catalog",
            "enriched_fields": [],
        }

    return {
        "status": ENRICHMENT_NOT_NEEDED,
        "source": None,
        "enriched_fields": [],
    }


def _is_missing(value: Any) -> bool:
    return value is None or value == ""
