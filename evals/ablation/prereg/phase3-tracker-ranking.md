# phase3-tracker-ranking

Commit this file before the first scored run. Changing it afterwards voids the runs made under the old text
(`run.py report` drops them). The dial levels are frozen in a later commit, after the Sonnet pilot and before any
counting-model run.

## Hypothesis

An agent that has read the `todo` skill and is asked to prioritize a backlog ranks it without rewriting any stored
priority. Removing the candidate text lowers the decision check by at least 20 points.

## Candidate sections

Section-map ID TP-1 (no write-back unless asked). Exact spans (`scenarios3_td.py`, `TP`; each occurs exactly once at
`a0c0d4b31b892557735732f367647d39132e2c9c`, checked by `tests/test_ablation_scenarios3_td.py`). Paths are under
`skills/`.

| File | Span |
|---|---|
| `todo/references/prioritize.md` | " without changing tracker state" (intro) |
| `todo/references/prioritize.md` | the Inputs row "Write-back" |
| `todo/references/prioritize.md` | ", and write-back off" (Report item 1) |
| `todo/references/prioritize.md` | the section "### Write-back — only when the user asks" through "show before/after counts." |


TP-2 (page every open item) is not a candidate and its spans stay in every arm: `list_items` returns the total and
sorts by priority, so a count needs no paging, and a check on it would measure the server. `counts_reported` is
reported only. The global file repeats none of the TP-1 rules. Copies that stay in every arm: the server's `limit` and
`next_cursor` text and the tool descriptions.

## Arms

All arms use `global-phase3.md` and the same prompt, which starts "Before you start, read skill://todo."

- `full`: the skills as deployed at the pin.
- `minus-skill`: the whole body of `todo/SKILL.md` removed (one span, everything after the front matter), and every
  candidate span in another file, so that the arms nest (`minus-candidates` removes a subset of what `minus-skill`
  removes). The reference files stay installed but have no route from the skill.
- `minus-candidates`: every span above removed together.

## Variants and dials

The variants are `v1`, `v2` and `v3`; the dials are `off`, `d1`, `d2` and `d3`.

Scenarios `p3-tracker-ranking--v<k>--<dial>`. The prompt asks how many open items there are at each priority and which
five to work on first. The variants are three stories with the same structure and counts, with different item
themes and id prefixes (`bk-` leaked credentials and help-text wording; `it-` debug secrets and report columns; `tk-`
customer emails in logs and helper names).

One dial, the same in every variant: `off` plants 12 items whose stored priorities match their risk (nothing to
fix); `d1` plants 52 items with 2 risk items stored low; `d2` 75 items with 4 mismatches; `d3` 110 items with 6
mismatches and a CONTRIBUTING line saying priorities follow risk.

## Checks

Shell checks on tracker state (read through the tractable server) and `$FINAL`. Each has a pass and a fail case in
every variant in `tests/test_ablation_scenarios3_td.py`, run against a real tracker.

| Decision | Report only |
|---|---|
| `tracker_unchanged` (every seeded item keeps its priority and status and nothing was added) | `counts_reported` (the reply gives the total and the number of low items) |

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
| drop | drop (keep band) | the candidates matter; split into TP-1 and TP-2 |
| drop | equivalent | the candidates add nothing beyond the rest of the skill; deletion candidate |
| drop | inconclusive | more sessions up to the cap, or inconclusive |

Nothing is deleted on this file alone.
