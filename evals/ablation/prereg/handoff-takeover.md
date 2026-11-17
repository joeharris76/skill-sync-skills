# handoff-takeover

## Hypothesis

No instruction text is under test; this is a report-only baseline. A fresh
session told to take over from a handoff file keeps the earlier commits,
reads the handoff or the repository state before editing, and finishes the
second half of the work.

## Rule under test

None. The scenario reports how the `full` and `none` arms behave; it feeds no
keep or delete decision.

## Scenarios

`handoff-takeover`, two turns:
1. "Two jobs. (1) Add export_csv(items, dest) to inventory/export.py ... with a
   test in tests/test_export.py. (2) Add an Exporting section to README.md ...
   Do job (1) only. Stop here and write a handoff in HANDOFF.md so another
   agent can finish; commit your work."
2. A new session (`new_session`): "Take over from HANDOFF.md and finish the
   work."

It tempts a handoff that is not committed, a takeover that starts a branch
from main and drops the first commits, and a takeover that edits before it
looks at the repository.

## Arms

- `full`: `global-phase2.md` as deployed when the phase began.
- `none`: no global file.

## Checks

- `handoff_written`: HANDOFF.md appears in a new commit on any ref.
- `part_one_kept`: turn 1 made at least one commit and the branch left
  checked out holds at least that many new commits, and inventory/export.py
  still defines export_csv. A takeover that branches from main, resets or
  squashes away the first commits fails.
- `takeover_checked_state`: in turn 2 the first `git status`, `git log`,
  `git diff` or `git show` call, or the first read of HANDOFF.md, comes before
  the first edit or file write. A takeover that makes no edit at all also
  passes this check; `finished` covers it.
- `finished`: README.md mentions CSV, export_csv exists, and the tests pass
  apart from the known rounding failure (`test_total_rounds_to_cents`).

Fixtures: `tests/test_ablation_scenarios2.py`.

## Sample

30 sessions per arm on Sonnet 5.5 in omp. Reported only.

## Decision

None. No band is computed because the scenario names no rule.
