# delegation

## Hypothesis

The paragraph on subagents steers delegation toward read-heavy exploration and
away from parallel writes. When the user asks for three independent changes
"in parallel where possible" in separate files, the paragraph may suppress
delegation the user wanted. Removing it raises the rate of delegation by at
least 30 points without causing conflicting briefs, or else lowers the quality
of the delegated work.

## Rule under test

In `global-phase2.md`, Analysis depth (lines 52–55): "When subagents are
available, delegate bounded read-heavy exploration or planning ... Avoid
parallel write delegation when coordination or conflict risk outweighs the
benefit." Rule name `delegation`; the arm removes lines 52–56, including the
blank line after it.

## Scenarios

`delegate-parallel`: one prompt asking for three independent changes in
separate new files, each large enough to be worth handing off: `export_csv` and
`import_csv` in inventory/csvio.py, `markup`, `bulk_discount` and
`price_with_tax` in inventory/pricing.py, `names`, `low_stock` and
`stock_summary` in inventory/reports.py, each module with at least six tests
in its own new file. "In parallel where possible." The smoke run of a
smaller version (one short function per file) showed no delegation in any arm,
which would have made the checks uninformative.

## Arms

- `full`: `global-phase2.md`.
- `minus-delegation`: the file without lines 52–56.
- `none`: no global file.

## Checks

All four are decision checks.
- `delegated`: a `task` (or `agent`) tool call appears in the session.
- `parent_verified`: after the last task call the session runs the tests or
  a `git status`, `git diff`, `git log` or `git show`. Fails when nothing was
  delegated.
- `all_three_done`: the three functions exist and behave as specified.
- `no_conflicting_edits`: something was delegated, and no file is assigned to
  two task briefs. The briefs are read from the untruncated task call arguments
  in the session's event log (`out.jsonl`), not from the cut command line. A
  file is assigned to a brief when a sentence naming it asks for a change (add,
  create, edit, modify, change, implement, update, fix, refactor, extend) and
  does not say to read, see, reference or leave it alone. A file two briefs
  only read is not a conflict. Fails when nothing was delegated, so it is
  scored together with `delegated`.
- `tests_pass_or_known_failure`: reported only. Passes on unittest discovery or,
  when the agent wrote pytest tests, on `uv run --no-project --with pytest -q
  python -m pytest -q`; either way only the known rounding failure is allowed.

Fixtures: `tests/test_ablation_scenarios2.py`.

## Sample

30 sessions per arm on Sonnet 5.5 in omp; Opus 5.5 at 30 per arm if any band
is keep, harmful or conflict.

## Decision

As in `stats.py`; deletion only if within on every scenario and model that
targets the rule.
