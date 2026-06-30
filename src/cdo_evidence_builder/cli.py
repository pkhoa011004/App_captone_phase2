"""CLI for building CDO evidence bundles locally."""

from __future__ import annotations

import argparse
import sys

from .builder import (
    EvidenceBuilderError,
    build_evidence_bundle,
    read_json_file,
    write_json_file,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build CDO evidence bundle locally")
    parser.add_argument("--incident", required=True, help="Correlator incident JSON path")
    parser.add_argument(
        "--evidence-root",
        required=True,
        help="Evidence root containing metrics/logs/traces/k8s-events/deploys/ownership",
    )
    parser.add_argument("--output", required=True, help="Output evidence_bundle.json path")
    parser.add_argument("--max-logs", type=int, default=50, help="Maximum log lines")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Reserved for future stricter validation; currently validates required inputs.",
    )
    args = parser.parse_args()

    try:
        incident = read_json_file(args.incident)
        bundle = build_evidence_bundle(
            incident,
            evidence_root=args.evidence_root,
            max_logs=args.max_logs,
        )
        write_json_file(args.output, bundle)
    except (FileNotFoundError, EvidenceBuilderError) as exc:
        print(f"evidence builder error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print("Evidence bundle generated:")
    print(f"- incident_id: {bundle['incident_id']}")
    print(f"- metrics: {len(bundle['metrics'])}")
    print(f"- logs: {len(bundle['logs'])}")
    print(f"- traces: {len(bundle['traces'])}")
    print(f"- k8s_events: {len(bundle['k8s_events'])}")
    print(f"- recent_deploys: {len(bundle['recent_deploys'])}")
    print(f"- context_quality: {bundle['context_quality']}")


if __name__ == "__main__":
    main()
