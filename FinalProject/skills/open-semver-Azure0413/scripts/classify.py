#!/usr/bin/env python3
"""
open-semver-advisor in-loop harness.

Usage:
    python classify.py '{"old_code":"def f(a): ...","new_code":"def f(a,b): ..."}'

Prints a single fenced JSON block:
    {"bump": "major"|"minor"|"patch"|"",
     "breaking": [str], "additive": [str],
     "error": str}

Pure stdlib (ast). No LLM, no network. The Hermes agent calls this to obtain the deterministic
SemVer verdict + the concrete API changes, then writes a human-readable changelog around them
and emits the contract via run.py. If either source has a syntax error, `bump` is "" and `error`
is set, so the agent can report low confidence instead of guessing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _semver import classify  # noqa: E402


def _emit(obj: dict, ok: bool) -> int:
    sys.stdout.write("```json\n")
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2))
    sys.stdout.write("\n```\n")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return _emit({"bump": "", "breaking": [], "additive": [],
                      "error": "usage: classify.py '<json>'"}, ok=False)
    try:
        try:
            payload = json.loads(argv[1])
        except json.JSONDecodeError:
            payload = json.loads(argv[1].replace("\\'", "'"))  # tolerate the invalid \' escape
        if not isinstance(payload, dict):
            raise ValueError("payload not an object")
    except (json.JSONDecodeError, ValueError) as e:
        return _emit({"bump": "", "breaking": [], "additive": [],
                      "error": f"argv JSON invalid: {e}"}, ok=False)

    res = classify(str(payload.get("old_code", "")), str(payload.get("new_code", "")))
    out = {
        "bump": res["bump"],
        "breaking": res["changes"]["breaking"],
        "additive": res["changes"]["additive"],
        "error": res["error"],
    }
    return _emit(out, ok=(res["bump"] != ""))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
