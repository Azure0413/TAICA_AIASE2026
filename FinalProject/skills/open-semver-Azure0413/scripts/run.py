#!/usr/bin/env python3
"""
open-semver-advisor skill — final output wrapper (FILE-BASED output contract).

Reads a JSON payload from argv[1] with {task_id, bump, changelog, rationale, confidence},
enforces the deterministic output shape, and **atomically writes** a contract-conformant
result to the agreed result file (course 2026-06 file-based update). Failure still produces
a contract-conformant JSON (spec §1.4 #7); confidence is always a finite number in [0,1].

Result path = $AIASE_RESULT_PATH, else ./aiase_result.json (cwd). Self-contained: we do NOT
`import aiase_contract` (not importable once the skill is installed standalone).
"""

from __future__ import annotations

import json
import math
import os
import sys

ALLOWED_BUMPS = {"major", "minor", "patch"}


def resolve_result_path() -> str:
    """Result file path: $AIASE_RESULT_PATH, else ./aiase_result.json in cwd.

    Kept identical to aiase_contract.resolve_result_path (the grader's reader)."""
    return os.environ.get("AIASE_RESULT_PATH") or os.path.join(os.getcwd(), "aiase_result.json")


def _clamp_confidence(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(f):   # reject NaN / Infinity (spec §1.4 #2 forbids them in the JSON)
        return 0.0
    return max(0.0, min(1.0, f))


def emit_contract(obj: dict) -> int:
    bump = str(obj.get("bump", "")).strip().lower()
    if bump not in ALLOWED_BUMPS:
        bump = ""  # leave invalid for the grader rather than guessing
    out = {
        "task_id": str(obj.get("task_id", "")),
        "bump": bump,
        "changelog": str(obj.get("changelog", "")),
        "rationale": str(obj.get("rationale", "")),
        "confidence": _clamp_confidence(obj.get("confidence", 0.5)),
    }
    path = resolve_result_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, path)  # atomic
    print(f"written ok -> {path}")
    return 0


def loads_lenient(s: str):
    """json.loads, with one fallback for the most common LLM glitch: an invalid `\\'` escape
    (JSON does not allow escaping a single quote). Returns a dict or raises."""
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return json.loads(s.replace("\\'", "'"))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return emit_contract({"task_id": "", "bump": "", "changelog": "",
                              "rationale": "run.py invoked without argv payload", "confidence": 0.0})
    try:
        payload = loads_lenient(argv[1])
        if not isinstance(payload, dict):
            raise ValueError("payload not an object")
    except (json.JSONDecodeError, ValueError) as e:
        return emit_contract({"task_id": "", "bump": "", "changelog": "",
                              "rationale": f"invalid argv JSON: {e}", "confidence": 0.0})
    return emit_contract(payload)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
