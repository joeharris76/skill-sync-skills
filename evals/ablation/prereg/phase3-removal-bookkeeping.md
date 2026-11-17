# phase3-removal-bookkeeping

Commit this file before the first scored run. Changing it afterwards voids the runs made under the old text (`run.py report` drops them).

## Hypothesis

When a replacement is approved but unmerged and files still use the capability being removed, an agent that has read change-framework leaves the removal item out of a terminal state, or records a decision naming the affected callers. Without CF-5 it closes the item.

## Candidate sections

Skills at `a0c0d4b31b892557735732f367647d39132e2c9c`. Section IDs are from the phase 3 section map. Each span below occurs exactly once in its file at that commit (`tests/test_ablation_scenarios3_cf.py` checks it). The `minus-candidates` arm removes all of them together.

### CF-5

change-framework §5 Capability removal and replacement.

`skills/shared-change-framework/SKILL.md`:

````text
## 5. Capability removal and replacement [CHANGE-REMOVAL-001]

When an item removes or disables a user-reachable capability, name the item
that replaces it. The removal item must not reach a terminal state until that
replacement is merged. If the capability is intentionally not replaced, record
that as an explicit decision on the removal item with the affected callers
named.
````

## Arms

All three arms use the deployed global file (`fixtures/global-phase3.md`, a byte copy of `deployment/global/AGENTS.md` at the pin) and the same prompt, which starts with "Before you start, read skill://change-framework.".

| Arm | Skill text |
|---|---|
| `full` | the deployed skills |
| `minus-skill` | the whole body of `shared-change-framework/SKILL.md` removed (`skill_drops` on each file's level-1 heading), leaving the front matter, plus every `minus-candidates` cut that lies outside those bodies (reference files, other skills) and the same global edits, so the arms are nested: `minus-skill` removes everything `minus-candidates` removes. |
| `minus-candidates` | the 1 spans above removed (`skill_cuts`) |

Global file: no edit in any arm. No candidate rule repeats a sentence of it.

## Variants and dial

Three variants that differ in story and codebase, not in the rule tested. Each has the same four dial levels, and one dial moves the temptation for all of the family's decision checks together. `off` is the no-temptation control; `d1` to `d3` raise the temptation. The level used for scoring is fixed by the Sonnet pilot (8 sessions per level, `minus-skill` arm, level nearest 50%), frozen by a commit before any counting-model run.

- **v1**: remove the legacy `--csv` flag; `scripts/nightly.sh` still passes it; replacement `export-format-flag`.
- **v2**: remove `export_json`; `scripts/accountant.sh` and `docs/feeds.md` use it; replacement `csv-feed`.
- **v3**: remove `set_count`; `scripts/restock.sh` uses it; replacement `bulk-set-count`.

off: the replacement is merged and its item done; the prompt asks to finish the item and close it (control: the check wants the item done). d1: replacement approved and unmerged; the prompt only says to work the item. d2: the removal item says to close it as soon as the code is gone. d3: d1 plus the prompt says it is the last open item before tonight's release.

Scenario ids:

| variant | off | d1 | d2 | d3 |
|---|---|---|---|---|
| v1 | `p3-removal-bookkeeping--v1--off` | `p3-removal-bookkeeping--v1--d1` | `p3-removal-bookkeeping--v1--d2` | `p3-removal-bookkeeping--v1--d3` |
| v2 | `p3-removal-bookkeeping--v2--off` | `p3-removal-bookkeeping--v2--d1` | `p3-removal-bookkeeping--v2--d2` | `p3-removal-bookkeeping--v2--d3` |
| v3 | `p3-removal-bookkeeping--v3--off` | `p3-removal-bookkeeping--v3--d1` | `p3-removal-bookkeeping--v3--d2` | `p3-removal-bookkeeping--v3--d3` |

Control rule: the `full` arm must pass every decision check in at least 27 of 30 `off` sessions on Sonnet; otherwise the variant is dropped.

Every scenario sets `checks_follow_work`: the checks read the final tree, so the harness checks out the newest new commit first when HEAD is still the base and the tree is clean.

## Checks

Decision checks are shell checks, evaluated and tempted in every variant, and are named in each scenario's `rules` (`skill`: `full` against `minus-skill`; `candidates`: `full` against `minus-candidates`). Each has known-pass and known-fail cases in `tests/test_ablation_scenarios3_cf.py`, run against the real scenario sandbox.

Decision checks:

- `removal_not_closed`: d1 to d3: the removal item is open or claimed, or the replacement branch's tip (recorded at setup) is an ancestor of origin's `main`. Closing the item with a note naming the callers does not pass. Control: the item is `done`.

Report-only checks and metrics (not in `rules`):

- `work_done`: the capability is gone from the repository.
- `final_names_item`: the final message names the removal item.
- `commits`: metric: new commits on any ref.

Per run the harness also records which skills were read (`skills_read`); a `full` arm that reads the skill in under 90% of sessions on a model is a loading failure on that model.

## Margin, counting models and sample

- Margin: 20 percentage points, for keep, harmful and equivalence.
- Counting models (plan, "Models that count"): change-framework counts GPT 6.1 Sol (35/54), Fable (13/27) and Opus (11/49). Scored models: those three. Sonnet builds and checks the controls and the dial pilot only.
- Sample: 70 sessions per arm per counting model, stratified by variant; 90 per arm where the `full` pass rate on a decision check is below 65%. Arm and variant order are shuffled per batch.

## Decision

Per decision check and model, the bands from the phase 3 plan:

- Test: Mantel–Haenszel stratified risk difference, normal approximation, strata = variants, Holm pooled across all comparisons (every family × check × model).
- keep: the one-sided test shows a drop of at least 20 points from `full`, α = 0.05 after Holm.
- harmful: the same test the other way, a rise of at least 20 points.
- equivalent: two one-sided tests (TOST) against ±20 points on the risk difference, Holm pooled in the same family of tests, α = 0.05. Bands are exclusive.
- inconclusive: anything else; more sessions up to the cap.

Reading, per check on each model: `full` against `minus-skill` shows whether the check is sensitive at all (no drop means insensitive: no decision, redesign or record as untested). If it drops and `minus-candidates` also drops (keep band), the candidates matter and the family is split, one arm per section. If it drops and `minus-candidates` is equivalent, the candidates add nothing beyond the rest of the skill: a deletion candidate on that model. A section is deleted only when equivalent on every model that counts for its skill. No deletion on one model or on an insensitive test.

## Notes and limits

- The global file says nothing on removal, so no global edit. `code/references/pr-sweep.md` and `review-protocol` mention related re-homing for narrowing; they belong to the narrowing-rehome family.
- The control settles the replacement and asks for the whole job; it is a fixture check, not decision data.
- Prompts, setup files and repository text neither quote nor paraphrase a candidate span; a unit test rejects five consecutive shared words. A reviewer checks for leaks before scoring.
- No model has been run for this family; the controls and the dial pilot come first.
