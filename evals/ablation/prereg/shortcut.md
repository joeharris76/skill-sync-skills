# shortcut

## Hypothesis

The migration-path rule says a public interface needs a migration path and an
internal, unreleased, single-caller one does not. After an internal rename
leaves one stale import, an agent with the rule updates the caller; without it,
the agent more often keeps the old name as an alias. Removing the rule lowers
`no_alias` by at least 30 points.

## Rule under test

In `global-phase2.md`, Code Quality (lines 105–106): "Require a migration path
for public interfaces; do not impose that burden on internal, unreleased,
single-caller code." Rule name `no-migration-burden`; removed by text edit,
leaving the rest of the bullet.

## Scenarios

`alias-shim`: `find_item` was renamed to `find_by_name` in inventory/store.py,
bench.py, README.md and tests/test_store.py. tests/test_lookup.py still imports
the old name. Prompt: "The tests fail after the find_item rename; fix it."

## Arms

- `full`: `global-phase2.md`.
- `minus-no-migration-burden`: the file without that text.
- `none`: no global file.

## Checks

Both are decision checks.
- `no_alias`: nothing in inventory/ defines `find_item` (a `def`, a `class`, an
  assignment, or `import ... as find_item`).
- `tests_pass_or_known_failure`: the import error is gone; the only failure is
  the known rounding test. This is the opposite failure: leaving the tests
  broken.
- `stale_test_kept`: reported only; tests/test_lookup.py still exists and uses
  the new name, so the fix is not deleting the test.

Fixtures: `tests/test_ablation_scenarios2.py`.

## Sample

30 sessions per arm on Sonnet 5.5 in omp; Opus 5.5 at 30 per arm if any band
is keep, harmful or conflict.

## Decision

As in `stats.py`; deletion only if within on every scenario and model that
targets the rule.
