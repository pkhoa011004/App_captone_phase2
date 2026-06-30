"""CLI for the Phase 2 same-service correlator."""

from __future__ import annotations

import argparse
import sys

from .correlate import (
    CorrelatorInputError,
    correlate_payload,
    load_state,
    read_json_file,
    write_json_file,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CDO Phase 2 correlator locally")
    parser.add_argument("--input", required=True, help="Ingest wrapper JSON file")
    parser.add_argument(
        "--state",
        default="outputs/phase2-correlator/state/open-incidents.json",
        help="Local open incident state JSON file",
    )
    parser.add_argument(
        "--output",
        default="outputs/phase2-correlator/incident.json",
        help="Incident output JSON file",
    )
    args = parser.parse_args()

    try:
        payload = read_json_file(args.input)
        state = load_state(args.state)
        output, updated_state = correlate_payload(payload, state=state)
        write_json_file(args.output, output)
        write_json_file(args.state, updated_state)
    except (FileNotFoundError, CorrelatorInputError) as exc:
        print(f"correlator error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"{args.input} -> {args.output}")
    print(f"state -> {args.state}")


if __name__ == "__main__":
    main()
