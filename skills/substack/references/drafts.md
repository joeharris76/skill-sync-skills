# Draft Actions

## `draft`

Preview first, then run `mcp__letterops__draft` from the markdown file. Use a
dry-run when supported, ask before `execute: true`, optionally set audience and
tags, return the draft URL/post ID, and commit local/state changes.

## `update`

Use `mcp__letterops__update` for an existing draft without publishing. Preview
if the file was not recently validated, then commit local tracking changes.

## `suggest_tags`

Use `mcp__letterops__suggest_tags` with `file_path` before drafting or
publishing.

Audience: free for open-source deep dives, methodology, history, and feature
series; paid for cloud-platform or SF1000+ benchmarks. Confirm audience before
`draft`, `publish`, or `schedule` when file metadata does not specify it.
