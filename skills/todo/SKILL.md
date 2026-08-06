---
name: todo
description: Use when the user asks to "ideate on an idea", "refine an idea", "brainstorm", "write a spec", or "create a specification". Idea -> spec authoring that precedes tracked work; all TODO tracker actions (create/claim/implement/complete/defer/batch/...) belong to the `todo-db` skill.
version: 0.7.0
tools: Bash, Read, Edit, Write, Task
---

# Idea to Spec

Use this skill for thinking work that happens before you create a TODO. It does not write to the tracker.

## Purpose

Turn a rough idea into a clear spec. The `todo-db` skill owns all tracker state.

## Actions

| Action | When to use it | Guide |
|---|---|---|
| `ideate` | You need to refine or brainstorm an idea | `references/ideate.md` |
| `spec` | You need to write a spec | `references/spec.md` |
| `help` | You need the action list | This table |

Read the guide in the Read column before you act.

## Handoff

When the spec is agreed, switch to `todo-db`: run `todo create` (or create from spec). Do not write TODO state to files. The database is the record.
