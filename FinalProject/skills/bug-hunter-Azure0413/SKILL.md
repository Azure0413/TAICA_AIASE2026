---
name: bug-hunter-Azure0413
description: Audit a Python function for bugs against its task description, then write a structured bug report via scripts/run.py per the AIASE 2026 Pairwise Bug Hunter contract (file-based output).
version: 2.0.0
metadata:
  hermes:
    tags: [code, audit, aiase-2026]
    category: code
    requires_toolsets: [terminal]
---

# Bug Hunter Skill (Pairwise Track)

## When to Use

When the user sends a JSON payload with `code` (Python source), `task_description`, and `task_id`. The skill must produce a structured bug report whose `bugs[]` matches actual bugs (Jaccard-ish line+type overlap), with low false-positive rate on clean code.

Trigger example:

```
/bug-hunter-<your_github_id> {"task_id":"task_042",
  "code":"def merge_intervals(intervals): ...",
  "task_description":"Merge overlapping intervals, empty input returns []."}
```

## Procedure

1. **Parse** the payload. Read `code` line-by-line (1-indexed); read the task description for the spec.
2. **Probe** the code by running `python scripts/analyze.py` with the code + task description + entry function name. The script:
   - parses the AST to extract function name + parameters,
   - runs the function on a battery of deterministic edge inputs (empty, single-element, extremes),
   - returns per-input crash / mismatch / OK plus suspicious line ranges.
3. **Review** the analyzer signals. For each suspicious line range, decide:
   - **bug or not** (don't over-report — false positives are penalized).
   - **type**: one of `off_by_one` / `null_deref` / `type_error` / `logic_error` / `edge_case` / `api_misuse` / `inefficient` / `unhandled_input` (see spec §2.3).
   - **severity**: `critical` / `high` / `medium` / `low` — calibrated to "how easily triggered + how severe".
   - **suggested_fix**: actionable, specific.
4. **Verdict**: `clean` if no bugs found, `buggy` otherwise. If `verdict=clean`, `bugs[]` must be `[]`.
5. **Write the result** by running `scripts/run.py` with the **`terminal` tool** (not a
   background/process tool), passing the final `{task_id, verdict, bugs, confidence}`. `run.py`
   **writes the result file** (`$AIASE_RESULT_PATH`, else `./aiase_result.json`) and prints
   `written ok -> <path>`. **You do NOT need to print or repeat any JSON in the conversation** —
   the grader reads the file, not your message.

> **Passing the payload (quote-safe):** the `code` you analyze is full of quotes, which collide with a
> single-quoted shell argv. Both `analyze.py` and `run.py` read the payload from **stdin**, so use a
> **quoted heredoc** — no escaping needed. Use the directory Hermes reports as `[Skill directory: ...]`:
>
> ```bash
> python3 <skill_dir>/scripts/analyze.py <<'JSON'
> {"code":"def f(x):\n    return 'ok'\n","entry_function":"f"}
> JSON
> ```
>
> ```bash
> python3 <skill_dir>/scripts/run.py <<'JSON'
> {"task_id":"task_042","verdict":"buggy","bugs":[{"line_start":3,"line_end":3,"severity":"medium","type":"edge_case","description":"...","suggested_fix":"..."}],"confidence":0.8}
> JSON
> ```
>
> The argv form (`python3 <skill_dir>/scripts/run.py '{...}'`) also works when the JSON has no single quotes.

## Pitfalls

- **Over-reporting** (always reporting many bugs) destroys score — clean code FP rate is 25% of your grade.
- **Under-reporting** (always `verdict=clean`) also destroys score — F1 on buggy code is 50%.
- **Wrong severity calibration**: empty-input crash = `medium` (edge), wrong-answer-on-common-input = `high`/`critical`. See spec §2.3.
- **Wrong line numbers**: 1-indexed, point at the smallest line range that contains the bug. Don't point at the function signature line for an off-by-one in the loop.

## Verification

`scripts/run.py` writes the result file (`$AIASE_RESULT_PATH`, else `./aiase_result.json`) as a
single JSON **object** with:

- `task_id` (must equal input)
- `verdict` (`"buggy"` or `"clean"`)
- `bugs` (array of bug objects with `line_start`, `line_end`, `severity`, `type`, `description`, `suggested_fix`; **must be `[]` when verdict=clean**)
- `confidence` (number in `[0.0, 1.0]`)

The grader reads that file and compares your `bugs[]` against the reference / Code Author failures.
The file must exist and be valid JSON; no result file = the scenario scores 0. Nothing needs to be
printed in the conversation.
