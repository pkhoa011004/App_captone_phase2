"""Shared constants for the Evidence Builder."""

from __future__ import annotations

SCHEMA_VERSION = "cdo.evidence.v1"

REQUIRED_INCIDENT_FIELDS = (
    "incident_id",
    "correlation_id",
    "tenant_id",
    "environment",
    "cluster",
    "namespace",
    "service",
    "signals",
    "related_entities",
    "time_window",
)

REQUIRED_CONTEXT_GROUPS = (
    "metrics",
    "logs",
    "k8s_events",
    "ownership",
)

OPTIONAL_CONTEXT_GROUPS = (
    "traces",
    "recent_deploys",
)

FORBIDDEN_RCA_FIELDS = (
    "suspected_root_cause",
    "confidence",
    "recommended_actions",
    "ticket_payload",
)
