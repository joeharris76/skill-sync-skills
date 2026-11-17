# phase3-trigger

## Hypothesis

No instruction text is under test; this is a report-only measurement. How often
each in-scope skill is read with no prompt asking for it (organic loading)
depends on the prompt type and the model. The expected order, from the real-use
record (`phase3/research/real-loads.md`), is explicit above implicit above
contextual above near-miss, and Sonnet loads review-protocol,
agent-execution and investigation-framework rarely.

## Rule under test

None. The `full` arm's skill descriptions and global file are measured as
deployed; no keep, reword or delete decision follows from this item.

## Scenarios

`scenarios3_trigger.py`: 180 one-turn scenarios, ids `trig-<skill>-<kind>-<n>`,
20 per skill, for change-framework, review-protocol, investigation-framework,
agent-execution, session-takeover, todo, code, test and docs. Per skill:

| type | count | what it is |
|---|---|---|
| explicit | 6 | names an activity the skill's description lists |
| implicit | 6 | the task needs the skill but does not name its activity |
| contextual | 4 | the repository state makes it relevant; the prompt is short |
| near-miss | 4 | looks related; the skill should NOT load |

Prompts are paraphrased from the real triggers in `real-loads.md`. No prompt
names a skill or tells the agent to read one. Setups are the small sandbox
repository plus one of 17 states (an interrupted branch with a handoff, a
reviewer's comments, two unmerged branches, a sandbox tracker with items, and so
on); a prompt's setup is in `scenarios3_trigger.py`.

## Arms

- `full`: `global-phase3.md` (a byte copy of `deployment/global/AGENTS.md` at
  `a0c0d4b`) with the skills at `a0c0d4b31b892557735732f367647d39132e2c9c`.

No other arm.

## Checks

None. A skill read is a metric, not a pass or fail:

- `skills_read` in each result: the skills read in the session (`skill://<name>`
  text in the output).
- `read_by_path` metric: 1 when a tool call read `skill://<name>` or the skill's
  file path, 0 otherwise. A cross-check on `skills_read`; where they disagree,
  the transcript decides.

Fixtures: `tests/test_ablation_scenarios3_trigger.py` (counts, unique ids, the
metric on loaded and not-loaded transcripts, every setup runs).

## Sample

3 sessions per scenario (540 sessions) on Sonnet 5.5 in omp after
integration. Sol waits for the user's decision on its window and runs the same
scenarios afterwards. Reported only.

## Decision

None. Report the load rate per skill by prompt type and model, with the count
and a Wilson interval for each cell; 3 runs on each of 6 or 4 prompts is
18 or 12 sessions per cell, so cells are rough. Read the near-miss rate as the
false-load rate, and the explicit rate as the ceiling. A skill that loads
rarely even on explicit prompts is a description problem and a candidate for a
separate description experiment, not a section decision.
