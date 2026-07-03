#!/usr/bin/env python3
"""
text2sql skill — final output wrapper (FILE-BASED output contract).

Reads a JSON payload from argv[1] (or stdin) containing {task_id, sql, rationale,
confidence}, validates the contract minimally, and **atomically writes** the Basic
Track result to the agreed result file. The grader reads that file — it no longer
scrapes a fenced JSON block from the conversation (course 2026-06 file-based update).

Result path = $AIASE_RESULT_PATH, else ./aiase_result.json (cwd). Self-contained:
we do NOT `import aiase_contract` — once the skill is installed under
~/.hermes/skills/<cat>/<name>/ that repo-root module is not importable. The path
rule below is kept byte-for-byte identical to aiase_contract.resolve_result_path.

The LLM (Hermes agent) is responsible for filling in `sql` (via the Procedure in
SKILL.md). This script only enforces the deterministic output shape + the write.
"""

from __future__ import annotations

import json
import math
import os
import sys


CONTRACT_FIELDS = ("task_id", "sql", "rationale", "confidence")


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
    os.replace(tmp, path)  # atomic on POSIX + Windows
    print(f"written ok -> {path}")
    return 0


def emit_contract(obj: dict) -> int:
    out = {
        "task_id": str(obj.get("task_id", "")),
        "sql": str(obj.get("sql", "")).strip(),
        "rationale": str(obj.get("rationale", "")),
        "confidence": _clamp_confidence(obj.get("confidence", 0.5)),
    }
    # 任何 extra fields 一律忽略(規格書 §1.4 #3)。
    return write_result(out)


def _clamp_confidence(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(f):   # reject NaN / Infinity (spec §1.4 #2 forbids them in the JSON)
        return 0.0
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


def _raw_payload(argv: list[str]) -> str:
    """Read the JSON payload from argv[1], or from stdin when argv is absent or '-'.

    The stdin path is the quote-safe route: a SQL string literal uses single quotes
    (`WHERE title = 'X'`), which collide with a single-quoted shell argv. Passing the
    payload via a quoted heredoc (`python run.py <<'JSON' ... JSON`) needs no escaping.
    Guarded by isatty() so a no-argv, no-pipe invocation returns "" immediately instead
    of blocking on an interactive terminal.
    """
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
        # 失敗也要寫出契約 JSON,不可只噴錯(規格書 §1.4 #7)。
        return emit_contract({
            "task_id": "",
            "sql": "",
            "rationale": "run.py invoked without a payload (argv or stdin)",
            "confidence": 0.0,
        })

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("payload not an object")
    except (json.JSONDecodeError, ValueError) as e:
        return emit_contract({
            "task_id": "",
            "sql": "",
            "rationale": f"invalid argv JSON: {e}",
            "confidence": 0.0,
        })

    return emit_contract(payload)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
