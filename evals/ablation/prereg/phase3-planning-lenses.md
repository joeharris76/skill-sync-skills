# phase3-planning-lenses

Commit this file before the first scored run. Changing it afterwards voids the runs made under the old text
(`run.py report` drops them). Dial levels are frozen in it by commit after the Sonnet pilot.

## Hypothesis

Asked for a plan, an agent that has read `review-protocol` checks the plan against the recorded decisions in the repository and cites the one the obvious plan contradicts, and flags the manual step that follows the change but has no owner. Without sections 8 and 10 (and their references), at least 20 points fewer plans do each.

## Candidate sections

Skills are pinned at `a0c0d4b31b892557735732f367647d39132e2c9c` and the global file is `global-phase3.md` (a byte copy of
`deployment/global/AGENTS.md` at that commit). Each span below occurs exactly once in its file at the pin; the
unit tests check it.

- **RP-8** (section map): `review-protocol` §8 "Plan prior-decision reconciliation" [REVIEW-PLAN-RECON-001] in full.
- **RP-10**: §10 "User-experience lens" [REVIEW-UX-001] in full.
- Cross-references removed with them: the phrase in the front-matter description that names plan prior-decision reconciliation, and the two policy-ID entries for these sections in §7's list of IDs to preserve.
- No global sentence repeats them (the global file points at §3, which stays).

`minus-candidates` cut 1, file `skills/shared-review-protocol/SKILL.md`:

```
## 8. Plan prior-decision reconciliation [REVIEW-PLAN-RECON-001]

Claim-against-code checking is necessary and not sufficient for plan reviews.
Before judging a plan's steps, enumerate the recorded decision surfaces the
plan's scope touches:

- future-state index and its priority tiers
- migration gates in design docs
- readiness and evidence documents
- open tracker items at the relevant priority

The plan must cite each one or explicitly supersede it. An unexplained
demotion of recorded priority, or a dropped open gate, is a plan defect.

```

`minus-candidates` cut 2, file `skills/shared-review-protocol/SKILL.md`:

```

## 10. User-experience lens [REVIEW-UX-001]

Apply a user-experience lens distinct from security and correctness: ask who
performs each remaining manual step after the change lands and flag steps
with no owner.
```

`minus-candidates` cut 3, file `skills/shared-review-protocol/SKILL.md`:

```
, and plan prior-decision reconciliation```

`minus-candidates` cut 4, file `skills/shared-review-protocol/SKILL.md`:

```
- `REVIEW-PLAN-RECON-001`
```

`minus-candidates` cut 5, file `skills/shared-review-protocol/SKILL.md`:

```
- `REVIEW-UX-001`
```

## Arms

Every scenario has the same three arms, all with `global-phase3.md`, the pinned skills and the same prompt
(which starts with the line asking the agent to read the family's skill):

- `full`: the deployed skill(s).
- `minus-skill`: the whole body of the family's skill file(s) removed, everything after the front matter, as one
  `skill_cuts` span per file.
- `minus-candidates`: only the spans listed above removed, with the cross-references that point at them.
- The global file is the same in all three arms.

Rules (the `rules` field of every scenario): `planning-lenses-skill`, `planning-lenses-candidates`. Each compares `full` with the named removal arm on the
decision checks below.

## Variants and dials

Each variant asks for a plan (reply only, no file changes) in a repository with a future-state index (`docs/future-state.md`, a P0 item), a decision record (`docs/decisions/DEC-xxxx-*.md`) that the obvious plan contradicts, and a runbook (`docs/runbook.md`) whose last row is a manual step with no owner:

- v1: an in-memory cache of counts; `DEC-0412` (counts have one store); manual step `RB-9` (restart the shop-tablet app by hand).
- v2: moving the stock file to SQLite; `DEC-0518` (JSON stays the system of record until the accountant export is retired); `RB-4` (re-point the accountant's macro by hand).
- v3: replacing `export_json` with CSV; `DEC-0233` (the export is a contract with the accountant); `RB-12` (phone the accountant).

The dial moves how directly the user's request points at that evidence: `off` names the decision and the runbook step by id and asks for a rollout section (the control; it checks the fixture and the checks, not the rule); `d1` says "the background is in docs/"; `d2` says nothing, and the README lists the documents; `d3` says nothing, the README does not mention `docs/`, and eight unrelated notes sit beside the records.

| Variant | `off` | `d1` | `d2` | `d3` |
|---|---|---|---|---|
| v1 | `p3-planning-lenses--v1--off` | `p3-planning-lenses--v1--d1` | `p3-planning-lenses--v1--d2` | `p3-planning-lenses--v1--d3` |
| v2 | `p3-planning-lenses--v2--off` | `p3-planning-lenses--v2--d1` | `p3-planning-lenses--v2--d2` | `p3-planning-lenses--v2--d3` |
| v3 | `p3-planning-lenses--v3--off` | `p3-planning-lenses--v3--d1` | `p3-planning-lenses--v3--d2` | `p3-planning-lenses--v3--d3` |

Scenario ids are `p3-planning-lenses--v<k>--<dial>`.

## Decision checks

Shell checks only, scored in every arm. Passing is the wanted behaviour.

- `cites_decision` (all variants): the reply contains the planted decision id.
- `flags_unowned_step` (all variants): a reply line naming the planted runbook step (its id or its distinctive words) has "no owner", "unowned", "nobody" or "who owns/will/is" on the same or an adjacent line.

## Report-only checks

Recorded, never used for a decision.

- `mentions_step` (all variants): the reply names the planted step.
- `cites_future_state` (all variants): the reply mentions `future-state` or `P0`.
- `changed_nothing` (all variants): no uncommitted change and no commit beyond the base.
- `reply_is_a_plan` (all variants): the reply has at least 120 words.



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
