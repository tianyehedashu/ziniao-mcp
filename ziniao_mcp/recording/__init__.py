"""Codegen-style recording: IR, emitters, and DOM2 capture (binding + buffer)."""

from .buffer import RecordingBuffer
from .ir import RECORDING_SCHEMA_VERSION, actions_for_disk, compute_delay_ms, parse_emit, redact_actions_secrets
from .locator import build_locator_dict, locator_to_css_selector, normalize_action_for_replay

__all__ = [
    "RECORDING_SCHEMA_VERSION",
    "RecordingBuffer",
    "actions_for_disk",
    "build_locator_dict",
    "compute_delay_ms",
    "locator_to_css_selector",
    "normalize_action_for_replay",
    "parse_emit",
    "redact_actions_secrets",
]
