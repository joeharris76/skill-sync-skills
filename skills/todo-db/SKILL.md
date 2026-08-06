---
name: todo-db
description: Use when the user asks to "create a TODO", "show TODO items", "manage TODOs", "prioritize TODOs", "top N most important todos", "rank the backlog", "what should we work on", "implement a TODO", "implement a batch of TODOs", "batch implement TODOs", "complete a TODO", "cleanup TODOs", "review TODO quality", "claim a TODO", "what's ready" / "ready queue", "defer this work", "promote a deferral", "dismiss a deferral", "block"/"unblock a TODO", "create TODOs from a spec", or "todo stats". The production database-backed tracker; all tracker state lives in the shared DB and flows through the `todo` CLI (except skill-only analysis actions such as prioritize).
version: 0.4.0
tools: Bash, Read, Edit, Write, Task
---

# TODO Tracker

## Purpose

Use this skill to manage TODO items in the shared database. The database is the only record. Do not write tracker state to files.

## How to run commands

Use `_project/scripts/todo`. Check that the wrapper supports the command you need:

* Run `_project/scripts/todo --help` and confirm the subcommand appears.
* If the subcommand is missing, report the gap and stop.

`prioritize` has no CLI command. It is a skill-only analysis. Follow `references/prioritize.md` and use only the inspect commands it lists.

Put global flags before the subcommand: `todo --db <path> --actor <name> <command>`.

Exit code 2 means a general failure. Exit code 4 means the hosted database rejected your credentials. When you get exit code 4, stop all writes, run `todo doctor`, and show the error. Some wrappers try once to refresh the token before they return exit code 4.

The `--help` output for the command you chose is the full contract.

## Actions

| Action | Guide |
|---|---|
| `bootstrap`, `init`, `doctor` | `references/bootstrap.md` |
| `ready`, `claim`, `start`, `done`, `defer`, `check-scope`, `verify`, `complete`, `promote`, `dismiss` | `references/implement.md` |
| `create`, `update`, `list`, `show`, `stats`, `deps`, `export`, `block`, `unblock`, `release`, `sweep-stale`, `drop` | `references/queries.md` |
| `prioritize` — skill-only, no CLI command | `references/prioritize.md` |
| `lint` | `references/review.md` |
| `finding candidates`, `finding triage`, `finding sync`, `finding promote` | `references/implement.md` |
| `batch` — a set of related TODOs | `references/batch.md` |

`todo ready` and `todo stats` may print a one-line warning on stderr when there are untriaged findings (open findings or unsynced drafts). The warning does not affect stdout. When you see it, run `todo finding candidates` to triage. The warning is silent when there are no findings.

## Rules

* Follow the guide you selected. Commit only through `SHARED/change-framework/SKILL.md`.
* Never write tracker state to files by hand. `TODO_DB_URL` can set the hosted database. The CLI never prints its connection string.
