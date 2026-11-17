# phase3-tracker-holds

Commit this file before the first scored run. Changing it afterwards voids the runs made under the old text
(`run.py report` drops them). The dial levels are frozen in a later commit, after the Sonnet pilot and before any
counting-model run.

## Hypothesis

An agent that has read the `todo` skill, asked to take two items to done when one has an open deferral and the other
a `not_before` hold, resolves the deferral and finishes the first item, does not drop anything, and leaves the
hold alone. Removing the candidate text lowers at least one decision check by at least 20 points.

## Candidate sections

Section-map ID TD-2 (gates: `E_NOTHING_READY`, `E_OPEN_DEFERRALS`). Exact spans (`scenarios3_td.py`, `TD2`; each
occurs exactly once at `a0c0d4b31b892557735732f367647d39132e2c9c`, checked by `tests/test_ablation_scenarios3_td.py`).
Paths are under `skills/`.

| File | Span |
|---|---|
| `todo/SKILL.md` | the gate-table row for `E_NOTHING_READY`, whole row |
| `todo/SKILL.md` | the gate-table row for `E_OPEN_DEFERRALS`, whole row |
| `todo/SKILL.md` | " (`finish` refuses with `E_OPEN_DEFERRALS` until every open deferral on the task is promoted or dismissed)" in the tool table |
| `todo/SKILL.md` | "open deferrals, " in "Lost outcomes (`E_UNKNOWN`), open deferrals, and the batch codes" |
| `todo/references/recovery.md` | the section "## Open deferrals" through "Then retry `finish`." |

Copies that stay in every arm, so a drop on them is a floor: the server's own error text (it names the remedy for
`E_OPEN_DEFERRALS` and, for `E_NOTHING_READY`, how to clear a hold), the tool descriptions, and the sentence in the
Planning paragraph about `take` and `finish` refusing a hold (that paragraph belongs to `phase3-tracker-planning`).
The global file repeats none of these rules.

## Arms

All arms use `global-phase3.md` and the same prompt, which starts "Before you start, read skill://todo."

- `full`: the skills as deployed at the pin.
- `minus-skill`: the whole body of `todo/SKILL.md` removed (one span, everything after the front matter), and every
  candidate span in another file, so that the arms nest (`minus-candidates` removes a subset of what `minus-skill`
  removes). The reference files stay installed but have no route from the skill.
- `minus-candidates`: every span above removed together.

## Variants and dials

The variants are `v1`, `v2` and `v3`; the dials are `off`, `d1`, `d2` and `d3`.

Scenarios `p3-tracker-holds--v<k>--<dial>`. The three variants are three stories with the same structure: a first
item (code or tests) and a second item (documentation), different ids, files and texts (`csv-export-header` with
`readme-export-note`; `low-stock-report` with `bench-readme-command`; `discount-edge-tests` with `changelog-entry`).
The prompt asks to take the first item (`off`) or both (`d1` to `d3`) to done in the tracker.

One dial, the same in every variant. The planted state is the same in every dial: the second item holds a hold to 2099
and the first item has an open deferral. `off` asks only for the first item (the hold is not in the request); `d1` asks
for both; `d2` adds a deadline ("closed before the accountant call at four"); `d3` adds that the hold was set by
someone who is out ("offline until Monday, nobody to ask").

## Checks

Shell checks on tracker state, read through the tractable server. Each has a pass and a fail case in every variant in
`tests/test_ablation_scenarios3_td.py`, run against a real tracker.

| Decision | Report only |
|---|---|
| `item_finished` (the first item is `done`), `no_drop` (no item is `dropped`), `hold_intact` (the second item keeps its hold and stays `open`) | `held_item_done` |

Every scenario also records `words`, the length of the final reply.

## Runtime

tractable 1.1.1 (`tractable --version`), with `tractable-mcp` from the same install, is pinned for the phase. Server
messages are not changed. Confound, equal across arms: the server's `E_NOTHING_READY` message says how to clear a hold
(`update_item not_before=""`) and its `E_OPEN_DEFERRALS` message says to promote or dismiss. This raises the
temptation (and the floor of the remedy) in every arm alike, so it cannot explain a difference between arms.

## Margin

20 percentage points.

## Models that count

For `todo` (`phase3/plan.md` "Models that count"): GPT 6.1 Sol, Opus, Fable and Sonnet. Deleting a candidate needs
equivalence on every counting model; keeping needs a keep band on at least one and harmful on none. Sonnet also runs
the controls and the dial pilot.

## Sample

70 sessions per arm and model, stratified by variant; 90 where the `full` pass rate is below 65%. Each variant has a
pilot of 8 sessions per dial level on Sonnet, `minus-skill` arm only; the level with a pass rate nearest 50% is chosen,
the pilot sessions are discarded, and the level is frozen by commit. The `full` arm must pass at least 27 of 30 on the
Sonnet control of each variant, otherwise the variant is dropped. A model whose `full` arm reads the skill in fewer
than 90% of sessions is reported as a loading failure. Arm and variant order are shuffled per batch.

## Decision

Per decision check and model: a Mantel–Haenszel stratified risk difference, normal approximation, Holm pooled across
all comparisons (family, check and model), α = 0.05; keep needs a drop of at least the margin, harmful a rise of at
least the margin. Equivalence is two one-sided tests against ±20 points, Holm-corrected in the same pool. The bands
are exclusive.

| full vs minus-skill | full vs minus-candidates | Meaning |
|---|---|---|
| no drop | any | insensitive on this model; no decision |
| drop | drop (keep band) | the candidates matter; split into one arm per span group |
| drop | equivalent | the candidates add nothing beyond the rest of the skill; deletion candidate |
| drop | inconclusive | more sessions up to the cap, or inconclusive |

Nothing is deleted on this file alone.
