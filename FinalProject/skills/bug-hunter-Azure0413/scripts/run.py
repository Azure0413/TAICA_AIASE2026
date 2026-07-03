#!/usr/bin/env python3
"""
bug-hunter skill — final output wrapper (FILE-BASED output contract).

Reads JSON from argv[1] (or stdin) with {task_id, verdict, bugs, confidence}; enforces
shape and the rule "verdict=clean → bugs=[]"; and **atomically writes** the Pairwise Bug
Hunter result to the agreed result file. The grader reads that file — it no longer scrapes
a fenced JSON block from the conversation (course 2026-06 file-based update).

Result path = $AIASE_RESULT_PATH, else ./aiase_result.json (cwd). Self-contained: we do NOT
`import aiase_contract` (not importable once the skill is installed standalone).
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


ALLOWED_VERDICTS = {"buggy", "clean"}
ALLOWED_TYPES = {
    "off_by_one", "null_deref", "type_error", "logic_error",
    "edge_case", "api_misuse", "inefficient", "unhandled_input",
}
ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}


def _clamp_confidence(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(f):   # reject NaN / Infinity (spec §1.4 #2 forbids them in the JSON)
        return 0.0
    return max(0.0, min(1.0, f))


def _sanitize_bug(b: dict) -> dict | None:
    if not isinstance(b, dict):
        return None
    try:
        ls = int(b.get("line_start"))
        le = int(b.get("line_end", ls))
    except (TypeError, ValueError):
        return None
    if ls < 1 or le < ls:
        return None
    sev = str(b.get("severity", "")).strip().lower()
    typ = str(b.get("type", "")).strip().lower()
    if sev not in ALLOWED_SEVERITIES or typ not in ALLOWED_TYPES:
        return None
    return {
        "line_start": ls,
        "line_end": le,
        "severity": sev,
        "type": typ,
        "description": str(b.get("description", "")),
        "suggested_fix": str(b.get("suggested_fix", "")),
    }


def emit_contract(obj: dict) -> int:
    verdict = str(obj.get("verdict", "")).strip().lower()
    if verdict not in ALLOWED_VERDICTS:
        verdict = "clean"

    raw_bugs = obj.get("bugs") or []
    if not isinstance(raw_bugs, list):
        raw_bugs = []
    bugs = [b for b in (_sanitize_bug(x) for x in raw_bugs) if b is not None]

    # 規格:verdict=clean 時 bugs[] 必須是 []。
    if verdict == "clean":
        bugs = []
    # 若有 bugs 卻 verdict=clean 已被擋;反之有 bug 但 verdict=buggy ok。
    if verdict == "buggy" and not bugs:
        # buggy 但沒列任何 bug 是 contract 違規,但我們不自動翻為 clean — 留給評分器扣分。
        pass

    out = {
        "task_id": str(obj.get("task_id", "")),
        "verdict": verdict,
        "bugs": bugs,
        "confidence": _clamp_confidence(obj.get("confidence", 0.5)),
    }
    return write_result(out)


def _raw_payload(argv: list[str]) -> str:
    """argv[1], or stdin when argv absent/'-'. The `code` input contains quotes, which collide
    with a single-quoted shell argv; a quoted heredoc is escaping-free. isatty()-guarded."""
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
        return emit_contract({"task_id": "", "verdict": "clean", "bugs": [], "confidence": 0.0})
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("payload not an object")
    except (json.JSONDecodeError, ValueError):
        return emit_contract({"task_id": "", "verdict": "clean", "bugs": [], "confidence": 0.0})
    return emit_contract(payload)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
