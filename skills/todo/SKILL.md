---
name: todo
description: Use when the user asks to "create a TODO", "manage TODOs", "show TODO items", "prioritize TODOs", "implement a TODO", "review TODOs", "complete a TODO", "cleanup TODOs", "create TODOs from spec", "initialize TODO system", "ideate on an idea", "refine an idea", "write a spec", or "create a specification".
version: 0.4.0
tools: Bash, Read, Edit, Write, Task
---

# TODO Workflow

YAML TODO management with dependency graphs, indexes, and implementation guardrails.

## Paths And Commands

Resolve paths from `todo.config.yaml`, else `_project/TODO` and `_project/DONE` at git root. Indexes live under `_indexes/` and are generated, never hand-edited.

```bash
TODO_CLI="uv run --project ~/.claude/tools/todo todo-cli"
TODO_VALIDATE="uv run --project ~/.claude/tools/todo todo-validate"
TODO_INDEX="uv run --project ~/.claude/tools/todo todo-index"
```

## Actions

| Action | Trigger | Contract |
|---|---|---|
| `init` | "initialize TODOs", "setup TODO system" | Bootstrap config, dirs, schema/template, indexes |
| `list` | "show TODOs", "list items" | Query items, stats, ready queue |
| `create` | "create TODO", "add item" | Create validated item(s) with work units and guardrails |
| `prioritize` | "prioritize", "rebalance" | Rebalance priorities using impact/deps/effort/time |
| `implement` | "implement TODO", "work on" | Execute ready work units with guardrails, tests, commits |
| `review` | "review TODO quality" | Score clarity, completeness, actionability, freshness, guardrails, work breakdown |
| `complete` | "mark complete", "finish TODO" | Move completed item to DONE and reindex |
| `cleanup` | "cleanup TODOs", "commit TODO changes" | Validate graph/schema, cleanup, commit |
| `from-spec` | "TODOs from spec", "parse requirements" | Convert spec into TODO YAML |
| `ideate` | "ideate", "refine idea", "brainstorm" | Diverge/converge on ideas, surface assumptions |
| `spec` | "write spec", "create specification" | Produce decision-ready spec before code |
| `help` | "help", "list actions" | Show actions |

## Hard Rules

- Write actions auto-cleanup after verification and commit/push through SHARED/commit-framework.md.
- Plain `review` is read-only under SHARED/review-protocol/SKILL.md.
- Implementation must read the TODO guardrails, research target code, respect `scope_limit`, test each work unit, mark work done, and commit incrementally.
- Use flat `work[]` with `needs` edges; inter-item dependencies go in `deps.needs`.
- See `references/structure.md` for schema, statuses, commands, and layout.

## Action Notes

- **Init:** create default config/dirs, copy schema/template, generate empty indexes.
- **List:** `$TODO_CLI list|stats|ready`; support priority/status/worktree filters.
- **Create:** parse title(s) or conversation; slug id; choose worktree/phase/priority/category; add `work[]`, `deferred[]`, optional `deps.needs`; for code work add specific `verification`, `must_preserve`, `approach`, and risk-only `anti_patterns`/`scope_limit`.
- **Prioritize:** ideal active distribution is Critical 0-2, High 3-5, Medium-High 5-10; update and reindex.
- **Implement:** confirm ready, get `$TODO_CLI next <slug>`, move planning -> active, implement ready units using SHARED/research/slicing/verify, run verification, `$TODO_CLI done`, commit changed files only.
- **Review:** grade 0-3 across clarity, completeness, actionability, freshness, guardrails, work breakdown; Required findings for vague verification, broad scope, missing dependencies, or legacy nested format.
- **Complete:** require all work done/no blockers, set `Completed` + date, `git mv` to DONE, reindex.
- **Cleanup:** `$TODO_CLI check-graph`, `$TODO_CLI cleanup`, `$TODO_VALIDATE --all`, `$TODO_INDEX`, commit TODO/DONE files.
- **From-Spec:** parse markdown/yaml/text into items and work units; support `--dry-run`; write planning items, validate, index.
- **Ideate:** restate as problem, ask only material questions, generate options, stress-test assumptions, recommend MVP/not-doing/open questions; save only after confirmation.
- **Spec:** state assumptions, define objective, commands, structure, style, tests, boundaries, success criteria, and review gate; save only after confirmation.
