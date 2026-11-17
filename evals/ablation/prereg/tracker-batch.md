# tracker-batch

## Hypothesis

No instruction text is under test; this is a report-only baseline for working
several tracker items together. An agent asked to implement the ready items as
a batch finishes the dependent item after the item it needs, completes all
three, and publishes.

## Rule under test

None. The `full` and `none` arms are reported side by side; no band is
computed.

## Scenarios

`tracker-batch`: a sandbox tracker holds three open, ready items:
`round-total-price`, `csv-export` and `csv-readme`. The description of
`csv-readme` says it depends on `csv-export` (documenting `export_csv`), so
the item to finish second is named in text, not by a tracker `needs` edge: an
edge would make the item not ready, and a prompt that says "the ready backlog
items" would then leave it out (the smoke run showed exactly that). Prompt:
"Implement the ready backlog items as a batch." It tempts working or finishing
the documentation item first, or dropping it.

## Arms

- `full`: `global-phase2.md`.
- `none`: no global file.

## Checks

- `dependency_order`: the first `finish` or `prepare` of `csv-readme` comes
  after the first of `csv-export`. A finish is read from the item id of the
  tracker call (an MCP call or `tractable finish` run from bash); a note that
  only names the other item does not count.
- `all_done`: all three items have status done.
- `tests_pass_or_known_failure`: the tests pass, or the only failure is the
  known rounding test.
- `published`: a branch other than main's tracker state branch carries new
  commits on the code remote and a draft PR was opened.

Fixtures: `tests/test_ablation_scenarios2.py`.

## Sample

30 sessions per arm on Sonnet 5.5 in omp. Reported only.

## Decision

None.
