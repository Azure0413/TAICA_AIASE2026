---
name: open-semver-Azure0413
description: Given two versions of a Python module, decide the required SemVer bump (major/minor/patch) by deterministic AST analysis of the public-API surface, draft a changelog, and write the result via scripts/advise.py (file-based output contract). AIASE 2026 Open Track.
version: 2.0.0
metadata:
  hermes:
    tags: [semver, versioning, ast, changelog, verifiable, aiase-2026]
    category: code
    requires_toolsets: [terminal]
---

# SemVer Advisor Skill (Open Track)

Decide whether a code change is a **major**, **minor**, or **patch** release under
[Semantic Versioning](https://semver.org), and draft a changelog. The version decision is **not**
left to the LLM's intuition: `scripts/classify.py` extracts each version's **public-API surface**
with Python's `ast` and applies a fixed rule set, so the answer is deterministic and reproducible.
The LLM's job is to (1) confirm/relay that verdict and (2) write a clear human-readable changelog.

This is the course's *deterministic-shell-wrapping-probabilistic-core* pattern: the **bump** is the
deterministic shell (AST rules), the **changelog prose** is the probabilistic core (LLM).

## When to Use

When the user sends a JSON payload with `old_code` (the previous version's full Python source),
`new_code` (the new version's full source), and an optional `task_id`. The skill must return the
required SemVer `bump` plus a `changelog` draft.

Trigger example:

```
/open-semver-Azure0413 {"task_id":"semver_001",
  "old_code":"def add(a, b):\n    return a + b\n",
  "new_code":"def add(a, b, c=0):\n    return a + b + c\n"}
```

## SemVer rule (contract — this is exactly what the grader checks)

**Public symbol set**: module-level functions and classes whose name does not start with `_`; for
each public class, its methods not starting with `_`, plus `__init__`.

**Bump (old → new), first match wins:**

- **major** — a previously-valid call could break: a public symbol is removed; a public class loses
  a public method; or a function/method signature changes incompatibly (an accepted parameter name
  disappears, the required-argument count increases, or `*args`/`**kwargs` is removed).
- **minor** — backward-compatible addition (and no major change): a new public symbol is added; an
  existing function/method gains a new **optional** parameter; or `*args`/`**kwargs` is newly added.
- **patch** — none of the above: the public API surface is unchanged (only bodies or private
  `_`-prefixed symbols changed).

## Procedure

**One shot — do exactly this, nothing more.**

This skill is deterministic: a script computes the bump **and** the changelog **and writes the
result file**. Your only job is to run **one** command with the user's payload. **Do not decide the
bump yourself, do not add or change any field, do not re-print the JSON in the conversation.**

1. Run exactly one command with the **`terminal` tool** (not a background/process tool), passing the
   user's input JSON payload verbatim. Use the directory Hermes reports as `[Skill directory: ...]`.

   **Preferred (quote-safe):** `old_code`/`new_code` are Python source full of quotes; pass the
   payload on **stdin via a quoted heredoc** so no escaping is needed:

   ```bash
   python3 <skill_dir>/scripts/advise.py <<'JSON'
   {"task_id":"semver_001","old_code":"def f(a):\n    return a\n","new_code":"def f(a, b=0):\n    return a+b\n"}
   JSON
   ```

   The plain argv form also works (`advise.py` tolerantly recovers over-escaped `\n`/`\"`):

   ```
   python3 <skill_dir>/scripts/advise.py '<the user's input JSON payload, verbatim>'
   ```

   (In the argv form keep newlines inside the code as `\n` — a single backslash — not `\\n`.)

2. `advise.py` computes the final contract (`task_id`, `bump`, `changelog`, `rationale`,
   `confidence`) and **writes it to the result file** (`$AIASE_RESULT_PATH`, else
   `./aiase_result.json`), printing `written ok -> <path>`. **That is the whole job — you do NOT need
   to print or repeat any JSON in the conversation.** The grader reads the file, not your message.

> Advanced (optional): `scripts/classify.py '{"old_code":...,"new_code":...}'` returns just the
> raw `{bump, breaking, additive}` evidence if you want to inspect the API diff first. The bump is
> always whatever the script computes — never your own guess.

## Pitfalls

- **Don't decide the bump yourself.** `advise.py` computes it from the AST; you only relay. Adding an
  optional parameter *feels* like patch but is **minor**; renaming a public parameter *feels* minor
  but is **major** — the script gets these right, intuition often won't.
- **Don't re-print or hand-edit the result.** `advise.py` writes the final contract to the result
  file itself (file-based output) — you do **not** need to echo any JSON back in the conversation, and
  you must not add or change fields. The grader reads the file, not your message.
- **Newline escaping** — wrap the whole payload in single quotes; write newlines inside the code as
  `\n` (a single backslash), not `\\n`. (`advise.py` recovers from `\\n` anyway, but `\n` is correct.)

## Verification

`scripts/advise.py` **writes the result file** (`$AIASE_RESULT_PATH`, else `./aiase_result.json`)
as a single JSON **object** with:

- `task_id` (equals input)
- `bump` (string enum: `"major"` / `"minor"` / `"patch"`)
- `changelog` (string — auto-generated, names every changed public symbol)
- `rationale` (string)
- `confidence` (number in `[0.0, 1.0]`)

The grader reads that file. The deterministic evaluator (`scripts/evaluate.py`) recomputes the
authoritative bump from `old_code`/`new_code` and scores `bump_correct` (primary, non-gameable) plus
`changelog_coverage` (secondary). Because `advise.py` computes both the bump and a symbol-complete
changelog deterministically **and writes the file itself**, the skill scores correctly on **any**
model that can run one command — including the grader's held-out perturbed diffs. The file must exist
and be valid JSON; no result file = the scenario scores 0. Nothing needs to be printed in the
conversation. (`scripts/run.py` remains available as a plain file-writing wrapper if a payload is
assembled manually.)
