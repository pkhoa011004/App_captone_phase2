"""Shared CDO ingest contract constants."""

from __future__ import annotations

SCHEMA_VERSION = "cdo.alert.v1"

REQUIRED_FIELDS = (
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

ALLOWED_ENVIRONMENTS = {"prod", "staging", "sandbox"}

OPTIONAL_LABELS = (
    "pod",
    "deployment",
    "container",
    "metric_names",
    "trace_id",
    "status_code",
    "reason",
    "suspected_dependency",
    "jira_project",
    "jira_component",
    "runbook_url",
    "region",
    "image_digest",
    "git_sha",
    "deployment_version",
)

# Phase 1 warns only for optional context the next stage normally benefits from.
# Deploy-specific labels are preserved when present, but are not required on all alerts.
WARNING_OPTIONAL_LABELS = (
    "trace_id",
    "metric_names",
    "runbook_url",
    "jira_project",
)

CATALOG_ENRICHABLE_LABELS = (
    "jira_project",
    "jira_component",
    "runbook_url",
)

STATUS_VALID = "VALID"
STATUS_VALID_WITH_WARNINGS = "VALID_WITH_WARNINGS"
STATUS_INVALID_ALERT = "INVALID_ALERT"

ENRICHMENT_ENRICHED = "ENRICHED"
ENRICHMENT_NOT_AVAILABLE = "NOT_AVAILABLE"
ENRICHMENT_NOT_NEEDED = "NOT_NEEDED"
