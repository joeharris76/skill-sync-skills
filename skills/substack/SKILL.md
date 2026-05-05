---
name: substack
description: "`auth`, `status`, `preview`, `draft`, `publish`, `schedule`, `update`, `suggest_tags`, `pending`, `fetch`, `sync`, `pull`"
---

Unified Substack workflow backed by the `letterops` MCP.

## Available Verbs

- `auth`: verify authentication and server access
- `status`: show local tracking state and optionally remote state
- `preview`: validate and render a markdown file without publishing
- `draft`: create a Substack draft from a markdown file
- `publish`: publish a file live now
- `schedule`: schedule a file for live publication
- `update`: update an existing draft without publishing
- `suggest_tags`: suggest tags for a draft
- `pending`: list locally changed files since last sync
- `fetch`: refresh remote state and local hashes without pulling content
- `sync`: push local tracked changes to Substack
- `pull`: pull remote changes to local files

> **Commit rule**: After successful write actions, run Commit before returning.

## Global Rules

- Use MCP tool names as the action names. Do not invent higher-level aliases.
- Prefer read-only checks first: `auth`, `status`, `preview`, `pending`.
- Run dry-run mutations before any execute step whenever the MCP supports it.
- After publish or schedule, use `fetch`, not `pull`, to refresh state.
- Never pull into `_blog/published/` without explicit user review of the dry-run output.
- If a Substack action edits local/state files, commit via SHARED/commit-framework/SKILL.md before returning.
- If an action is read-only or leaves the worktree unchanged, do not create a commit.

## Routing

- User asks to preview a post: use `preview`
- User asks to create or refresh a Substack draft: use `draft` or `update`
- User asks to publish now: use `publish`
- User asks to schedule publication: use `schedule`
- User asks what changed or what is tracked: use `status` or `pending`
- User asks to refresh remote state only: use `fetch`
- User asks to push local changes: use `sync`
- User asks to bring remote changes down locally: use `pull`

## Preconditions

- All tools read config from `_project/substack/config.yaml` automatically through `LETTEROPS_CONFIG`.
- Paths may be repo-relative or absolute.
- Published markdown files under `_blog/published/` are the local source of truth.

## `auth`

Use `mcp__letterops__auth(test=true)` to verify credentials and connectivity before a live operation or when troubleshooting access.

## `status`

Use `mcp__letterops__status` to show tracking state.

- Add `remote: true` when the user wants the remote view too.
- Use this first when the user asks for "what is synced?" or "what is the current state?"

CLI fallback:
- `make tools-run CMD='status --remote'`

## `preview`

Use `mcp__letterops__preview` with `file_path` to validate structure and show the rendered block summary without creating a draft or publishing.

Steps:
1. Read the target file.
2. Run preview.
3. Show validation results and parsed structure.
4. If there are errors, suggest fixes before any draft or publish action.

CLI fallback:
- `make tools-run CMD='preview <file_path>'`

## `draft`

Use `mcp__letterops__draft` to create a Substack draft from a markdown file.

Steps:
1. Preview first.
2. Run draft in dry-run mode if supported by the current tool invocation.
3. Ask for confirmation before `execute: true`.
4. Optionally set audience and tags.
5. Return the draft URL and post ID.
6. Commit local/state file changes via SHARED/commit-framework/SKILL.md.

CLI fallback:
- `make tools-run CMD='draft <file_path> --execute'`

## `update`

Use `mcp__letterops__update` to update an existing draft without publishing it.

- This is for draft lifecycle management, not sync reconciliation.
- Preview first if the user has not recently validated the file.
- Commit local tracking changes via SHARED/commit-framework/SKILL.md.

## `suggest_tags`

Use `mcp__letterops__suggest_tags` with `file_path` to generate tag recommendations before drafting or publishing.

## `publish`

Use `mcp__letterops__publish` for immediate live publication.

Steps:
1. Preview first.
2. Ensure the user explicitly confirms live publication.
3. Run dry-run if available, then `execute: true` with `confirm_live: true`.
4. After publish, run `fetch` to refresh remote state.
5. Commit `fetch`/state changes via SHARED/commit-framework/SKILL.md.

CLI fallback:
- `make tools-run CMD='publish <file_path> --execute --confirm-live'`

## `schedule`

Use `mcp__letterops__schedule` to publish at a specified ISO datetime.

Steps:
1. Preview first.
2. Confirm the schedule timestamp with the user.
3. Run `execute: true` with `confirm_live: true`.
4. After scheduling, run `fetch`.
5. Commit `fetch`/state changes via SHARED/commit-framework/SKILL.md.

CLI fallback:
- `make tools-run CMD='schedule <file_path> "<ISO_DATETIME>" --execute --confirm-live'`

## Audience Rules

Free: open source deep dives, methodology, history series, feature series
Paid: cloud platform benchmarks, large-scale benchmarks (SF1000+)

Always confirm audience with the user before `draft`, `publish`, or `schedule` when the audience is not explicit in the file metadata.

## `pending`

Use `mcp__letterops__pending` to list local files changed since the last recorded sync state.

CLI fallback:
- `make tools-run CMD='pending'`

## `fetch`

Use `mcp__letterops__fetch` to refresh remote state and local hashes without pulling remote content into local markdown files.

- Prefer this after `publish` or `schedule`.
- Prefer this when state hashes are stale but local content should remain authoritative.
- Commit tracked state changes via SHARED/commit-framework/SKILL.md.

CLI fallback:
- `make tools-run CMD='status --remote'`

## `sync`

Use `mcp__letterops__sync` to push local tracked changes to Substack.

Steps:
1. Show `status` and `pending` first.
2. Run dry-run first.
3. Ask whether the user wants one-way push or bidirectional sync.
4. If approved, run with `execute: true`.
5. Commit sync state changes via SHARED/commit-framework/SKILL.md.

Conflict handling for bidirectional sync:
- `skip`: report conflicts, take no action
- `keep-local`: push local, overwrite remote
- `keep-remote`: pull remote, overwrite local
- `newest-wins`: compare timestamps and choose the most recent

CLI fallback:
- `make tools-run CMD='sync --dry-run'`
- `make tools-run CMD='sync --execute'`
- `make tools-run CMD='sync --bidirectional --on-conflict skip --dry-run'`
- `make tools-run CMD='sync --bidirectional --on-conflict skip --execute'`

## `pull`

Use `mcp__letterops__pull` to bring remote changes into local files.

Pull modes:
- Specific tracked file via `file_path`
- Remote-only post via `post_id` and `output_path`
- All remote changes via `pull_all: true`

Pull safety rules:
- Never run pull with `execute: true` against files under `_blog/published/` unless the user has reviewed the dry-run and explicitly approved it.
- Always run pull in dry-run mode first.
- If pull shows changes to `_blog/published/`, stop and ask the user before proceeding.
- When the real need is only state refresh, use `fetch` instead of `pull`.
- Commit pull changes via SHARED/commit-framework/SKILL.md.

## Recommended Flow

1. Read-only checks first:
   - `auth`
   - `status`
   - `preview`
2. Dry-run mutations:
   - `draft`
   - `publish`
   - `sync`
3. Execute after user review:
   - `draft`
   - `publish`
   - `schedule`
   - `sync`
