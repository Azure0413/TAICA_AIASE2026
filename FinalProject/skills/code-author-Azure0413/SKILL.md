---
name: code-author-Azure0413
description: Implement a Python function from a natural-language task description, self-test, and write the AIASE 2026 Pairwise Code Author result via scripts/run.py (file-based output contract).
version: 2.0.0
metadata:
  hermes:
    tags: [code, python, aiase-2026]
    category: code
    requires_toolsets: [terminal]
---

# Code Author Skill (Pairwise Track)

## When to Use

When the user sends a JSON payload with `task_description`, `constraints` (entry_function, max_loc, imports_forbidden), and `task_id`. The skill must produce a Python implementation that:

- defines exactly the entry function named in `constraints.entry_function`,
- does not exceed `constraints.max_loc` source lines (measured by `radon raw`),
- does not import anything in `constraints.imports_forbidden`,
- handles realistic edge cases (empty input, single element, extremes — see Pitfalls).

Trigger example:

```
/code-author-<your_github_id> {"task_id":"task_042",
  "task_description":"Implement merge_intervals(intervals): merge overlapping intervals, empty input returns [].",
  "constraints":{"entry_function":"merge_intervals","max_loc":500,"imports_forbidden":["os","sys"]}}
```

## Procedure

1. **Parse** the task description; identify inputs, outputs, edge cases, and complexity targets.
2. **Draft** a Python implementation defining `constraints.entry_function`. Keep code idiomatic; do not over-engineer.
3. **Self-test** by running `python scripts/selftest.py` with the candidate code + constraints + a small set of edge inputs (empty list, single element, extremes). The script returns `{passed, failed, errors, sloc, import_violations}`.
   - If any check fails: read the error, fix the code, retry (up to 3 rounds).
4. **Write the result** by running `scripts/run.py` with the **`terminal` tool** (not a
   background/process tool), passing the final `{task_id, code, loc, self_test_results, rationale,
   confidence}`. `run.py` **writes the result file** (`$AIASE_RESULT_PATH`, else `./aiase_result.json`)
   and prints `written ok -> <path>`. **You do NOT need to print or repeat any JSON in the
   conversation** — the grader reads the file, not your message.

> **Passing the payload (quote-safe):** the `code` string is full of quotes, which collide with a
> single-quoted shell argv. Both `selftest.py` and `run.py` read the payload from **stdin**, so use a
> **quoted heredoc** — no escaping needed. Use the directory Hermes reports as `[Skill directory: ...]`:
>
> ```bash
> python3 <skill_dir>/scripts/run.py <<'JSON'
> {"task_id":"task_042","code":"def f(x):\n    return 'ok'\n","loc":2,"self_test_results":{"passed":1,"failed":0},"rationale":"...","confidence":0.85}
> JSON
> ```
>
> The argv form (`python3 <skill_dir>/scripts/run.py '{...}'`) also works when the code has no single quotes.

## Pitfalls

- **Missing empty-input handling** — the most common Pairwise failure. Always test `[]` / `""` / `0`.
- **Off-by-one** in loops / slicing — test both endpoints (first, last) explicitly.
- **Forbidden imports** — `os`, `sys`, `subprocess` etc. The harness will flag them; don't import anything not strictly needed.
- **LoC limit** — `radon raw` counts source lines (excludes blank + pure-comment). The grader re-runs `radon` independently of your reported `loc`. Keep code lean.
- **No network / no filesystem outside cwd** in sandbox (see spec §2.3). Don't read files, don't call APIs.

## Verification

`scripts/run.py` writes the result file (`$AIASE_RESULT_PATH`, else `./aiase_result.json`) as a
single JSON **object** with:

- `task_id` (must equal input)
- `code` (string, valid Python defining `entry_function`)
- `loc` (integer — what your harness measured)
- `self_test_results` (object with `passed` and `failed` counts at minimum)
- `rationale` (string)
- `confidence` (number in `[0.0, 1.0]`)

The grader reads that file, drops `code` into the sandbox and runs hidden tests. The file must
exist and be valid JSON; no result file = the scenario scores 0. Nothing needs to be printed in
the conversation.
