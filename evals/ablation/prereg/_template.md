# <experiment name>

Commit this file before the first scored run. Changing it afterwards voids the
runs made under the old text (`run.py report` drops them).

## Hypothesis

What the rule is expected to change, in one or two sentences.

## Rule under test

The exact text, with its file and section.

## Scenarios

Scenario ids in `scenarios2.py`, and the failure each one tempts.

## Arms

- `full`: the file as deployed when the phase began.
- removal arm: the file without the rule (`minus:<heading>` or `lines:<ranges>`).
- `none`: no global file.
- candidate rewording or mechanical replacement, if one is proposed.

## Checks

For each check: what passes, what fails, and its known-pass and known-fail
fixtures in `tests/test_ablation_checks.py`. Name the paired check for any
opposite failure mode.

## Sample

Sessions per arm (default 30) and models, in order.

## Decision

The band each outcome leads to, under the rule in `stats.py`: keep, reword,
delete (only if every scenario and model is within), or inconclusive (no
action).
