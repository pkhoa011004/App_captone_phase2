"""Same-service multi-signal correlation for local Phase 2 CDO runs."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import (
    CORRELATION_TYPE,
    CORRELATION_WINDOW_MINUTES,
    FORBIDDEN_RCA_FIELDS,
    GROUP_BY_FIELDS,
    NEXT_STEP_BUILD_EVIDENCE,
    REQUIRED_ALERT_FIELDS,
    SEVERITY_ORDER,
    STATUS_MULTIPLE_GROUPS_UNSUPPORTED,
    STATUS_NO_VALID_ALERTS,
    STATUS_OPEN,
    VALIDATION_STATUS_VALID,
)

JsonMap = dict[str, Any]
GroupKey = tuple[str, str, str, str, str, str]


class CorrelatorInputError(ValueError):
    """Raised when the CLI input cannot be read or parsed."""


def read_json_file(path: str | Path) -> Any:
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"input file does not exist: {input_path}")

    try:
        with input_path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise CorrelatorInputError(f"invalid JSON in {input_path}: {exc}") from exc


def write_json_file(path: str | Path, payload: Any) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")


def load_state(path: str | Path | None) -> JsonMap:
    if path is None:
        return {"open_incidents": {}}

    state_path = Path(path)
    if not state_path.exists():
        return {"open_incidents": {}}

    data = read_json_file(state_path)
    if not isinstance(data, dict):
        raise CorrelatorInputError(f"state file must contain a JSON object: {state_path}")

    open_incidents = data.get("open_incidents")
    if not isinstance(open_incidents, dict):
        data["open_incidents"] = {}

    return data


def correlate_payload(
    payload: Any,
    *,
    state: JsonMap | None = None,
) -> tuple[JsonMap, JsonMap]:
    """Correlate one same-service group and return output plus updated state."""

    wrappers = _coerce_wrappers(payload)
    current_state = deepcopy(state) if state is not None else {"open_incidents": {}}
    current_state.setdefault("open_incidents", {})

    valid_alerts, skipped_count = _extract_valid_alerts(wrappers)

    if not valid_alerts:
        return (
            {
                "status": STATUS_NO_VALID_ALERTS,
                "incident": None,
                "skipped_count": skipped_count,
            },
            current_state,
        )

    grouped: dict[GroupKey, list[JsonMap]] = {}
    for alert_context in valid_alerts:
        grouped.setdefault(alert_context["group_key"], []).append(alert_context)

    if len(grouped) > 1:
        return (
            {
                "status": STATUS_MULTIPLE_GROUPS_UNSUPPORTED,
                "incident": None,
                "group_keys": [
                    _group_key_to_output(group_key) for group_key in sorted(grouped)
                ],
                "skipped_count": skipped_count,
            },
            current_state,
        )

    group_key, group_alerts = next(iter(grouped.items()))
    incident = _load_or_create_incident(current_state, group_key)
    _merge_alerts_into_incident(incident, group_alerts)
    _assert_no_forbidden_fields(incident)
    _save_incident_to_state(current_state, group_key, incident, group_alerts)

    return incident, current_state


def _coerce_wrappers(payload: Any) -> list[JsonMap]:
    if isinstance(payload, list):
        wrappers = payload
    elif isinstance(payload, dict):
        wrappers = [payload]
    else:
        raise CorrelatorInputError("input must be a wrapper object or list of wrappers")

    return [wrapper for wrapper in wrappers if isinstance(wrapper, dict)]


def _extract_valid_alerts(wrappers: Sequence[JsonMap]) -> tuple[list[JsonMap], int]:
    valid_alerts: list[JsonMap] = []
    skipped_count = 0

    for wrapper in wrappers:
        validation = wrapper.get("validation")
        normalized_alert = wrapper.get("normalized_alert")

        if (
            not isinstance(validation, dict)
            or validation.get("status") not in (VALIDATION_STATUS_VALID, "VALID_WITH_WARNINGS")
            or not isinstance(normalized_alert, dict)
        ):
            skipped_count += 1
            continue

        if _missing_required_fields(normalized_alert):
            skipped_count += 1
            continue

        try:
            started_at = _parse_iso_z(str(normalized_alert["started_at"]))
        except ValueError:
            skipped_count += 1
            continue

        bucket_start = _bucket_start(started_at)
        valid_alerts.append(
            {
                "wrapper": wrapper,
                "alert": normalized_alert,
                "started_at": started_at,
                "bucket_start": bucket_start,
                "group_key": _group_key(normalized_alert, bucket_start),
            }
        )

    return valid_alerts, skipped_count


def _missing_required_fields(alert: Mapping[str, Any]) -> list[str]:
    return [field for field in REQUIRED_ALERT_FIELDS if _is_missing(alert.get(field))]


def _load_or_create_incident(state: JsonMap, group_key: GroupKey) -> JsonMap:
    state_key = _serialize_group_key(group_key)
    existing = state.get("open_incidents", {}).get(state_key)
    if isinstance(existing, dict):
        return {
            key: deepcopy(value)
            for key, value in existing.items()
            if key not in {"started_at", "updated_at"}
        }

    tenant_id, environment, cluster, namespace, service, bucket_id = group_key
    incident_id = (
        f"inc-{_id_part(tenant_id)}-{_id_part(environment)}-"
        f"{_id_part(service)}-{bucket_id}"
    )
    correlation_id = (
        f"corr-{_id_part(tenant_id)}-{_id_part(environment)}-"
        f"{_id_part(service)}-{bucket_id}"
    )

    return {
        "incident_id": incident_id,
        "correlation_id": correlation_id,
        "tenant_id": tenant_id,
        "environment": environment,
        "cluster": cluster,
        "namespace": namespace,
        "service": service,
        "severity": "info",
        "status": STATUS_OPEN,
        "correlation": {
            "type": CORRELATION_TYPE,
            "window_minutes": CORRELATION_WINDOW_MINUTES,
            "group_by": list(GROUP_BY_FIELDS),
            "reason": (
                "Multiple valid alerts for the same service occurred within "
                "the correlation window."
            ),
        },
        "alerts": [],
        "alert_ids": [],
        "deduped_alert_ids": [],
        "signals": [],
        "related_entities": {
            "pods": [],
            "deployments": [],
            "containers": [],
        },
        "time_window": {},
        "next_step": NEXT_STEP_BUILD_EVIDENCE,
    }


def _merge_alerts_into_incident(
    incident: JsonMap,
    alert_contexts: Iterable[JsonMap],
) -> None:
    existing_alert_ids = set(incident.get("alert_ids", []))
    existing_deduped_alert_ids = set(incident.get("deduped_alert_ids", []))
    dedup_keys = {
        _dedup_key_from_alert_summary(incident, alert_summary)
        for alert_summary in incident.get("alerts", [])
        if isinstance(alert_summary, dict)
    }

    for alert_context in sorted(
        alert_contexts,
        key=lambda item: (item["started_at"], str(item["alert"]["alert_id"])),
    ):
        alert = alert_context["alert"]
        alert_id = str(alert["alert_id"])
        if alert_id in existing_alert_ids or alert_id in existing_deduped_alert_ids:
            continue

        dedup_key = _dedup_key(alert, alert_context["bucket_start"])
        if dedup_key in dedup_keys:
            _append_unique(incident["deduped_alert_ids"], alert_id)
            existing_deduped_alert_ids.add(alert_id)
            continue

        alert_summary = _alert_summary(alert)
        incident["alerts"].append(alert_summary)
        _append_unique(incident["alert_ids"], alert_id)
        existing_alert_ids.add(alert_id)
        dedup_keys.add(dedup_key)

        for signal in _extract_signals(alert):
            _append_unique(incident["signals"], signal)

    _recalculate_incident_fields(incident)


def _recalculate_incident_fields(incident: JsonMap) -> None:
    alerts = incident.get("alerts", [])
    severities = [str(alert.get("severity", "info")) for alert in alerts]
    incident["severity"] = _highest_severity(severities)
    incident["related_entities"] = _related_entities(alerts)
    incident["time_window"] = _time_window(alerts)


def _alert_summary(alert: Mapping[str, Any]) -> JsonMap:
    return {
        "alert_id": alert["alert_id"],
        "source": alert["source"],
        "title": alert["title"],
        "severity": alert["severity"],
        "started_at": alert["started_at"],
        "labels": deepcopy(alert.get("labels", {})),
    }


def _extract_signals(alert: Mapping[str, Any]) -> list[str]:
    labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
    metric_names = labels.get("metric_names", [])
    if isinstance(metric_names, str):
        metric_text = metric_names
    elif isinstance(metric_names, list):
        metric_text = " ".join(str(metric) for metric in metric_names)
    else:
        metric_text = ""

    title = str(alert.get("title", ""))
    reason = str(labels.get("reason", ""))
    status_code = str(labels.get("status_code", ""))
    text = f"{title} {reason} {metric_text}".lower()

    signals: list[str] = []
    if "5xx" in text or status_code.startswith("5"):
        signals.append("http_5xx_high")
    if "latency" in text:
        signals.append("latency_high")
    if "healthcheck" in text or "blackbox" in text or "ping" in text:
        signals.append("healthcheck_failed")
    if "crashloop" in text:
        signals.append("pod_crashloop")
    if "restart" in text:
        signals.append("container_restart")
    if "timeout" in text:
        signals.append("timeout")
    if "oom" in text:
        signals.append("oom_killed")
    if "memory_usage_high" in text or "high memory" in text or "memory_usage_mb" in text:
        signals.append("memory_usage_high")
    if "throttle" in text:
        signals.append("cpu_throttled")
    elif "cpu" in text:
        signals.append("cpu_usage_high")

    return signals or ["unknown_signal"]


def _related_entities(alerts: Sequence[Mapping[str, Any]]) -> JsonMap:
    entities: JsonMap = {
        "pods": [],
        "deployments": [],
        "containers": [],
    }
    for alert in alerts:
        labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
        _append_unique(entities["pods"], labels.get("pod"))
        _append_unique(entities["deployments"], labels.get("deployment"))
        _append_unique(entities["containers"], labels.get("container"))
    return entities


def _time_window(alerts: Sequence[Mapping[str, Any]]) -> JsonMap:
    if not alerts:
        return {}

    starts = [_parse_iso_z(str(alert["started_at"])) for alert in alerts]
    alert_start = min(starts)
    alert_end = max(starts)
    return {
        "alert_start": _format_iso_z(alert_start),
        "alert_end": _format_iso_z(alert_end),
        "evidence_start": _format_iso_z(alert_start - timedelta(minutes=15)),
        "evidence_end": _format_iso_z(alert_end + timedelta(minutes=5)),
    }


def _save_incident_to_state(
    state: JsonMap,
    group_key: GroupKey,
    incident: JsonMap,
    alert_contexts: Sequence[JsonMap],
) -> None:
    state_key = _serialize_group_key(group_key)
    entry = deepcopy(incident)
    time_window = incident.get("time_window", {})
    entry["started_at"] = time_window.get("alert_start")
    entry["updated_at"] = _latest_received_at(alert_contexts)
    state.setdefault("open_incidents", {})[state_key] = entry


def _latest_received_at(alert_contexts: Sequence[JsonMap]) -> str:
    received_times: list[datetime] = []
    for alert_context in alert_contexts:
        received_at = alert_context.get("wrapper", {}).get("received_at")
        if not received_at:
            continue
        try:
            received_times.append(_parse_iso_z(str(received_at)))
        except ValueError:
            continue

    if received_times:
        return _format_iso_z(max(received_times))

    started_times = [alert_context["started_at"] for alert_context in alert_contexts]
    return _format_iso_z(max(started_times))


def _highest_severity(severities: Sequence[str]) -> str:
    if not severities:
        return "info"
    return max(severities, key=lambda severity: SEVERITY_ORDER.get(severity, -1))


def _group_key(alert: Mapping[str, Any], bucket_start: datetime) -> GroupKey:
    return (
        str(alert["tenant_id"]),
        str(alert["environment"]),
        str(alert["cluster"]),
        str(alert["namespace"]),
        str(alert["service"]),
        _bucket_id(bucket_start),
    )


def _group_key_to_output(group_key: GroupKey) -> JsonMap:
    tenant_id, environment, cluster, namespace, service, bucket_id = group_key
    return {
        "tenant_id": tenant_id,
        "environment": environment,
        "cluster": cluster,
        "namespace": namespace,
        "service": service,
        "time_bucket": bucket_id,
    }


def _dedup_key(alert: Mapping[str, Any], bucket_start: datetime) -> tuple[str, ...]:
    labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
    return (
        str(alert["tenant_id"]),
        str(alert["environment"]),
        str(alert["cluster"]),
        str(alert["namespace"]),
        str(alert["service"]),
        str(alert["title"]),
        str(labels.get("pod", "")),
        _bucket_id(bucket_start),
    )


def _dedup_key_from_alert_summary(
    incident: Mapping[str, Any],
    alert_summary: Mapping[str, Any],
) -> tuple[str, ...]:
    labels = (
        alert_summary.get("labels")
        if isinstance(alert_summary.get("labels"), dict)
        else {}
    )
    started_at = _parse_iso_z(str(alert_summary["started_at"]))
    return (
        str(incident["tenant_id"]),
        str(incident["environment"]),
        str(incident["cluster"]),
        str(incident["namespace"]),
        str(incident["service"]),
        str(alert_summary["title"]),
        str(labels.get("pod", "")),
        _bucket_id(_bucket_start(started_at)),
    )


def _serialize_group_key(group_key: GroupKey) -> str:
    return "|".join(group_key)


def _bucket_start(value: datetime) -> datetime:
    return value.replace(
        minute=(value.minute // CORRELATION_WINDOW_MINUTES)
        * CORRELATION_WINDOW_MINUTES,
        second=0,
        microsecond=0,
    )


def _bucket_id(value: datetime) -> str:
    return value.strftime("%Y%m%d%H%M")


def _parse_iso_z(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_iso_z(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _append_unique(values: list[Any], value: Any) -> None:
    if _is_missing(value):
        return
    if value not in values:
        values.append(value)


def _id_part(value: str) -> str:
    sanitized = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    return sanitized or "unknown"


def _is_missing(value: Any) -> bool:
    return value is None or value == ""


def _assert_no_forbidden_fields(incident: Mapping[str, Any]) -> None:
    for field in FORBIDDEN_RCA_FIELDS:
        if field in incident:
            raise AssertionError(f"correlator must not emit RCA field: {field}")
