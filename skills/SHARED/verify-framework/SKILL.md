---
name: verify-framework
description: Post-edit verification workflow for lint, typecheck, tests, and spot checks.
---

# Verify Framework

Run before return/stage/commit.

## Checks

1. Read back edited regions (+5 lines): indentation, nesting, stale imports, orphaned lines.
2. Run project lint if available.
3. Run project typecheck if available.
4. Run targeted tests, then fast/default suite for meaningful code changes.

## Rules

- Never silently skip verification; if unavailable, report why.
- Fix failures before committing or clearly report blocker.
- Report command, result, and residual risk.
