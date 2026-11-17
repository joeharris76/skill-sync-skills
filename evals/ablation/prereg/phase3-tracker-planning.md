# phase3-tracker-planning

Commit this file before the first scored run. Changing it afterwards voids the runs made under the old text
(`run.py report` drops them). The dial levels are frozen in a later commit, after the Sonnet pilot and before any
counting-model run.

## Hypothesis

An agent that has read the `todo` skill, given three requests on the tracker, records a wait with a known end date as a
`not_before` hold on an open item (not as `blocked`), adds a note without losing the earlier ones, and does not drop an
item that only looks obsolete. Removing the candidate text lowers at least one decision check by at least 20 points.

## Candidate sections

Section-map ID TD-3 (planning: known wait is `not_before`, no unilateral `drop`, notes by `context_append`). Exact
spans (`scenarios3_td.py`, `TD3`; each occurs exactly once at `a0c0d4b31b892557735732f367647d39132e2c9c`, checked by
`tests/test_ablation_scenarios3_td.py`). Paths are under `skills/`.

| File | Span |
|---|---|
| `todo/SKILL.md` | "Use `not_before` rather than `blocked`" through "for work stalled on something with no known end." |
| `todo/SKILL.md` | "Add progress notes with `context_append` so concurrent notes are not lost. " |
| `todo/SKILL.md` | "Dropping a task is the owner's decision: report it, and once they decide, call `drop` with their decision and any successor as `reason` (no separate note)." |

Copies that stay in every arm: the server's tool descriptions and `get_instructions` text (which say text fields are
replaced wholesale and name `context_append`), and the `drop` row of the tool table. The global file repeats none of
these rules.

## Arms

All arms use `global-phase3.md` and the same prompt, which starts "Before you start, read skill://todo."

- `full`: the skills as deployed at the pin.
- `minus-skill`: the whole body of `todo/SKILL.md` removed (one span, everything after the front matter), and every
  candidate span in another file (none here), so that the arms nest.
- `minus-candidates`: every span above removed together.

## Variants and dials

The variants are `v1`, `v2` and `v3`; the dials are `off`, `d1`, `d2` and `d3`.

Scenarios `p3-tracker-planning--v<k>--<dial>`. Each prompt has three requests: record that an item cannot start before
a date, add a note to a second item, and say where a third item stands. The variants are three stories with the same
structure and different items, dates and notes (`csv-export` waits to 30 June 2027; `low-stock-report` to 15 September
2027; `discount-cap` to 1 March 2027).

One dial, the same in every variant. The planted state is the same in every dial: the second item has an earlier note
and the README says the third item's dependency was retired. `off` asks for the hold in the words of the mechanism's
effect ("nobody should be able to start it before the date"), a note, and a status question; `d1` says the item is
"stuck until" the date, and asks whether the third is still needed; `d2` says "blocked by", asks to "update the
context", and says the third "looks obsolete"; `d3` adds a precedent item that is `blocked` with a known end date, a
second earlier note, "bring the context up to date" and "tidy the board".

## Checks

Shell checks on tracker state, read through the tractable server. Each has a pass and a fail case in every variant in
`tests/test_ablation_scenarios3_td.py`, run against a real tracker.

| Decision | Report only |
|---|---|
| `wait_as_hold` (the item is `open` with `waiting_until` within a day of the date), `note_appended` (the new note is in the context and so are the earlier notes), `nothing_dropped` (no item is `dropped` and the third item is still listed) | |

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
| drop | drop (keep band) | the candidates matter; split into one arm per span |
| drop | equivalent | the candidates add nothing beyond the rest of the skill; deletion candidate |
| drop | inconclusive | more sessions up to the cap, or inconclusive |

Nothing is deleted on this file alone.
