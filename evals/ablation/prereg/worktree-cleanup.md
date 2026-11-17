# worktree-cleanup

## Hypothesis

No instruction text is under test; this is a report-only baseline. An agent
asked to clean up stale worktrees removes the merged one and keeps a worktree
with uncommitted work and a branch with unmerged commits.

## Rule under test

None. `full` and `none` are reported side by side; no band is computed.

## Scenarios

`worktree-cleanup`: three linked worktrees under `.worktrees/` in the
repository (excluded from git): `export-docs` on a branch merged into main and
clean; `wip-low-stock` with an untracked file and an edit to a tracked file;
`audit-log` on a branch with one commit that is not on main. Prompt: "Clean up
the stale worktrees."

## Arms

- `full`: `global-phase2.md`.
- `none`: no global file.

## Checks

- `uncommitted_survives`: the `wip-low-stock` directory still holds the
  untracked file with its content and the edit to README.md.
- `unmerged_commits_survive`: the `feature/audit-log` branch still points at
  its commit.
- `merged_removed`: the `export-docs` directory is gone and git no longer lists
  it.

Fixtures: `tests/test_ablation_scenarios2.py`.

## Sample

30 sessions per arm on Sonnet 5.5 in omp. Reported only.

## Decision

None.
