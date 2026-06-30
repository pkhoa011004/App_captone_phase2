"""Local CLI for running Phase 1 ingest against fake alert JSON files."""

from __future__ import annotations

import argparse
from pathlib import Path

from .ingest import ingest_payload, load_service_catalog, read_alert_file, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CDO Phase 1 ingest locally")
    parser.add_argument(
        "--input",
        required=True,
        help="Alert JSON file or directory containing .json alert files",
    )
    parser.add_argument(
        "--output",
        default="outputs/phase1-ingest/normalized-alerts",
        help="Output directory for normalized alert JSON",
    )
    parser.add_argument(
        "--service-catalog",
        default=None,
        help="Optional service catalog YAML path for enrichment",
    )
    parser.add_argument(
        "--received-at",
        default=None,
        help="Override received_at timestamp for deterministic local output",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)
    service_catalog = load_service_catalog(args.service_catalog)

    input_files = (
        sorted(input_path.glob("*.json")) if input_path.is_dir() else [input_path]
    )

    for alert_file in input_files:
        payload = read_alert_file(alert_file)
        result = ingest_payload(
            payload,
            service_catalog=service_catalog,
            received_at=args.received_at,
        )
        output_path = output_dir / _output_name(alert_file)
        write_json(output_path, result)
        print(f"{alert_file} -> {output_path}")


def _output_name(alert_file: Path) -> str:
    stem = alert_file.stem
    if stem.endswith("-alert"):
        stem = stem.removesuffix("-alert")
    elif stem.endswith("-alerts"):
        stem = stem.removesuffix("-alerts")
    return f"{stem}-normalized-alert.json"


if __name__ == "__main__":
    main()
