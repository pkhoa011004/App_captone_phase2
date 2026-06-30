"""CDO Phase 2 same-service correlator package."""

from .correlate import correlate_payload, load_state, read_json_file, write_json_file

__all__ = ["correlate_payload", "load_state", "read_json_file", "write_json_file"]
