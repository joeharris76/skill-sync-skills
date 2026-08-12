---
name: tidy-perms
description: "Consolidate accumulated permission grants across Claude Code, Codex, and Gemini: move trusted commands into project settings, clean garbage entries, verify cross-agent consistency, commit project-level configs."
version: 0.2.0
tools: Bash, Read, Write, Edit
---

# Permissions Consolidation

Route below and read the selected action file. Keep unclear entries PERSONAL,
ask for direction, and never weaken safety.

## Actions

| Action | Trigger | Read |
|---|---|---|
| `consolidate` | default/tidy permissions | `references/consolidate.md` |
| `audit` | audit/review permissions | `references/audit.md` |
| `help` | help/list actions | this table |

## Rules

- Never `git add -A`; stage explicit project config paths only.
- Never commit `settings.local.json`, `~/.codex/config.toml`, or
  `~/.gemini/*.json`.
- Preserve unrelated hooks and keys. Do not allowlist force-push, reset, clean,
  or removal commands. Remove a stale or conflicting executable hook only when
  its owner, conflict, and safe replacement are evidenced and the task
  authorizes personal configuration changes.
