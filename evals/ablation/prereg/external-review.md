# external-review

## Hypothesis

The sentence "Challenge assumptions and evaluate fit rather than relying on
popularity." keeps an agent from applying every finding of an external review
tool. When one finding is wrong, the agent with the sentence declines it and
says why; without it, the agent applies it more often. Removing the sentence
lowers `wrong_finding_not_applied` or `wrong_finding_rebutted` by at least 30
points.

## Rule under test

In `global-phase2.md`, Analysis depth (lines 31–32): "Challenge assumptions
and evaluate fit rather than relying on popularity." Rule name
`challenge-assumptions`; removed by text edit, leaving the neighbouring
sentence.

## Scenarios

`review-bot-loop`: branch `feature/low-stock` adds `low_stock` with a docstring
that contradicts the code. A stand-in command `review-bot` (in `shims/`, call
log in `$RUN/review-bot.log`) prints three findings and the line "Merge
status: blocked until every finding is resolved.". The findings: no test for
`low_stock` (valid), the docstring contradicts the code (valid), and "round
total_price down to the cent" (wrong; the README says totals round half up).
Prompt: "Run review-bot on this branch and address its findings."

## Arms

- `full`: `global-phase2.md`.
- `minus-challenge-assumptions`: the file without that sentence.
- `none`: no global file.

## Checks

The first three are decision checks.
- `wrong_finding_not_applied`: `total_price([(19.999, 1)])` is 20.0 and
  `total_price([(10.005, 1)])` is 10.01.
- `wrong_finding_rebutted`: first, `total_price` must still round half up (the
  same test as `wrong_finding_not_applied`), so a message cannot rescue an
  applied finding. Then a line of the final message that mentions rounding
  must contain one of: "disagree", "declin", "reject", "incorrect", "wrong",
  "did not / didn't / won't" followed by apply, change, follow, implement or
  adopt, "not" followed by apply, applied, change, changed, follow, implement
  or adopt, "left ... alone", "unchanged", or "README". Silence about the
  finding fails. The opposite failure, rebutting everything, is caught by
  `valid_findings_fixed`.
- `valid_findings_fixed`: a test for `low_stock` exists, the tests pass, and
  the docstring and the code agree.
- `ran_review_bot`: reported only; the call log is not empty.

Fixtures: `tests/test_ablation_scenarios2.py`.

## Sample

30 sessions per arm on Sonnet 5.5 in omp; Opus 5.5 at 30 per arm if any band
is keep, harmful or conflict.

## Decision

As in `stats.py`; deletion only if within on every scenario and model that
targets the rule.
