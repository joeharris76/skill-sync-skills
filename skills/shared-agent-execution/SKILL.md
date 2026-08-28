---
name: agent-execution
description: Select model tiers, map reasoning effort, and dispatch delegated work through native or external agent harnesses. Use when a workflow must choose an agent model or effort level, or launch a worker or independent reviewer; do not use for direct, undelegated tool calls.
---

# Agent Execution

Use this component when another skill delegates work and needs a consistent
model tier, reasoning effort, or agent harness configuration. The calling skill
continues to own task decomposition, authorization, workspace isolation, and
acceptance criteria.

## Model Tiers

Tiers describe operating roles, not absolute quality rankings. Match models to
task complexity and risk.

*Selection Rule*: Pick the tier here; take the exact identifier from the target
harness row in
[references/external-harnesses.md](references/external-harnesses.md). Default
reasoning effort to `medium`. Use maximum effort only for Tier 1 adversarial
review; use `low` for mechanical bulk work.

- **Tier 1: Strategic**
  - Models: `gpt-5.6-sol`, `claude-fable-5`, `grok-4.6`, `gemini-3.7-flash-high`
  - Usage: Strategic planning, architecture, high-risk tradeoffs, and final adversarial review.
- **Tier 2: Generalist**
  - Models: `gpt-5.6-terra`, `claude-opus-5`, `grok-4.5`, `gemini-3.7-flash-medium`, `muse-spark-1.2`
  - Usage: Management, decomposition, integration, investigation, and routine review.
- **Tier 3: Contributor**
  - Models: `gpt-5.6-luna`, `claude-sonnet-5`, `gemini-3.7-flash-low`, `gemini-3.7-flash-tiered`, `muse-spark-1.2-contributor`
  - Usage: Focused implementation, bounded research, bulk work, and parallel coverage.

## Reasoning Effort Reference

| Harness | CLI Flag / Option | Supported Values (Lowest to Highest) |
| :--- | :--- | :--- |
| **pi** | `--thinking <level>` | `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` |
| **claude** | `--effort <level>` | `low`, `medium`, `high`, `xhigh`, `max` |
| **muse** | `--reasoning-effort <EFFORT>` | `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `ultra` |
| **agy** | `--effort <level>` | `low`, `medium`, `high` |
| **grok** | `--reasoning-effort <EFFORT>` | `low`, `medium`, `high`, `xhigh` |
| **codex** | `-c model_reasoning_effort="<level>"` | `low`, `medium`, `high`, `xhigh`, `max`, `ultra` |
| **prime-agent** | `--thinking <level>` | `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` |

For `jcode`, `opencode`, `hermes`, `goose`, and `aider`, effort is selected via
model variants (e.g. `gemini-3.7-flash-tiered`, `:thinking` suffix) or provider
settings.

## Dispatch Rules

Use native host subagents by default. Assign an explicit role, bounded goal,
path constraints, permission scope, success criteria, and output contract.

Choose the dispatch mode from the delegated role:

- **Worker:** use a write-capable mode only within the authorized workspace or
  sandbox. Require the repository's narrowest proving check and explicit-path
  staging; never permit `git add -A`.
- **Reviewer:** use a separate dispatch that did not author the work. Prefer a
  hard read-only sandbox or tool allowlist. A plan mode is soft read-only and
  requires explicit findings-only instructions that forbid edits, commits,
  pushes, and other mutations.

Use an external or headless harness only when native delegation is unavailable
or cannot supply the required model, isolation, or read-only boundary. Then read
[references/external-harnesses.md](references/external-harnesses.md), select the
documented command for the role, and use it directly. If that command fails,
diagnose the actual failure then.

Headless dispatch may suppress interactive approval prompts only when write
scope is bounded by a sandbox, workspace flag, or dedicated worktree. Never add
flags that remove path or permission limits, including
`--permission-mode acceptEdits`, `--dangerously-skip-permissions`,
`--always-approve`, or `--yolo`.

The external harness reference contains the worker and reviewer commands, model
identifiers, and hard-versus-soft read-only classifications.
