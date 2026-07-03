"""
File-based output contract tests (course 2026-06 update).

Two layers:
1. aiase_contract — the shared core the grader imports: resolve_result_path / read_result /
   validate_basic_schema.
2. Each graded skill's scripts/run.py (and the Open Track advise.py) actually WRITES a valid
   result file when given a payload and $AIASE_RESULT_PATH. This is the thing that decides the
   grade now — "no result file = 0".
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import aiase_contract as contract

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS = REPO_ROOT / "skills"


# ---------------------------------------------------------------------------
# 1. aiase_contract core
# ---------------------------------------------------------------------------


def test_resolve_result_path_env(monkeypatch, tmp_path):
    target = tmp_path / "r.json"
    monkeypatch.setenv("AIASE_RESULT_PATH", str(target))
    assert contract.resolve_result_path() == str(target)


def test_resolve_result_path_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("AIASE_RESULT_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    assert contract.resolve_result_path() == os.path.join(str(tmp_path), "aiase_result.json")


def test_read_result_missing(tmp_path):
    assert contract.read_result(str(tmp_path / "nope.json")) is None


def test_read_result_object(tmp_path):
    p = tmp_path / "r.json"
    p.write_text('{"task_id": "x", "sql": "SELECT 1"}', encoding="utf-8")
    assert contract.read_result(str(p)) == {"task_id": "x", "sql": "SELECT 1"}


def test_read_result_rejects_non_object(tmp_path):
    p = tmp_path / "r.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    assert contract.read_result(str(p)) is None
    p.write_text("not json", encoding="utf-8")
    assert contract.read_result(str(p)) is None


def test_validate_basic_schema():
    ok, _ = contract.validate_basic_schema(
        {"task_id": "t1", "sql": "SELECT 1", "confidence": 0.5}, "t1")
    assert ok
    assert not contract.validate_basic_schema(
        {"task_id": "other", "sql": "SELECT 1"}, "t1")[0]          # task_id mismatch
    assert not contract.validate_basic_schema(
        {"task_id": "t1", "sql": "  "}, "t1")[0]                    # empty sql
    assert not contract.validate_basic_schema(
        {"task_id": "t1", "sql": "SELECT 1", "confidence": 2.0}, "t1")[0]  # confidence OOR


# ---------------------------------------------------------------------------
# 2. Each skill's run.py / advise.py writes a valid result file
# ---------------------------------------------------------------------------


def _run_writer(script: Path, payload: dict, tmp_path: Path) -> dict:
    """Invoke a skill writer with $AIASE_RESULT_PATH set; return the JSON it wrote."""
    result_path = tmp_path / "aiase_result.json"
    env = dict(os.environ)
    env["AIASE_RESULT_PATH"] = str(result_path)
    proc = subprocess.run(
        [sys.executable, str(script), json.dumps(payload, ensure_ascii=False)],
        env=env, capture_output=True, text=True, encoding="utf-8", timeout=30, check=False,
    )
    assert result_path.exists(), (
        f"{script.name} did not write the result file\nstdout:{proc.stdout}\nstderr:{proc.stderr}")
    return json.loads(result_path.read_text(encoding="utf-8"))


def test_text2sql_run_writes_file(tmp_path):
    out = _run_writer(
        SKILLS / "text2sql-Azure0413" / "scripts" / "run.py",
        {"task_id": "t1", "sql": "SELECT 1", "rationale": "r", "confidence": 0.8}, tmp_path)
    ok, why = contract.validate_basic_schema(out, "t1")
    assert ok, why
    assert out["sql"] == "SELECT 1"


def test_code_author_run_writes_file(tmp_path):
    out = _run_writer(
        SKILLS / "code-author-Azure0413" / "scripts" / "run.py",
        {"task_id": "t2", "code": "def f(x):\n    return x\n", "loc": 2,
         "self_test_results": {"passed": 1, "failed": 0}, "rationale": "r", "confidence": 0.9},
        tmp_path)
    assert out["task_id"] == "t2"
    assert "def f" in out["code"]
    assert out["self_test_results"]["passed"] == 1
    assert 0.0 <= out["confidence"] <= 1.0


def test_bug_hunter_run_writes_file(tmp_path):
    out = _run_writer(
        SKILLS / "bug-hunter-Azure0413" / "scripts" / "run.py",
        {"task_id": "t3", "verdict": "clean", "bugs": [], "confidence": 0.7}, tmp_path)
    assert out["task_id"] == "t3"
    assert out["verdict"] == "clean"
    assert out["bugs"] == []


def test_bug_hunter_clean_forces_empty_bugs(tmp_path):
    # verdict=clean must coerce bugs to [] (contract rule), even if bugs were passed.
    out = _run_writer(
        SKILLS / "bug-hunter-Azure0413" / "scripts" / "run.py",
        {"task_id": "t3", "verdict": "clean",
         "bugs": [{"line_start": 1, "line_end": 1, "severity": "low",
                   "type": "logic_error", "description": "d", "suggested_fix": "f"}],
         "confidence": 0.7}, tmp_path)
    assert out["bugs"] == []


def test_open_semver_advise_writes_file(tmp_path):
    # advise.py computes the bump deterministically AND writes the result file.
    out = _run_writer(
        SKILLS / "open-semver-Azure0413" / "scripts" / "advise.py",
        {"task_id": "semver_x",
         "old_code": "def f(a):\n    return a\n",
         "new_code": "def f(a, b=0):\n    return a + b\n"}, tmp_path)
    assert out["task_id"] == "semver_x"
    assert out["bump"] == "minor"            # new optional param -> minor (deterministic)
    assert 0.0 <= out["confidence"] <= 1.0


def test_writer_bad_input_still_writes_contract(tmp_path):
    # spec §1.4 #7: even on garbage input, a contract-conformant file must be written.
    out = _run_writer(
        SKILLS / "text2sql-Azure0413" / "scripts" / "run.py",
        {"not": "a valid payload"}, tmp_path)
    assert "task_id" in out and "sql" in out and "confidence" in out
