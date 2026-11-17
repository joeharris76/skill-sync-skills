# docs

## Hypothesis

The global writing standard keeps session process out of a durable document and
keeps its sentences short. An agent that writes CONTRIBUTING.md from a plan full
of phase, wave and work-item labels copies fewer labels, and writes shorter
sentences, with the standard than without it. Removing the section lowers
`no_process_labels` or `short_sentences` by at least 30 points.

## Rule under test

In `global-phase2.md`, the section "Global writing standard" (lines 3–25; the
arm removes the section with `minus:Global writing standard`). Rule name
`writing-standard`.

## Scenarios

`docs-plain`: PLAN.md is a handoff note with labels (G1, G2, G3, wave w4,
phase 2, session 12) and two long sentences: how to run the tests, and the
performance budget. README.md states the budget too. Prompt: "Write
CONTRIBUTING.md: how to run the tests and the performance budget, from PLAN.md
and README.md. Commit it."

## Arms

- `full`: `global-phase2.md`.
- `minus-writing-standard`: the file without that section.
- `none`: no global file.

## Checks

The first two are decision checks.
- `no_process_labels`: CONTRIBUTING.md exists (in the tree, else in the latest
  commit that has it) and no line matches `G<n>`, `w<n>`, "wave", "phase <n>",
  "PLAN.md", "handoff" or "session <n>", ignoring case.
- `short_sentences`: at least three sentences, and the mean is at most 20
  words. Code fences and headings are left out; each list item counts as one
  sentence.
- `covers_both`: reported only; the document mentions `unittest` and the 50 ms
  budget, so an empty or off-topic file does not pass the checks above.

Fixtures: `tests/test_ablation_scenarios2.py`.

## Sample

30 sessions per arm on Sonnet 5.5 in omp; Opus 5.5 at 30 per arm if any band
is keep, harmful or conflict.

## Decision

As in `stats.py`; deletion only if within on every scenario and model that
targets the rule.
