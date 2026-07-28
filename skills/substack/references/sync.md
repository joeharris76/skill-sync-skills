# Sync Actions

## `sync`

Use `mcp__letterops__sync`. Show `status` and `pending`, dry-run first, ask
whether the user wants one-way push or bidirectional sync, then execute only
after approval. Commit sync state changes. Conflict modes are `skip`,
`keep-local`, `keep-remote`, and `newest-wins`; report skipped conflicts.
CLI fallbacks include `make tools-run CMD='sync --dry-run'` and
`make tools-run CMD='sync --execute'`.

## `pull`

Use `mcp__letterops__pull` for a tracked `file_path`, remote `post_id` plus
`output_path`, or `pull_all: true`. Dry-run first. If the dry-run changes
`_blog/published/`, stop for explicit review; never execute that pull without
it. Use `fetch` when only state refresh is needed. Commit pull changes.
