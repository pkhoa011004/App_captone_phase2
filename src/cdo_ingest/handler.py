"""AWS Lambda-compatible entrypoint for CDO Phase 1 ingest."""

from __future__ import annotations

import json
import os
from typing import Any

from .ingest import ingest_payload, load_service_catalog


def lambda_handler(event: Any, context: Any) -> Any:
    payload = _extract_payload(event)
    service_catalog = load_service_catalog(os.getenv("SERVICE_CATALOG_PATH"))
    return ingest_payload(payload, service_catalog=service_catalog)


def _extract_payload(event: Any) -> Any:
    if isinstance(event, dict) and "body" in event:
        body = event["body"]
        if isinstance(body, str):
            return json.loads(body)
        return body

    if isinstance(event, dict) and "Records" in event:
        payloads = []
        for record in event["Records"]:
            body = record.get("body", record)
            payloads.append(json.loads(body) if isinstance(body, str) else body)
        return payloads

    return event
