#!/usr/bin/env python3
"""hello-aiase smoke-test entry point — deterministic, no LLM, no network (FILE-BASED).

Writes the result to $AIASE_RESULT_PATH (else ./aiase_result.json). Self-contained: we do NOT
import aiase_contract — once a skill is installed standalone that repo-root module is not
importable, so the path rule below is kept identical to aiase_contract.resolve_result_path."""

from __future__ import annotations

import json
import os
import sys


def resolve_result_path() -> str:
    return os.environ.get("AIASE_RESULT_PATH") or os.path.join(os.getcwd(), "aiase_result.json")


def main(argv: list[str]) -> int:
    raw = argv[1] if len(argv) > 1 else "{}"
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {"_warning": "input was not a JSON object", "_raw": raw}
    except json.JSONDecodeError as e:
        payload = {"_warning": f"invalid JSON: {e}", "_raw": raw}

    out: dict = {
        "ok": True,
        "skill": "hello-aiase",
        "echo": payload,
        "greeting": f"hello, {payload.get('name', 'AIASE 2026')}!",
    }
    if "task_id" in payload:
        out["task_id"] = payload["task_id"]

    # 輸出契約(file-based):原子寫入結果檔。
    path = resolve_result_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, path)
    print(f"written ok -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
