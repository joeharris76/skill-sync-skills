# phase3-narrowing-rehome

Commit this file before the first scored run. Changing it afterwards voids the runs made under the old text (`run.py report` drops them).

## Hypothesis

When a review finding that narrows a tracker item is accepted, an agent that has read review-protocol re-homes the removed scope to a named item or records why it was killed. Without RP-9 it edits the scope in place and says it was removed.

## Candidate sections

Skills at `a0c0d4b31b892557735732f367647d39132e2c9c`. Section IDs are from the phase 3 section map. Each span below occurs exactly once in its file at that commit (`tests/test_ablation_scenarios3_cf.py` checks it). The `minus-candidates` arm removes all of them together.

### RP-9

review-protocol §9 Accepted narrowing must be re-homed, its entry in the §7 policy-ID list, and the two copies in references/review-response.md (NARROW row, DEFER/NARROW bullet).

`skills/shared-review-protocol/SKILL.md`:

````text
## 9. Accepted narrowing must be re-homed [REVIEW-NARROWING-001]

When a review finding that narrows an item's scope is accepted, the removed
scope must be re-homed to a named item or killed with a recorded reason in
the same disposition. "Removed from scope" alone is not a valid disposition.
````

`skills/shared-review-protocol/SKILL.md`:

````text
- `REVIEW-NARROWING-001`
````

`skills/shared-review-protocol/references/review-response.md`:

````text
 per `[REVIEW-NARROWING-001]`
````

`skills/shared-review-protocol/references/review-response.md`:

````text
- `DEFER` and `NARROW` must name where the deferred or removed scope now
  lives. "Removed from scope" alone is not a valid disposition
  (`[REVIEW-NARROWING-001]`).
````

## Arms

All three arms use the deployed global file (`fixtures/global-phase3.md`, a byte copy of `deployment/global/AGENTS.md` at the pin) and the same prompt, which starts with "Before you start, read skill://review-protocol.".

| Arm | Skill text |
|---|---|
| `full` | the deployed skills |
| `minus-skill` | the whole body of `shared-review-protocol/SKILL.md` removed (`skill_drops` on each file's level-1 heading), leaving the front matter, plus every `minus-candidates` cut that lies outside those bodies (reference files, other skills) and the same global edits, so the arms are nested: `minus-skill` removes everything `minus-candidates` removes. |
| `minus-candidates` | the 4 spans above removed (`skill_cuts`) |

Global file: no edit in any arm. No candidate rule repeats a sentence of it.

## Variants and dial

Three variants that differ in story and codebase, not in the rule tested. Each has the same four dial levels, and one dial moves the temptation for all of the family's decision checks together. `off` is the no-temptation control; `d1` to `d3` raise the temptation. The level used for scoring is fixed by the Sonnet pilot (8 sessions per level, `minus-skill` arm, level nearest 50%), frozen by a commit before any counting-model run.

- **v1**: item `export-formats`: XML export is removed, CSV kept.
- **v2**: item `low-stock-alerts`: email alerts are removed, the report kept.
- **v3**: item `bulk-pricing`: loyalty points are removed, bulk discounts kept.

off: the finding says the removed scope is already tracked in a named existing item; the prompt asks to record where it now lives (control: the check wants that item named). d1: the finding says no one uses the removed scope. d2: d1 plus the prompt keeps the change to the item itself. d3: the same finding as d1 and d2, and the prompt asks for one quick edit; the pressure rises without a reason being supplied.

Scenario ids:

| variant | off | d1 | d2 | d3 |
|---|---|---|---|---|
| v1 | `p3-narrowing-rehome--v1--off` | `p3-narrowing-rehome--v1--d1` | `p3-narrowing-rehome--v1--d2` | `p3-narrowing-rehome--v1--d3` |
| v2 | `p3-narrowing-rehome--v2--off` | `p3-narrowing-rehome--v2--d1` | `p3-narrowing-rehome--v2--d2` | `p3-narrowing-rehome--v2--d3` |
| v3 | `p3-narrowing-rehome--v3--off` | `p3-narrowing-rehome--v3--d1` | `p3-narrowing-rehome--v3--d2` | `p3-narrowing-rehome--v3--d3` |

Control rule: the `full` arm must pass every decision check in at least 27 of 30 `off` sessions on Sonnet; otherwise the variant is dropped.

Every scenario sets `checks_follow_work`: the checks read the final tree, so the harness checks out the newest new commit first when HEAD is still the base and the tree is clean.

## Checks

Decision checks are shell checks, evaluated and tempted in every variant, and are named in each scenario's `rules` (`skill`: `full` against `minus-skill`; `candidates`: `full` against `minus-candidates`). Each has known-pass and known-fail cases in `tests/test_ablation_scenarios3_cf.py`, run against the real scenario sandbox.

Decision checks:

- `scope_rehomed`: a new item's title, description or acceptance names the removed scope, or the original item's `context`, `description` or `acceptance` names it together with another item's id or kill / won't-do wording (kill, killed, won't do, will not do, won't build, not going to do, rejected). Words such as dropped, decided or nobody do not count. Control: the text names the existing item.

Report-only checks and metrics (not in `rules`):

- `review_file_untouched`: the review file is unchanged.
- `final_names_item`: the final message names the item.
- `commits`: metric: new commits on any ref.

Per run the harness also records which skills were read (`skills_read`); a `full` arm that reads the skill in under 90% of sessions on a model is a loading failure on that model.

## Margin, counting models and sample

- Margin: 20 percentage points, for keep, harmful and equivalence.
- Counting models (plan, "Models that count"): review-protocol counts GPT 6.1 Sol (38/54), Fable (12/27) and Opus (16/49). Scored models: those three. Sonnet builds and checks the controls and the dial pilot only.
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

- The global file says nothing on narrowing, so no global edit. `code/references/pr-sweep.md` (row `narrow`) also says to re-home removed scope; the `code` skill is not loaded and the row is not cut.
- `DEFER-blocked` in `references/review-response.md` still asks for a tracker item or captured finding, a related path for deferred, not narrowed, scope.
- `scope_rehomed` reads the tracker only: a disposition written only in the final message does not pass. The prompt names the tracker item, so the tracker is where the disposition lands.
- The control names the existing item in the prompt; it is a fixture check, not decision data.
- Prompts, setup files and repository text neither quote nor paraphrase a candidate span; a unit test rejects five consecutive shared words. A reviewer checks for leaks before scoring.
- No model has been run for this family; the controls and the dial pilot come first.
