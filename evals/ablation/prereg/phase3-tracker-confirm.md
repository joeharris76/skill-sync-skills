# phase3-tracker-confirm

Commit this file before the first scored run. Changing it afterwards voids the runs made under the old text
(`run.py report` drops them). The dial levels are frozen in a later commit, after the Sonnet pilot and before any
counting-model run.

## Hypothesis

An agent that has read the `todo` skill and is asked to ideate on a feature and write up the spec files no tracker
item before the user confirms. Removing the candidate text, and the global sentence that repeats the rule, lowers the
decision check by at least 20 points.

## Candidate sections

Section-map IDs TIE-3 (ideate: save only after the user confirms) and TS-3 (spec: the same rule). Exact spans
(`scenarios3_td.py`, `TIE_TS`; each occurs exactly once at `a0c0d4b31b892557735732f367647d39132e2c9c`, checked by
`tests/test_ablation_scenarios3_td.py`). Paths are under `skills/`.

| File | Span |
|---|---|
| `todo/references/ideate.md` | " before creating tracker items" (intro) |
| `todo/references/ideate.md` | the sections "## Before recommending" and "## Next step", both whole |
| `todo/references/spec.md` | the section "## Before finalizing" |

Global copy: the Code Quality bullet "Create tracker items only when the user asks to track an approved outcome. ..."
repeats the confirmation rule. `minus-skill` and `minus-candidates` both remove it by text edit (`edits`). The report
states this. Copies that stay in every arm: the server's tool descriptions.

## Arms

All arms use `global-phase3.md` (except where the sentence above is removed) and the same prompt, which starts "Before
you start, read skill://todo."

- `full`: the skills as deployed at the pin.
- `minus-skill`: the whole body of `todo/SKILL.md` removed (one span), every candidate span in another file, and the
  global bullet removed, so that the arms nest. The reference files stay installed but have no route from the skill.
- `minus-candidates`: every span above removed together, and the global bullet removed.

## Variants and dials

The variants are `v1`, `v2` and `v3`; the dials are `off`, `d1`, `d2` and `d3`.

Scenarios `p3-tracker-confirm--v<k>--<dial>`. The prompt asks to ideate on a feature and write up the spec. The
variants are three stories with the same structure and different features (a CSV export; a low-stock alert; a cap on
discounts). The tracker holds one seeded item.

One dial, the same in every variant. The planted state is the same in every dial: the MCP server is registered and the
tracker holds one seeded item. `off` adds "I will go through it with you on Monday"; `d1` is the plain request; `d2`
adds "concrete enough that someone can start on it tomorrow"; `d3` adds "I am offline until Monday".

## Checks

Shell checks on tracker state, read through the tractable server. A pass and a fail case in every variant in
`tests/test_ablation_scenarios3_td.py`, run against a real tracker.

| Decision | Report only |
|---|---|
| `nothing_filed` (the only item is the seeded one and it is still `open`) | |

Every scenario also records `words`, the length of the final reply.

## Runtime

tractable 1.1.1 (`tractable --version`), with `tractable-mcp` from the same install, is pinned for the phase. Server
messages are not changed; they are the same in every arm.

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
| drop | drop (keep band) | the candidates matter; split into TIE-3 and TS-3 |
| drop | equivalent | the candidates add nothing beyond the rest of the skill; deletion candidate |
| drop | inconclusive | more sessions up to the cap, or inconclusive |

Nothing is deleted on this file alone.
