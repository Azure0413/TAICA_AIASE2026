#!/usr/bin/env python3
"""
Deterministic grader-facing evaluator for the open-semver-advisor Open Track scenario.

This is the scorer described in OPEN_TRACK.md §4. It recomputes the authoritative SemVer bump
from (old_code, new_code) via the same AST core the skill uses, then compares it to the skill's
predicted bump. Because the bump is computed here — not supplied by the skill — and the grader
runs this on held-out perturbed diffs, the metric is non-gameable: a skill cannot hardcode an
answer for an unseen diff.

Two usage modes:

1. Inline payload:
       python evaluate.py '{"task_id":"t","old_code":"...","new_code":"...",
                            "predicted_bump":"minor","changelog":"..."}'

2. Scenario file + candidate-output file:
       python evaluate.py --scenario dev_set/open/semver_001.json --candidate cand.json

Prints a single fenced JSON block:
    {"task_id": str, "bump_truth": str, "bump_pred": str, "bump_correct": bool,
     "changelog_coverage": float, "accuracy": float, "error": str}

PRIMARY metric  = bump_correct (1.0 / 0.0): exact match of the SemVer level. This is the hard,
                  non-gameable signal.
SECONDARY metric = changelog_coverage: fraction of changed public symbols whose name appears in
                  the candidate changelog (1.0 when there are no changes). Reported but the
                  scenario's pass/accuracy is driven by bump_correct.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _semver import classify  # noqa: E402

_SYM_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")


def _changed_symbols(changes: dict) -> set:
    """Pull the dotted symbol names out of the human-readable change strings."""
    out = set()
    for kind in ("breaking", "additive"):
        for line in changes.get(kind, []):
            # each line looks like "function removed: name" / "method added: A.g"
            tail = line.split(":", 1)[-1].strip()
            m = _SYM_RE.search(tail)
            if m:
                out.add(m.group(0).split(".")[-1])  # base symbol name
    return out


def _coverage(changelog: str, symbols: set) -> float:
    if not symbols:
        return 1.0
    text = changelog or ""
    hit = sum(1 for s in symbols if s in text)
    return round(hit / len(symbols), 6)


def _build(task_id, old_code, new_code, predicted_bump, changelog) -> dict:
    res = classify(old_code, new_code)
    if res["error"]:
        return {"task_id": task_id, "bump_truth": "", "bump_pred": predicted_bump,
                "bump_correct": False, "changelog_coverage": 0.0, "accuracy": 0.0,
                "error": res["error"]}
    truth = res["bump"]
    correct = (str(predicted_bump).strip().lower() == truth)
    cov = _coverage(changelog, _changed_symbols(res["changes"]))
    return {"task_id": task_id, "bump_truth": truth, "bump_pred": str(predicted_bump).strip().lower(),
            "bump_correct": correct, "changelog_coverage": cov,
            "accuracy": 1.0 if correct else 0.0, "error": ""}


def _emit(obj: dict, ok: bool) -> int:
    sys.stdout.write("```json\n")
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2))
    sys.stdout.write("\n```\n")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] in ("--scenario", "--candidate"):
        p = argparse.ArgumentParser()
        p.add_argument("--scenario", required=True)
        p.add_argument("--candidate", required=True)
        args = p.parse_args(argv[1:])
        scn = json.loads(Path(args.scenario).read_text(encoding="utf-8"))
        cand = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
        out = _build(str(scn.get("task_id", cand.get("task_id", ""))),
                     str(scn.get("old_code", "")), str(scn.get("new_code", "")),
                     str(cand.get("bump", "")), str(cand.get("changelog", "")))
        return _emit(out, ok=out["bump_correct"])

    if len(argv) < 2:
        return _emit({"task_id": "", "bump_truth": "", "bump_pred": "", "bump_correct": False,
                      "changelog_coverage": 0.0, "accuracy": 0.0,
                      "error": "usage: evaluate.py '<json>' | --scenario f --candidate f"}, ok=False)
    try:
        payload = json.loads(argv[1])
        if not isinstance(payload, dict):
            raise ValueError("payload not an object")
    except (json.JSONDecodeError, ValueError) as e:
        return _emit({"task_id": "", "bump_truth": "", "bump_pred": "", "bump_correct": False,
                      "changelog_coverage": 0.0, "accuracy": 0.0, "error": f"argv JSON invalid: {e}"}, ok=False)

    out = _build(str(payload.get("task_id", "")), str(payload.get("old_code", "")),
                 str(payload.get("new_code", "")), str(payload.get("predicted_bump", payload.get("bump", ""))),
                 str(payload.get("changelog", "")))
    return _emit(out, ok=out["bump_correct"])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
