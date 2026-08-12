# Batch Implementation

Use `batch` to implement a named set of related TODOs in dependency order. One
call authorizes implementation, its required named branches and commits, PRs,
and conditional auto-merge only for that set. It does not authorize
out-of-scope work or bypass approval gates; do not request the same authority
for each item.

## Before you start

Run `todo doctor` through `_project/scripts/todo`. If unsupported, report the
skipped preflight. Fix failures before claiming an item.

If a command documents exit code 4 and returns it, stop the batch. The wrapper
may already have tried one token refresh.

1. Record stale tracker items and blockers in the ledger.
2. Show the authentication error and its documented recovery command.
3. Do not implement more work or open PRs while tracker writes fail.
4. After recovery, replay missed tracker writes before taking another item.

## Tracker commands

Use `_project/scripts/todo` for claims and leases (`claim`), worktrees and
branches (`start` and `done`), and completion and PRs (`complete --pr`). Rebuild
progress with `todo list`, `todo stats`, and `todo deps <id>`.

## Local ledger — batch bookkeeping only

Keep one local ledger for facts absent from the database:

- Deduplicated, dependency-sorted item order.
- Batch-local status: `pending`, `waiting`, `in_progress`, `in_review`,
  `pr_open`, `done`, or `blocked`.
- Blocker or wait reason.

Do not duplicate worktrees, branches, or PRs recorded by `start` and `complete`.
Store the ledger in an ignored scratch path or `.todo-batch/<slug>.yaml`. If
Git sees that path, add `.todo-batch/` to `.git/info/exclude`, not the committed
`.gitignore`. Never commit the ledger; read it first when resuming.

```yaml
batch: <slug>
order: [todo-a, todo-b]
items:
  todo-a: {status: pending, note: ""}
```

## Setup

1. Remove duplicate IDs and confirm each with `todo show <id>`.
2. Read each work order with `todo claim`, including scope, must-preserve notes,
   anti-patterns, verification, ready units, and deferrals. To preview without
   claiming, use `todo show <id> --json` and `todo deps <id>`.
3. Sort by `deps.needs`. Mark cyclic items `blocked` and continue.

## Scheduler

After a failure, make one focused retry. If it fails, mark the item `blocked`
and continue.

Repeat until every item is `done` or `blocked`:

1. Re-read the ledger. Refresh with `todo ready` and `todo deps`. If warned,
   triage findings with `todo finding candidates`; findings are not batch items.
2. Classify each non-terminal item (`ready` is derived, not stored):
   - `ready`: status is `pending`, every in-batch dependency is `done` and
     merged, and `todo ready` reports no external dependency.
   - `waiting`: a dependency PR, external dependency, CI check, or merge can
     still resolve this session.
   - `blocked`: the item is missing or malformed, has a cycle, failed its retry,
     or cannot resolve this session. Record why. For a hard tracker blocker,
     run `todo block <id> --reason ...`.
3. If a TODO is ready, implement it (see below).
4. If none are ready, mark ordinary pending CI as `waiting`. Monitor only a
   dependency gate that blocks another TODO. Announce the command, maximum time,
   log path, and stop condition, such as `gh pr checks`. A subagent may run and
   report a deterministic gate. Apply the retry rule to red batch-owned PRs.
   Not-ready means `waiting`, not `blocked`.

## For each ready TODO

1. Mark `in_progress` in the ledger.
2. For implementation, create a fresh linked worktree from the integration
   branch before editing. After its PRs merge, verify it is clean and remove
   that exact worktree under repository policy. Do not assume a retained pool.
   Refresh it if a dependency merged after creation.
3. Run `todo claim <id>` and follow the work order. For each work unit, run
   `todo start`, apply `SHARED/change-framework/SKILL.md` Section 1 before
   source-code edits, implement, then record evidence with `todo done`. Defer
   out-of-scope work with `todo defer`.
4. Run `todo check-scope <id>` and `todo verify <id> --run`.
5. Mark `in_review`. As internal implementation verification under
   `SHARED/review-protocol/SKILL.md` [REVIEW-AUTH-001], run the `code` skill
   review or apply its five axes. Fix valid Critical and Required findings.
   Apply Nit and Consider findings only when in scope. List skipped findings in
   the PR body. Re-verify and re-review after non-trivial fixes.
6. Commit through `SHARED/change-framework`, open one PR, then run
   `todo complete <id> --pr <n>` after resolving deferrals.
7. If another batch item needs the PR, mark `pr_open`. Enable auto-merge only
   when CI—not human approval—is the integration gate. Monitor until merged,
   then mark `done`. Otherwise mark `done` after PR creation and completion.

## Workers

Run one item at a time by default. Use one worker per TODO only when worker
sessions exist. The orchestrator retains ordering, the ledger, monitoring, and
the final report. Each worker returns `TODO`, `STATUS: done|pr_open|blocked`,
`PR`, `WORKTREE`, `BRANCH`, and `NOTES`.

## Final report

Report `TODO | PR # | status | note`, blockers, unblock steps, and the ledger
path. If items remain non-terminal, give the ledger path and tell the user to
rerun `batch` with the same inputs.
