"""CDO Phase 1 ingest package."""

from .ingest import ingest_alert, ingest_payload, load_service_catalog

__all__ = ["ingest_alert", "ingest_payload", "load_service_catalog"]
