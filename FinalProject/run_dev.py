#!/usr/bin/env python3
"""
run_dev.py — AIASE 2026 期末專案本地自測驅動程式（FILE-BASED，course 2026-06 更新）

輸出方式改為 **file-based**：你的 skill 由 `scripts/run.py`/`advise.py` 把最終結果
**寫入結果檔**(路徑取自環境變數 `AIASE_RESULT_PATH`),評分器**讀那個檔**評分,不再從
對話 stdout 擷取 JSON。本檔對每題：

  1. 設 `AIASE_RESULT_PATH` 指到該題唯一的 temp 結果檔。
  2. 用**正式評分指令**(含 `-Q`)呼叫 skill：
       hermes chat --toolsets skills,terminal --yolo -Q -q '/<skill> <json>'
  3. 用 `aiase_contract.read_result` 讀檔；沒檔 = 該題未產出(對齊評分器 gate)。
  4. (basic) 用 `validate_basic_schema` 驗 schema、在 sqlite 上以 `bag_equal` 比對 sql vs gold_sql。
     (pairwise) 讀檔 + 跑 reference 對手 / ground-truth test cases。

⚠️ 比對核心(`read_result` / `validate_basic_schema` / `bag_equal` / `run_sql`)一律來自
   `aiase_contract`(與評分器同一份,務必與本檔同層)。**本地 pass/fail 等同評分器**,但你看不到
   hidden test / perturbation / reference 答案。

用法：
    python run_dev.py --skill text2sql-<github_id> --track basic
    python run_dev.py --skill code-author-<github_id> --track pairwise --role code-author
    python run_dev.py --skill bug-hunter-<github_id>  --track pairwise --role bug-hunter
    python run_dev.py --check-only          # 只檢 dev_set 完整性 + helpers,不呼叫 hermes
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))  # 確保找得到同層的 aiase_contract
import aiase_contract as contract  # noqa: E402  (single source of truth — 與評分器共用)

DEV_SET_DIR = REPO_ROOT / "dev_set"
RESULTS_DIR = REPO_ROOT / "dev_run_results"

HERMES_BIN = os.environ.get("HERMES_BIN", "hermes")
HERMES_TIMEOUT_SEC = int(os.environ.get("HERMES_TIMEOUT_SEC", "120"))

# 正式評分指令固定 flag（含 -Q,course 2026-06 公告）。
HERMES_BASE = [HERMES_BIN, "chat", "--toolsets", "skills,terminal", "--yolo", "-Q"]


# ---------------------------------------------------------------------------
# 1. 比對核心 — 從 aiase_contract 取得（與評分器同一份），於此 re-export 供 tests 使用
# ---------------------------------------------------------------------------

bag_equal = contract.bag_equal            # multiset 比對（列順序/欄位順序不計、重複列計入）
run_sql_contract = contract.run_sql       # 在 sqlite 上跑 SQL，回 list of tuple
read_result = contract.read_result        # 讀結果檔（不存在/非 object → None）
validate_basic_schema = contract.validate_basic_schema
resolve_result_path = contract.resolve_result_path


def run_sql(db_path, sql: str, timeout_sec: float = 5.0) -> list:
    """Thin wrapper over aiase_contract.run_sql（保留舊簽名 timeout_sec 供既有測試呼叫）。"""
    return contract.run_sql(str(db_path), sql)


import re  # noqa: E402

READ_ONLY_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|ATTACH|DETACH|REPLACE|TRUNCATE|VACUUM|PRAGMA)\b",
    re.IGNORECASE,
)


def is_read_only_sql(sql: str) -> tuple[bool, str]:
    """淺檢:不允許 DDL/DML 與多 statement（與評分器一致的最小檢查）。"""
    if ";" in sql.strip().rstrip(";"):
        return False, "Multiple SQL statements not allowed."
    if READ_ONLY_FORBIDDEN_KEYWORDS.search(sql):
        return False, "DDL/DML keyword detected."
    return True, ""


# ---------------------------------------------------------------------------
# 2. Dev set loaders
# ---------------------------------------------------------------------------


def load_basic_tasks() -> list[dict]:
    tasks = []
    basic_dir = DEV_SET_DIR / "basic"
    if not basic_dir.exists():
        return tasks
    for p in sorted(basic_dir.glob("task_nl2sql_*.json")):
        try:
            tasks.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError as e:
            print(f"[warn] skip invalid JSON: {p.name}: {e}", file=sys.stderr)
    return tasks


def load_pairwise_reference_tasks() -> list[dict]:
    tasks = []
    ref_dir = DEV_SET_DIR / "pairwise" / "reference_tasks"
    if not ref_dir.exists():
        return tasks
    for p in sorted(ref_dir.glob("task_*.json")):
        if p.name.endswith("_GROUND_TRUTH.json"):
            continue
        try:
            tasks.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError as e:
            print(f"[warn] skip invalid JSON: {p.name}: {e}", file=sys.stderr)
    return tasks


def load_reference_ground_truth(task_id: str) -> Optional[dict]:
    """Ground-truth fields for a reference pairwise task (consolidated or *_GROUND_TRUTH form)."""
    base = DEV_SET_DIR / "pairwise" / "reference_tasks"
    gt = base / f"{task_id}_GROUND_TRUTH.json"
    if gt.exists():
        path = gt
    else:
        main = base / f"{task_id}.json"
        if not main.exists():
            return None
        path = main
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    data.setdefault("bugs", data.get("bugs_in_buggy", []))
    return data


# ---------------------------------------------------------------------------
# 3. Hermes 呼叫（file-based：設 AIASE_RESULT_PATH、加 -Q、讀結果檔）
# ---------------------------------------------------------------------------


def hermes_available() -> bool:
    return shutil.which(HERMES_BIN) is not None


@dataclass
class HermesResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int
    elapsed_sec: float
    error: str = ""


def call_hermes_skill(slash_command: str, payload: dict, result_path: str,
                      model: Optional[str] = None) -> HermesResult:
    """
    呼叫 `hermes chat --toolsets skills,terminal --yolo -Q -q '<slash> <payload_json>'`,
    並先把 `AIASE_RESULT_PATH` 指到本題的 result_path（skill 會把結果寫到該檔）。
    指令與正式評分環境一致(course 2026-06 公告:含 `-Q`、file-based)。
    """
    if not hermes_available():
        return HermesResult(
            ok=False, stdout="", stderr="", returncode=-1, elapsed_sec=0.0,
            error=f"`{HERMES_BIN}` not found in PATH; set $HERMES_BIN or install Hermes Agent.",
        )

    payload_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    arg = f"{slash_command} {payload_str}"
    cmd = list(HERMES_BASE)
    if model:
        cmd += ["-m", model]
    cmd += ["-q", arg]

    env = dict(os.environ)
    env["AIASE_RESULT_PATH"] = result_path

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, env=env, capture_output=True, text=True,
            timeout=HERMES_TIMEOUT_SEC, check=False,
        )
    except subprocess.TimeoutExpired:
        return HermesResult(
            ok=False, stdout="", stderr="", returncode=-1,
            elapsed_sec=time.time() - t0,
            error=f"hermes timed out after {HERMES_TIMEOUT_SEC}s",
        )
    elapsed = time.time() - t0
    return HermesResult(
        ok=(proc.returncode == 0),
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        returncode=proc.returncode,
        elapsed_sec=elapsed,
    )


# ---------------------------------------------------------------------------
# 4. Track 評分流程（file-based）
# ---------------------------------------------------------------------------


@dataclass
class TaskResult:
    task_id: str
    passed: bool
    reason: str = ""
    sql_returned: str = ""
    elapsed_sec: float = 0.0
    extras: dict = field(default_factory=dict)


@dataclass
class TrackReport:
    track: str
    skill: str
    role: str = ""
    total: int = 0
    passed: int = 0
    results: list[TaskResult] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pass_rate"] = (self.passed / self.total) if self.total else 0.0
        return d


def grade_basic(skill_name: str, model: Optional[str] = None, dry_run: bool = False) -> TrackReport:
    """對 dev_set/basic/ 內所有任務跑學生 skill(file-based),以 bag_equal 比對 gold_sql 結果。"""
    rep = TrackReport(track="basic", skill=skill_name)
    tasks = load_basic_tasks()
    rep.total = len(tasks)
    if not tasks:
        rep.note = "no basic tasks loaded from dev_set/basic/"
        return rep

    slash = f"/{skill_name}"
    tmpdir = Path(tempfile.mkdtemp(prefix="aiase_basic_"))
    for task in tasks:
        task_id = task.get("task_id", "<missing>")
        db_path = REPO_ROOT / task.get("db_path", "")
        gold_sql = task.get("gold_sql", "")

        if dry_run:
            rep.results.append(TaskResult(task_id, False, reason="dry-run (skill not invoked)"))
            continue
        if not db_path.exists():
            rep.results.append(TaskResult(task_id, False, reason=f"db_path missing: {db_path}"))
            continue

        result_path = str(tmpdir / f"{task_id}.json")
        if os.path.exists(result_path):
            os.remove(result_path)

        payload = {
            "task_id": task_id,
            "question": task.get("question", ""),
            "db_schema": task.get("db_schema", ""),
            "dialect": task.get("dialect", "sqlite"),
        }
        hr = call_hermes_skill(slash, payload, result_path, model=model)
        if not hr.ok:
            rep.results.append(TaskResult(
                task_id, False, reason=f"hermes call failed: {hr.error or hr.stderr[:200]}",
                elapsed_sec=hr.elapsed_sec))
            continue

        obj = read_result(result_path)
        if obj is None:
            rep.results.append(TaskResult(
                task_id, False, reason="no result file (task not produced)",
                elapsed_sec=hr.elapsed_sec))
            continue

        ok, why = validate_basic_schema(obj, task_id)
        if not ok:
            rep.results.append(TaskResult(
                task_id, False, reason=f"schema invalid: {why}", elapsed_sec=hr.elapsed_sec))
            continue

        student_sql = obj.get("sql", "")
        ok_ro, why_ro = is_read_only_sql(student_sql)
        if not ok_ro:
            rep.results.append(TaskResult(
                task_id, False, reason=f"non-read-only SQL: {why_ro}",
                sql_returned=student_sql, elapsed_sec=hr.elapsed_sec))
            continue

        try:
            student_rows = run_sql(db_path, student_sql)
            gold_rows = run_sql(db_path, gold_sql)
        except sqlite3.Error as e:
            rep.results.append(TaskResult(
                task_id, False, reason=f"SQL execution error: {e}",
                sql_returned=student_sql, elapsed_sec=hr.elapsed_sec))
            continue

        passed = bag_equal(student_rows, gold_rows)
        rep.results.append(TaskResult(
            task_id, passed, reason="" if passed else "bag equality failed",
            sql_returned=student_sql, elapsed_sec=hr.elapsed_sec,
            extras={"student_rowcount": len(student_rows), "gold_rowcount": len(gold_rows)}))

    rep.passed = sum(1 for r in rep.results if r.passed)
    return rep


def _bug_set_from_obj(obj: dict) -> set:
    out = set()
    for b in obj.get("bugs", []) or []:
        try:
            out.add((int(b.get("line_start")), str(b.get("type", "")).strip()))
        except (TypeError, ValueError):
            continue
    return out


def _run_code_test_cases(code: str, constraints: dict, test_cases: list) -> tuple[int, int]:
    entry = constraints.get("entry_function", "")
    if not entry or not code:
        return 0, len(test_cases)
    ns: dict = {}
    try:
        exec(compile(code, "<student_code>", "exec"), ns)
    except Exception:
        return 0, len(test_cases)
    fn = ns.get(entry)
    if not callable(fn):
        return 0, len(test_cases)
    passed = 0
    for tc in test_cases:
        args = tc.get("input", [])
        expected = tc.get("expected")
        try:
            got = fn(*args) if isinstance(args, list) else fn(args)
            if got == expected:
                passed += 1
        except Exception:
            pass
    return passed, len(test_cases) - passed


def grade_pairwise(skill_name: str, role: str, model: Optional[str] = None,
                   dry_run: bool = False) -> TrackReport:
    """Pairwise 本地評分(file-based) — 學生端無 hidden tests,只能對 reference 對手與 ground truth。"""
    rep = TrackReport(track="pairwise", skill=skill_name, role=role)
    tasks = load_pairwise_reference_tasks()
    rep.total = len(tasks)
    if not tasks:
        rep.note = "no reference tasks loaded from dev_set/pairwise/reference_tasks/"
        return rep

    slash = f"/{skill_name}"
    tmpdir = Path(tempfile.mkdtemp(prefix="aiase_pair_"))

    if role == "code-author":
        for task in tasks:
            task_id = task["task_id"]
            if dry_run:
                rep.results.append(TaskResult(task_id, False, reason="dry-run"))
                continue
            result_path = str(tmpdir / f"{task_id}.json")
            payload = {
                "task_id": task_id,
                "task_description": task.get("task_description", ""),
                "constraints": task.get("constraints", {}),
            }
            hr = call_hermes_skill(slash, payload, result_path, model=model)
            if not hr.ok:
                rep.results.append(TaskResult(task_id, False, reason=f"hermes failed: {hr.error}"))
                continue
            obj = read_result(result_path)
            if obj is None or obj.get("task_id") != task_id or "code" not in obj:
                rep.results.append(TaskResult(task_id, False, reason="no/invalid result file"))
                continue
            code = obj.get("code", "")
            gt = load_reference_ground_truth(task_id) or {}
            test_cases = gt.get("test_cases", [])
            passed_cases, failed_cases = _run_code_test_cases(code, task.get("constraints", {}), test_cases)
            all_pass = (failed_cases == 0 and passed_cases == len(test_cases))
            rep.results.append(TaskResult(
                task_id, all_pass,
                reason=("" if all_pass else f"{failed_cases}/{len(test_cases)} hidden-style cases failed"),
                elapsed_sec=hr.elapsed_sec,
                extras={"passed_cases": passed_cases, "total_cases": len(test_cases)}))

    elif role == "bug-hunter":
        for task in tasks:
            task_id = task["task_id"]
            if dry_run:
                rep.results.append(TaskResult(task_id, False, reason="dry-run"))
                continue
            gt = load_reference_ground_truth(task_id) or {}
            buggy_code = gt.get("buggy_code", "")
            clean_code = gt.get("clean_code", "")
            gt_bugs = _bug_set_from_obj({"bugs": gt.get("bugs", [])})
            if not buggy_code:
                rep.results.append(TaskResult(task_id, False, reason="no ground-truth buggy_code"))
                continue

            rp_b = str(tmpdir / f"{task_id}_buggy.json")
            payload_b = {"task_id": task_id, "task_description": task.get("task_description", ""),
                         "code": buggy_code}
            hr = call_hermes_skill(slash, payload_b, rp_b, model=model)
            if not hr.ok:
                rep.results.append(TaskResult(task_id, False, reason=f"hermes failed: {hr.error}"))
                continue
            obj = read_result(rp_b)
            if obj is None or obj.get("task_id") != task_id:
                rep.results.append(TaskResult(task_id, False, reason="no/invalid result file"))
                continue

            student_bugs = _bug_set_from_obj(obj)
            inter = len(student_bugs & gt_bugs)
            union = len(student_bugs | gt_bugs) or 1
            recall_like = inter / max(1, len(gt_bugs))

            clean_fp = 0
            if clean_code:
                rp_c = str(tmpdir / f"{task_id}_clean.json")
                payload_c = dict(payload_b); payload_c["code"] = clean_code
                hr_c = call_hermes_skill(slash, payload_c, rp_c, model=model)
                if hr_c.ok:
                    objc = read_result(rp_c) or {}
                    if objc.get("verdict") == "buggy" or len(objc.get("bugs", []) or []) > 0:
                        clean_fp = 1

            passed = (recall_like >= 0.5 and clean_fp == 0)
            rep.results.append(TaskResult(
                task_id, passed,
                reason=("" if passed else f"recall={recall_like:.2f}, clean_fp={clean_fp}"),
                elapsed_sec=hr.elapsed_sec,
                extras={"jaccard": inter / union, "recall_like": recall_like, "clean_fp": clean_fp}))
    else:
        rep.note = f"unknown role: {role}"
        return rep

    rep.passed = sum(1 for r in rep.results if r.passed)
    return rep


# ---------------------------------------------------------------------------
# 5. CLI
# ---------------------------------------------------------------------------


def _write_report(report: TrackReport) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    suffix = f"_{report.role}" if report.role else ""
    out = RESULTS_DIR / f"{report.track}{suffix}_{report.skill}_{stamp}.json"
    out.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return out


def _print_summary(report: TrackReport) -> None:
    print(f"\n=== {report.track.upper()} :: {report.skill} {('('+report.role+')') if report.role else ''} ===")
    if report.note:
        print(f"  note: {report.note}")
    print(f"  total: {report.total}  passed: {report.passed}  rate: "
          f"{(report.passed/report.total*100 if report.total else 0):.1f}%")
    for r in report.results[:50]:
        mark = "✓" if r.passed else "✗"
        print(f"   {mark} {r.task_id}  {r.reason}")
    if len(report.results) > 50:
        print(f"   ... ({len(report.results)-50} more)")


def _check_only() -> int:
    """Sanity check the dev set + helpers without invoking Hermes."""
    print("[check] loading basic tasks...")
    tasks = load_basic_tasks()
    print(f"  loaded {len(tasks)} basic tasks")
    bad = 0
    for t in tasks:
        tid = t.get("task_id", "?")
        db = REPO_ROOT / t.get("db_path", "")
        if not db.exists():
            print(f"  ✗ {tid}: missing db {db.relative_to(REPO_ROOT)}")
            bad += 1
            continue
        gold = t.get("gold_sql", "")
        ok, why = is_read_only_sql(gold)
        if not ok:
            print(f"  ✗ {tid}: gold_sql not read-only: {why}")
            bad += 1
            continue
        try:
            rows = run_sql(db, gold)
        except sqlite3.Error as e:
            print(f"  ✗ {tid}: gold_sql failed: {e}")
            bad += 1
            continue
        if not bag_equal(rows, rows):
            print(f"  ✗ {tid}: bag_equal not reflexive!")
            bad += 1
            continue
        print(f"  ✓ {tid}: {len(rows)} rows")

    print(f"\n[check] reference tasks...")
    refs = load_pairwise_reference_tasks()
    print(f"  loaded {len(refs)} reference tasks")
    for r in refs:
        tid = r.get("task_id", "?")
        gt = load_reference_ground_truth(tid)
        if gt is None:
            print(f"  ! {tid}: no ground-truth (may be intentional for student-facing variant)")
        else:
            print(f"  ✓ {tid}: ground-truth has {len(gt.get('bugs', []))} bugs, "
                  f"{len(gt.get('test_cases', []))} test cases")

    print(f"\n[check] aiase_contract present: {(REPO_ROOT / 'aiase_contract.py').exists()}")
    print(f"[check] done. {bad} issue(s).")
    return 0 if bad == 0 else 1


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="AIASE 2026 local dev runner (file-based)")
    p.add_argument("--skill", required=False, help="skill name (folder name)")
    p.add_argument("--track", choices=["basic", "pairwise"], required=False)
    p.add_argument("--role", choices=["code-author", "bug-hunter"], default="",
                   help="required for --track pairwise")
    p.add_argument("--model", default=None, help="override model (else hermes config default)")
    p.add_argument("--dry-run", action="store_true",
                   help="don't call hermes; just verify loader + structure")
    p.add_argument("--check-only", action="store_true",
                   help="check dev_set integrity + helpers, exit 0/1; no skill invocation")
    args = p.parse_args(argv)

    if args.check_only:
        return _check_only()

    if not args.skill or not args.track:
        p.error("--skill and --track are required (or use --check-only)")

    if args.track == "basic":
        rep = grade_basic(args.skill, model=args.model, dry_run=args.dry_run)
    else:
        if not args.role:
            p.error("--role is required when --track pairwise")
        rep = grade_pairwise(args.skill, args.role, model=args.model, dry_run=args.dry_run)

    _print_summary(rep)
    if not args.dry_run:
        out = _write_report(rep)
        print(f"\nreport written to: {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
