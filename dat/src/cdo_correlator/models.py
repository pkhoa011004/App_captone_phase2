"""Shared constants for the Phase 2 same-service correlator."""

from __future__ import annotations

CORRELATION_TYPE = "same_service_multi_signal"
CORRELATION_WINDOW_MINUTES = 10
NEXT_STEP_BUILD_EVIDENCE = "BUILD_EVIDENCE"

VALIDATION_STATUS_VALID = "VALID"

STATUS_OPEN = "OPEN"
STATUS_NO_VALID_ALERTS = "NO_VALID_ALERTS"
STATUS_MULTIPLE_GROUPS_UNSUPPORTED = "MULTIPLE_GROUPS_UNSUPPORTED"

GROUP_BY_FIELDS = (
    "tenant_id",
    "environment",
    "cluster",
    "namespace",
    "service",
)

REQUIRED_ALERT_FIELDS = (
    "alert_id",
    "tenant_id",
    "environment",
    "cluster",
    "namespace",
    "source",
    "service",
    "severity",
    "title",
    "started_at",
)

SEVERITY_ORDER = {
    "info": 0,
    "warning": 1,
    "critical": 2,
}

FORBIDDEN_RCA_FIELDS = (
    "suspected_root_cause",
    "confidence",
    "recommended_actions",
    "ticket_payload",
)
