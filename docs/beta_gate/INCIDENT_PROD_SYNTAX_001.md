# INCIDENT PROD-SYNTAX-001 — production outage, 2026-08-08

**Severity:** total outage. Gunicorn workers exited 3 in a crash loop; no HTTP
port ever opened; the service never booted.

## Cause

`routers/hearing_cc.py` built its cross-exam prompt with the context block
inline inside an f-string:

```python
f"...{("\n" + case_context_blok + "\n...\n") if case_context_blok else ""}"
```

A backslash inside an f-string **expression** is a `SyntaxError` on Python
3.11; it only became legal in 3.12 (PEP 701).

| Environment | Python | Result |
|---|---|---|
| local dev | 3.13 | parses fine, 3,500 tests pass |
| production | 3.11 (`Dockerfile`, `runtime.txt`) | **cannot import the module** |

Introduced 2026-08-06 by `8bf3d46` (Tau-006 Canonical Context Factory pilot).
Not introduced by the credit-system work; it surfaced now because this is when
that code first reached a deploy.

## Why no test caught it

Every test ran on the local interpreter. Nothing in the repository ever
compared local syntax against the **deployment target's** grammar. This was
not a coverage gap — a test of this code would have passed too, on 3.13.

`ast.parse(feature_version=(3,11))` does **not** help: verified, it reported
0 problems on the very file that was crash-looping production. CPython's
f-string tokenizer changed in 3.12 and `feature_version` does not restrict it.

## Fix

`5888d5a` — expression hoisted into `_ctx_prompt_blok` above the f-string, so
the expression part contains no backslash. Valid on 3.11 and 3.13 alike.
Repo-wide scan confirmed this was the **only** such site.

## Permanent guard

`tests/test_python311_production_compat.py` (5 tests, runs every suite):

- no backslash inside any f-string expression, repo-wide — detected by walking
  the AST and inspecting each expression's **source text**
- every module parses
- no PEP 695 type-parameter syntax (`def f[T]`, `class C[T]`, `type X =`) —
  also 3.12+ only
- `Dockerfile`/`runtime.txt` still pin 3.11, so the guard cannot silently
  protect the wrong target
- regression pin on the exact site that caused the outage

## Recovery

`GET /health` returns `200 {"status":"ok","pid":7,"redis":true,"workers":1}`
on both `vindex-ai.onrender.com` and `vindex.rs`.

## Follow-up (recommended, not done here)

Add a CI step that byte-compiles the tree on **python:3.11** — the same image
production uses. A guard written in the local interpreter can only catch
patterns someone thought to encode; compiling on the target catches the class.
