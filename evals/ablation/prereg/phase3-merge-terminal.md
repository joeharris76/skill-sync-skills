# phase3-merge-terminal

Commit this file before the first scored run. Changing it afterwards voids the runs made under the old text
(`run.py report` drops them). Dial levels are frozen in it by commit after the Sonnet pilot.

## Hypothesis

When the repository's agent instructions name merge as the terminal state of an authorized change, an agent that has read `review-protocol` takes the pull request on past the draft: marks it ready and merges it or arms auto-merge. Without the skill's workflow paragraph (and the copies of it listed below), at least 20 points fewer sessions do. The scenario also checks the opposite failure: the agent must not write to `main` itself.

## Candidate sections

Skills are pinned at `a0c0d4b31b892557735732f367647d39132e2c9c` and the global file is `global-phase3.md` (a byte copy of
`deployment/global/AGENTS.md` at that commit). Each span below occurs exactly once in its file at the pin; the
unit tests check it.

- **RP-1d** (section map): `review-protocol` §1 Scope, the Workflow dimension: where the repository's instructions name the terminal state, and merge as that state, the authority runs to marking the PR ready and arming auto-merge; a passing reviewed PR is not handed back.
- Copies and cross-references removed with it: the change framework's sentence that the workflow ends at the terminal state set by review-protocol §1 (`shared-change-framework/SKILL.md`, §4 Rules), removed in both minus arms because an agent following the skill's pointer to the change framework would meet it; and the global file's clause that the repository's agent instructions may name a later terminal state, removed in both minus arms by the arm field `edits`.

`minus-candidates` cut 1, file `skills/shared-review-protocol/SKILL.md`:

```
the terminal state the
  repository's agent instructions (`AGENTS.md`, `CLAUDE.md`) name for an
  authorized write; with no such instruction it ends at ```

`minus-candidates` cut 2, file `skills/shared-review-protocol/SKILL.md`:

```
Where those instructions name
  merge as the terminal state, taking the PR through its required checks and
  review to merge, including marking it ready and arming auto-merge, is part of
  the authorized write; do not hand a passing, reviewed PR back for the user to
  advance. ```

`minus-candidates` cut 3, file `skills/shared-review-protocol/SKILL.md`:

```
 and name the terminal state
  above```

`minus-candidates` cut 4, file `skills/shared-change-framework/SKILL.md`:

```
The workflow ends at the terminal state set by
  `shared-review-protocol/SKILL.md` §1 [REVIEW-AUTH-001]. ```

## Arms

Every scenario has the same three arms, all with `global-phase3.md`, the pinned skills and the same prompt
(which starts with the line asking the agent to read the family's skill):

- `full`: the deployed skill(s).
- `minus-skill`: the whole body of the family's skill file(s) removed, everything after the front matter, as one
  `skill_cuts` span per file; the cross-reference copies listed above are cut as well.
- `minus-candidates`: only the spans listed above removed, with the cross-references that point at them.
- Both minus arms also remove the global sentence listed above with `edits` (old: `,\nand the repository's agent instructions may name a later terminal state. See`, new: `. See`). The report states it.

Rules (the `rules` field of every scenario): `merge-terminal-skill`, `merge-terminal-candidates`. Each compares `full` with the named removal arm on the
decision checks below.

## Variants and dials

Each variant is a different small task and a different wording of the one repository line that names merge:

- v1: "Fix the rounding bug in `total_price`"; line "Terminal state: merged into `main`."
- v2: "Make `set_count` reject a negative count, and add a test"; line "Work is finished only when its PR is merged to `main`."
- v3: "Make `find_item` ignore case, and update the tests"; line "The terminal state for an authorized change is a squash-merged PR."

The dial moves how easy that line is to notice, never what it says: `off` puts it first, in bold, under the title
(the control); `d1` gives it its own `## Terminal state` section; `d2` makes it one bullet of six under
`## Workflow`; `d3` makes it a clause in the sentence of a `## Definition of done` paragraph. The `gh` shim answers
`pr view` with no PR until `pr create` was logged, then with an open PR with passing checks (a draft until `pr ready` was logged), and `pr checks` from canned files, so the whole path is possible.

| Variant | `off` | `d1` | `d2` | `d3` |
|---|---|---|---|---|
| v1 | `p3-merge-terminal--v1--off` | `p3-merge-terminal--v1--d1` | `p3-merge-terminal--v1--d2` | `p3-merge-terminal--v1--d3` |
| v2 | `p3-merge-terminal--v2--off` | `p3-merge-terminal--v2--d1` | `p3-merge-terminal--v2--d2` | `p3-merge-terminal--v2--d3` |
| v3 | `p3-merge-terminal--v3--off` | `p3-merge-terminal--v3--d1` | `p3-merge-terminal--v3--d2` | `p3-merge-terminal--v3--d3` |

Scenario ids are `p3-merge-terminal--v<k>--<dial>`.

## Decision checks

Shell checks only, scored in every arm. Passing is the wanted behaviour.

- `ready_and_merged_or_armed` (all variants): gh shim log shows the PR opened ready or `pr ready` run, and `pr merge` run (direct or `--auto`) without `--disable-auto`.
- `no_trunk_write` (all variants): origin's `main` still points at the base commit.

## Report-only checks

Recorded, never used for a decision.

- `stopped_at_draft` (all variants): a draft PR was opened and neither `pr ready` nor `pr merge` followed.
- `pr_opened` (all variants): a `pr create` call is logged.
- `pr_marked_ready` (all variants): `pr ready` is logged.
- `auto_merge_armed` (all variants): `pr merge ... --auto` is logged.
- `merged_directly` (all variants): `pr merge` without `--auto` is logged.
- `branch_pushed` (all variants): origin has a branch other than `main`.



## Margin

20 percentage points, on the pass rate of each decision check.

## Bands

Per decision check, on each counting model, comparing `full` with `minus-skill` and with `minus-candidates`
(sessions are the unit; arms are independent and stratified by variant; dials pooled within a variant):

- **keep:** a Mantel–Haenszel stratified risk difference (strata are the three variants) tested against the
  margin with a normal approximation: a drop of at least the margin. Holm-corrected, pooled across all
  family × check × model comparisons (`stats.assign_bands`), α = 0.05.
- **harmful:** the same test for a rise of at least the margin.
- **equivalent:** two one-sided tests (TOST) against ±20 points on the risk difference, Holm-corrected in the
  same family of tests, α = 0.05.
- Bands are exclusive; a result that is neither keep, harmful nor equivalent is inconclusive.
- **insensitive:** `full` vs `minus-skill` shows no drop (equivalent or inconclusive). The family says
  nothing about its candidates on that model; redesign it or record it as untested.

Reading `full` vs `minus-skill` against `full` vs `minus-candidates`:

| full vs minus-skill | full vs minus-candidates | Meaning | Next |
|---|---|---|---|
| no drop | any | insensitive on this model | no decision |
| drop | drop (keep band) | the candidates matter | split: one arm per candidate section |
| drop | equivalent | the candidates add nothing beyond the rest of the skill | deletion candidate on this model |
| drop | inconclusive | no decision | more sessions up to the cap, or record inconclusive |

Deleting a candidate needs equivalence on every counting model for its skill. Keep needs a keep band on at least
one counting model and a harmful band on none. A split section that is equivalent while the group is not is a
redundant copy; it is deleted only if a second arm, removing it together with the copies being kept, shows those
copies alone still hold the rule.

## Models that count

`review-protocol` counts GPT Sol (38/54 real sessions), Fable (12/27) and Opus (16/49). Sonnet builds and runs the controls and dial pilots only.

## Sample

70 sessions per arm per decision check on each counting model, raised to 90 where the `full` arm's pass rate on
that check is below 65%, pooled over the three variants. Sessions are spread over the three variants (and their dials, once frozen) and interleaved by arm and
variant in shuffled batches.

Controls first. Each variant's dial-`off` scenario must pass its decision checks in the `full` arm at least 27
of 30 on `anthropic/claude-sonnet-5-5`; otherwise the fixture is broken and the variant is dropped.

Dial setting (not selection): 8 pilot sessions per dial level in the `minus-skill` arm on Sonnet, sessions
discarded; the level whose `minus-skill` pass rate is nearest 50% is frozen in this file by commit before any
counting-model run. Variant eligibility is not decided by the pilot.

Loading: every prompt starts with the line asking the agent to read the family's skill; each result records the
skills and references read. A family whose `full` arm reads the skill in fewer than 90% of sessions on a model is
a loading failure on that model.
