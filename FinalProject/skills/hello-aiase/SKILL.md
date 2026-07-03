---
name: hello-aiase
description: Minimal smoke-test skill — echoes a greeting in the AIASE 2026 output contract. Use to verify the Hermes ↔ LiteLLM ↔ skill pipeline is wired up correctly.
version: 1.0.0
metadata:
  hermes:
    tags: [smoke-test, aiase-2026]
    category: utility
---

# Hello AIASE — Smoke Test

## When to Use

When the user invokes `/hello-aiase` with a JSON payload like `{"name":"world"}`. Use this skill to confirm Hermes can:

1. discover and load this skill,
2. invoke the script under `scripts/` with the `terminal` tool,
3. have that script **write the result file** (file-based output contract).

This skill performs **no LLM reasoning** — it just echoes structured input. If `/hello-aiase` works end-to-end (a result file is written), the rest of your AIASE 2026 setup is wired correctly.

## Procedure

1. Take the entire JSON payload from the user message verbatim (it should be an object; if missing, default to `{}`).
2. Invoke `scripts/run.py` with the **`terminal` tool**, passing the JSON payload as a single argv string, e.g.:

   ```
   python3 <skill_dir>/scripts/run.py '{"task_id":"t","name":"world"}'
   ```

3. The script **writes the result file** (`$AIASE_RESULT_PATH`, else `./aiase_result.json`) and prints `written ok -> <path>`. **You do NOT need to print any JSON in the conversation** — the grader reads the file.

## Pitfalls

- Do not paraphrase or re-print the result — the grader reads the result file, not your message.
- Do not call the LLM to "improve" the greeting — this skill is intentionally deterministic.

## Verification

- `scripts/run.py` writes the result file as a single JSON **object** with fields `ok=true`, `skill="hello-aiase"`, and `echo=<the input>`.
- If input contains `task_id`, the written `task_id` must equal the input `task_id`.
