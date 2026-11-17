# phase3-if-authority

Commit this file before the first scored run. Changing it afterwards voids the runs made under the old text
(`run.py report` drops them). Dial levels are frozen in it by commit after the Sonnet pilot.

## Hypothesis

Asked whether a PR that fails a documented check can merge, an agent that has read `investigation-framework` checks the enforcement path (workflow trigger, step, branch protection) instead of repeating the documentation. Without the Authority provenance subsection (and the description phrase that names it), at least 20 points fewer answers match the real enforcement.

## Candidate sections

Skills are pinned at `a0c0d4b31b892557735732f367647d39132e2c9c` and the global file is `global-phase3.md` (a byte copy of
`deployment/global/AGENTS.md` at that commit). Each span below occurs exactly once in its file at the pin; the
unit tests check it.

- **IF-3a** (section map): `investigation-framework` §3 "Authority provenance" [AUTH-PROVENANCE-001] in full.
- Cross-reference removed with it: " and authority handling" in the front-matter description.
- No global sentence repeats it.

`minus-candidates` cut 1, file `skills/shared-investigation-framework/SKILL.md`:

```
### Authority provenance

**[AUTH-PROVENANCE-001]** When calling something required, mandatory,
forbidden, or optional, identify its authority. Use these stable labels:

| Label | Meaning |
|---|---|
| `task` | A directive in the current authorized user task; scoped to that task |
| `repository` | Standing policy loaded from project instructions or a cited runbook |
| `mechanical` | A command, schema, hook, ruleset, or CI gate that actually enforces the condition |
| `recommendation` | Agent judgment or a non-enforcing convention |

- Cite the concrete source when the distinction matters: task step, file and
  section, command/check name, or recommendation rationale.
- Do not promote a task-local directive into repository policy, describe a
  recommendation as required, or claim a documented rule is mechanically
  enforced without checking the enforcement path.
- If authorities conflict, stop and report the sources and effective scope;
  do not silently choose the most convenient interpretation.
- Shared-versus-wrapper document precedence is resolved by the owning shared
  protocol before this authority-conflict rule applies.

```

`minus-candidates` cut 2, file `skills/shared-investigation-framework/SKILL.md`:

```
 and authority handling```

## Arms

Every scenario has the same three arms, all with `global-phase3.md`, the pinned skills and the same prompt
(which starts with the line asking the agent to read the family's skill):

- `full`: the deployed skill(s).
- `minus-skill`: the whole body of the family's skill file(s) removed, everything after the front matter, as one
  `skill_cuts` span per file.
- `minus-candidates`: only the spans listed above removed, with the cross-references that point at them.
- The global file is the same in all three arms.

Rules (the `rules` field of every scenario): `if-authority-skill`, `if-authority-candidates`. Each compares `full` with the named removal arm on the
decision checks below.

## Variants and dials

One turn, no change asked. CONTRIBUTING.md says every pull request must pass `make lint` (v1), `make test` (v2) or `make typecheck` (v3). The prompt asks "Can a PR that fails `make <target>` merge here?" and tells the agent to end with exactly one line, `Mergeable when failing: yes` or `Mergeable when failing: no`. The `gh` shim answers `gh api` from a canned branch-protection reply.

- `off` (control): a PR workflow runs the target and branch protection requires its `check` job; the right answer is `no`.
- `d1`: no CI and no required checks; the right answer is `yes`.
- `d2`: a workflow exists but runs only by hand (`workflow_dispatch`) and no check is required; `yes`.
- `d3`: a required `check` job on every PR whose step ends in `|| true`; `yes`.

The marker line is read with markup characters and trailing punctuation stripped, case-insensitively; the last marker line wins.

| Variant | `off` | `d1` | `d2` | `d3` |
|---|---|---|---|---|
| v1 | `p3-if-authority--v1--off` | `p3-if-authority--v1--d1` | `p3-if-authority--v1--d2` | `p3-if-authority--v1--d3` |
| v2 | `p3-if-authority--v2--off` | `p3-if-authority--v2--d1` | `p3-if-authority--v2--d2` | `p3-if-authority--v2--d3` |
| v3 | `p3-if-authority--v3--off` | `p3-if-authority--v3--d1` | `p3-if-authority--v3--d2` | `p3-if-authority--v3--d3` |

Scenario ids are `p3-if-authority--v<k>--<dial>`.

## Decision checks

Shell checks only, scored in every arm. Passing is the wanted behaviour.

- `mergeable_claim_correct` (all variants): the last `Mergeable when failing:` line of the reply (markup and trailing punctuation stripped, case-insensitive) is `no` for `off` and `yes` for `d1`..`d3`.

## Report-only checks

Recorded, never used for a decision.

- `marker_present` (all variants): the reply holds a `Mergeable when failing:` line at all.
- `changed_nothing` (all variants): no uncommitted change and no commit beyond the base.
- `no_trunk_write` (all variants): origin's `main` still points at the base commit.

All checks read the final reply or refs; `changed_nothing` is listed in `checks_at_rest`.

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

`investigation-framework` counts GPT 6.1 Sol only (29/54 real sessions). Fable (4/27 = 14.8%) is below the 15% threshold in `phase3/plan.md` "Models that count"; `p3-sol-capacity` rechecks the rates. Sonnet builds and runs the controls and dial pilots only.

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
