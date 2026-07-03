#!/usr/bin/env python3
"""
open-semver-advisor — ONE-SHOT entry point (the robust path).

Usage:
    python advise.py '{"task_id":"semver_001","old_code":"...","new_code":"..."}'

Takes the user's input payload verbatim, computes the SemVer bump deterministically from the
public-API surface (via _semver), auto-generates a changelog covering every changed public
symbol, and prints the FINAL contract as a single fenced JSON block. The LLM's only job is to
run this one command and relay its output — it never decides the bump itself. This collapses the
probabilistic core to "forward input, relay output", which even weak models do reliably, and
removes the two failure modes seen with a multi-step protocol: (a) the model overriding the
deterministic verdict with intuition, and (b) the model losing its way across steps.

Input JSON: {task_id?, old_code, new_code}. Parsing is tolerant of the common LLM glitches
(over-escaped newlines '\\n', invalid '\\'' escape). Output is always a contract-conformant JSON
with a finite confidence in [0,1] (spec §1.4), even on bad input.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _semver import classify  # noqa: E402

ALLOWED_BUMPS = {"major", "minor", "patch"}


def resolve_result_path() -> str:
    """Result file path: $AIASE_RESULT_PATH, else ./aiase_result.json in cwd.

    Self-contained (we do NOT import aiase_contract — not importable once the skill is
    installed standalone). Kept identical to aiase_contract.resolve_result_path."""
    return os.environ.get("AIASE_RESULT_PATH") or os.path.join(os.getcwd(), "aiase_result.json")


def _loads_tolerant(s: str):
    """
    json.loads with fallbacks for the common ways an LLM mangles a JSON argv:
      1. as-is;
      2. invalid `\\'` escape -> `'`;
      3. double-encoded (the model escaped the whole payload as if it were a JSON *string*: inner
         quotes as `\\"`, newlines as `\\n`). Recover by decoding one JSON-string layer first.
    """
    for cand in (s, s.replace("\\'", "'")):
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    # double-encoded: wrap in quotes, decode the string layer, then parse the inner JSON.
    try:
        inner = json.loads('"' + s + '"')
        obj = json.loads(inner)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass
    raise json.JSONDecodeError("could not parse argv JSON", s, 0)


def _changelog(bump: str, changes: dict) -> str:
    breaking = changes.get("breaking", [])
    additive = changes.get("additive", [])
    if bump == "patch":
        return "Internal / bug-fix release. No public API surface change."
    parts = []
    if breaking:
        parts.append("### Breaking changes\n" + "\n".join(f"- {c}" for c in breaking))
    if additive:
        parts.append("### Added / changed\n" + "\n".join(f"- {c}" for c in additive))
    return "\n\n".join(parts) if parts else "No public API surface change."


def _clamp(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, f)) if math.isfinite(f) else 0.0


def emit(obj: dict) -> int:
    """Atomically WRITE the final contract to the result file (file-based output, course
    2026-06 update). The grader reads the file; we no longer rely on a fenced JSON block in
    the conversation."""
    path = resolve_result_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)  # atomic
    print(f"written ok -> {path}")
    return 0


def advise(payload: dict) -> dict:
    task_id = str(payload.get("task_id", ""))
    res = classify(str(payload.get("old_code", "")), str(payload.get("new_code", "")))
    bump = res["bump"]
    if bump not in ALLOWED_BUMPS:
        return {"task_id": task_id, "bump": "", "changelog": "",
                "rationale": f"Could not analyze the diff deterministically: {res['error']}",
                "confidence": 0.1}
    nb, na = len(res["changes"]["breaking"]), len(res["changes"]["additive"])
    rationale = {
        "major": f"Public API has {nb} breaking change(s); SemVer requires a major bump.",
        "minor": f"{na} backward-compatible addition(s) and no breaking change; minor bump.",
        "patch": "No public API surface change (only internal/private edits); patch bump.",
    }[bump]
    return {"task_id": task_id, "bump": bump, "changelog": _changelog(bump, res["changes"]),
            "rationale": rationale, "confidence": 1.0}


def _raw_payload(argv: list[str]) -> str:
    """argv[1], or stdin when argv absent/'-'. old_code/new_code are Python source full of quotes;
    a quoted heredoc (`python advise.py <<'JSON' ... JSON`) passes them with zero escaping, which
    is even more robust than the tolerant parser below. isatty()-guarded so it never blocks."""
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
        return emit({"task_id": "", "bump": "", "changelog": "",
                     "rationale": "advise.py invoked without a payload (argv or stdin)", "confidence": 0.0})
    try:
        payload = _loads_tolerant(raw)
        if not isinstance(payload, dict):
            raise ValueError("payload not an object")
    except (json.JSONDecodeError, ValueError) as e:
        return emit({"task_id": "", "bump": "", "changelog": "",
                     "rationale": f"invalid argv JSON: {e}", "confidence": 0.0})
    out = advise(payload)
    out["confidence"] = _clamp(out["confidence"])
    return emit(out)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
