---
name: text2sql-Azure0413
description: Convert a natural-language question + SQLite schema into a verified read-only SQL query, then write the result via scripts/run.py (file-based output contract). AIASE 2026 Basic Track.
version: 2.0.0
metadata:
  hermes:
    tags: [sql, text2sql, data, aiase-2026]
    category: data
    requires_toolsets: [terminal]
---

# Text2SQL Skill (Basic Track)

## When to Use

When the user sends a JSON payload with `question`, `db_schema` (SQLite DDL), and optional `task_id` + `dialect`. The skill must produce a single read-only SQLite query whose result on the hidden DB matches the gold answer under bag equality.

Trigger example:

```
/text2sql-<your_github_id> {"task_id":"task_nl2sql_017",
  "question":"List the names of all students who scored above 90 ...",
  "db_schema":"CREATE TABLE Students(...); ...", "dialect":"sqlite"}
```

## Procedure

1. **Parse** the input payload. Extract `task_id`, `question`, `db_schema`, `dialect`.
2. **Plan** the SQL. Identify the relevant tables, JOIN keys, filters, aggregations. (See `## Pitfalls`.)
3. **Draft** a single SQLite read-only SQL statement.
4. **Validate** the SQL with `scripts/validate_sql.py` (payload `{"db_schema": <the input db_schema verbatim>, "sql": <your draft SQL>}`; the key `db_schema` or `schema_ddl` both work). It returns `{ok: bool, error: str}`.
   - If `ok=false`, read the error and **retry up to 3 times**, fixing the issue (typo, missing column, wrong alias…). After 3 failures, proceed with the best draft and lower `confidence`.
5. **Write the result** by running `scripts/run.py` with the **`terminal` tool** (not a background/process tool), passing the final `{task_id, sql, rationale, confidence}`. `run.py` **writes the result file** (path from `$AIASE_RESULT_PATH`, else `./aiase_result.json`). **You do NOT need to print or repeat any JSON in the conversation** — the grader reads the file, not your message. Use the skill directory that Hermes reports as `[Skill directory: ...]`:

   ```bash
   python3 <skill_dir>/scripts/run.py <<'JSON'
   {"task_id": "task_nl2sql_017", "sql": "SELECT DISTINCT s.name FROM Students s WHERE s.dept = 'CS'", "rationale": "...", "confidence": 0.82}
   JSON
   ```

   On success it prints `written ok -> <path>`. That's the whole final step.

### How to pass the payload (quote-safe — important)

SQL string literals use **single quotes** (`WHERE title = 'AI Foundations'`), which collide with a
single-quoted shell argv and make the shell fail *before* the script runs. **Both scripts accept the
payload on stdin**, so use a **quoted heredoc** — no escaping needed, single quotes inside the SQL are
safe:

```bash
python scripts/validate_sql.py <<'JSON'
{"db_schema": "CREATE TABLE Courses(cid INT, title TEXT);", "sql": "SELECT cid FROM Courses WHERE title = 'AI Foundations'"}
JSON
```

```bash
python scripts/run.py <<'JSON'
{"task_id": "task_nl2sql_017", "sql": "SELECT DISTINCT s.name FROM Students s WHERE s.dept = 'CS'", "rationale": "...", "confidence": 0.82}
JSON
```

The plain argv form (`python scripts/run.py '{...}'`) also works, but only when the SQL has no single
quotes. **When the SQL contains any `'`, always use the heredoc form above.**

## Pitfalls

- **Many-to-many JOINs without DISTINCT** → duplicate rows. The grader uses bag (multiset) equality, so duplicate rows fail. If the question semantically asks for a set ("list the students who ..."), use `DISTINCT`.
- **Column / table names** must exist in the given schema. `validate_sql.py` uses `EXPLAIN` against an in-memory DB built from the DDL; references to nonexistent columns will fail there.
- **Dialect**: always SQLite. No window functions, no CTE / `WITH`, no recursive queries (regardless of what dialect the LLM "feels like" using). See spec §2.2.
- **Single statement**: exactly one query, no semicolon-separated multiples.
- **Read-only**: no `INSERT` / `UPDATE` / `DELETE` / DDL.
- **task_id** in your output must equal the input `task_id`. The grader rejects mismatches.
- **Payload quoting (the #1 failure)**: SQL string literals use **single quotes** (`WHERE title = 'X'`,
  the SQLite standard), which collide with a single-quoted shell argv and make the shell fail before the
  script runs. **Use the quoted-heredoc form** (see "How to pass the payload" above) for any SQL that
  contains `'` — the heredoc body is literal, so no escaping is needed and `task_id` is never lost.

## Verification

`scripts/run.py` writes the result file (`$AIASE_RESULT_PATH`, else `./aiase_result.json`) as a
single JSON **object** with:

- `task_id` (must equal input)
- `sql` (single read-only SQLite query)
- `rationale` (string)
- `confidence` (number in `[0.0, 1.0]`)

The grader reads that file and runs the `sql` on the hidden DB, comparing the result set to the
gold answer under **bag (multiset) equality**. The file must exist and be valid JSON; no result
file = the task scores 0. Nothing needs to be printed in the conversation.
