#!/usr/bin/env python3
"""
code-author skill — final output wrapper (FILE-BASED output contract).

Reads JSON from argv[1] (or stdin) with the fields needed by the contract, validates
shape, and **atomically writes** the Pairwise Code Author result to the agreed result
file. The grader reads that file — it no longer scrapes a fenced JSON block from the
conversation (course 2026-06 file-based update).

Result path = $AIASE_RESULT_PATH, else ./aiase_result.json (cwd). Self-contained: we do
NOT `import aiase_contract` (not importable once the skill is installed standalone).
"""

from __future__ import annotations

import json
import math
import os
import sys


def resolve_result_path() -> str:
    """Result file path: $AIASE_RESULT_PATH, else ./aiase_result.json in cwd.

    Must stay identical to aiase_contract.resolve_result_path (the grader's reader)."""
    return os.environ.get("AIASE_RESULT_PATH") or os.path.join(os.getcwd(), "aiase_result.json")


def write_result(out: dict) -> int:
    """Atomically write the result JSON so the grader never reads a half-written file."""
    path = resolve_result_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, path)  # atomic
    print(f"written ok -> {path}")
    return 0


def _clamp_confidence(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(f):   # reject NaN / Infinity (spec §1.4 #2 forbids them in the JSON)
        return 0.0
    return max(0.0, min(1.0, f))


def emit_contract(obj: dict) -> int:
    self_test = obj.get("self_test_results") or {}
    if not isinstance(self_test, dict):
        self_test = {"passed": 0, "failed": 0, "_warning": "non-object coerced"}
    self_test.setdefault("passed", 0)
    self_test.setdefault("failed", 0)

    out = {
        "task_id": str(obj.get("task_id", "")),
        "code": str(obj.get("code", "")),
        "loc": int(obj.get("loc", 0)) if str(obj.get("loc", "0")).lstrip("-").isdigit() else 0,
        "self_test_results": self_test,
        "rationale": str(obj.get("rationale", "")),
        "confidence": _clamp_confidence(obj.get("confidence", 0.5)),
    }
    return write_result(out)


def _raw_payload(argv: list[str]) -> str:
    """argv[1], or stdin when argv is absent/'-'. Python code often contains quotes, which
    collide with a single-quoted shell argv; a quoted heredoc (`python run.py <<'JSON' ... JSON`)
    is escaping-free. isatty()-guarded so it never blocks on an interactive terminal."""
    if len(argv) >= 2 and argv[1] != "-":
        return argv[1]
    try:
        if not sys.stdin.isatty():
            return sys.stdin.read()
    except (OSError, ValueError):
        pass
    return ""


def main(argv: list[str]) -> int:
    raw = _raw_payload(argv)
    if not raw.strip():
        return emit_contract({
            "task_id": "", "code": "", "loc": 0,
            "self_test_results": {"passed": 0, "failed": 0},
            "rationale": "run.py invoked without a payload (argv or stdin)",
            "confidence": 0.0,
        })
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("payload not an object")
    except (json.JSONDecodeError, ValueError) as e:
        return emit_contract({
            "task_id": "", "code": "", "loc": 0,
            "self_test_results": {"passed": 0, "failed": 0},
            "rationale": f"invalid argv JSON: {e}",
            "confidence": 0.0,
        })
    return emit_contract(payload)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
