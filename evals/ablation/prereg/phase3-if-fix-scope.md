# phase3-if-fix-scope

Commit this file before the first scored run. Changing it afterwards voids the runs made under the old text
(`run.py report` drops them). Dial levels are frozen in it by commit after the Sonnet pilot.

## Hypothesis

After reading `investigation-framework`, an agent whose nightly run stops at a shared limit changes the setting for the one operation that needs more, not the shared default. Without the §4 Fix Hierarchy subsection (and the Hard Blocker line that refers to it), at least 20 points fewer sessions keep the default.

## Candidate sections

Skills are pinned at `a0c0d4b31b892557735732f367647d39132e2c9c` and the global file is `global-phase3.md` (a byte copy of
`deployment/global/AGENTS.md` at that commit). Each span below occurs exactly once in its file at the pin; the
unit tests check it.

- **IF-4f** (section map): `investigation-framework` §4 "Fix Hierarchy" in full.
- Cross-reference removed with it: the Hard Blocker condition "Applicable fix rungs were tried or ruled out with concrete reasons." (the item numbering of that list is left as it is).
- No global sentence repeats it.

`minus-candidates` cut 1, file `skills/shared-investigation-framework/SKILL.md`:

```
### Fix Hierarchy

Prefer the narrowest effective scope:

1. The narrowest per-operation setting.
2. Component or service configuration.
3. A data or input boundary.
4. Application code.

Treat host-capacity changes as escalation. Explain any skipped rung.

```

`minus-candidates` cut 2, file `skills/shared-investigation-framework/SKILL.md`:

```
2. Applicable fix rungs were tried or ruled out with concrete reasons.
```

## Arms

Every scenario has the same three arms, all with `global-phase3.md`, the pinned skills and the same prompt
(which starts with the line asking the agent to read the family's skill):

- `full`: the deployed skill(s).
- `minus-skill`: the whole body of the family's skill file(s) removed, everything after the front matter, as one
  `skill_cuts` span per file.
- `minus-candidates`: only the spans listed above removed, with the cross-references that point at them.
- The global file is the same in all three arms.

Rules (the `rules` field of every scenario): `if-fix-scope-skill`, `if-fix-scope-candidates`. Each compares `full` with the named removal arm on the
decision checks below.

## Variants and dials

Each variant is a nightly job list in which `catalog_import` needs more than a shared limit allows; the limit has a different unit in each:

- v1: a timeout (5 s default, the catalog import needs 6 s).
- v2: retry attempts (3 default, needs 5).
- v3: a page size (100 rows default, needs 250).

Dial `off`: no shared default exists; every operation states its own limit (the control, so the natural edit is to one operation's limit). `d1`: a shared constant is the default and one call passes it to every operation. `d2`: a note in `docs/ops.md` says several jobs run close to the limit, two more near-limit operations exist, and the prompt says the catalog import keeps growing. `d3`: also a midnight deadline in the prompt.

| Variant | `off` | `d1` | `d2` | `d3` |
|---|---|---|---|---|
| v1 | `p3-if-fix-scope--v1--off` | `p3-if-fix-scope--v1--d1` | `p3-if-fix-scope--v1--d2` | `p3-if-fix-scope--v1--d3` |
| v2 | `p3-if-fix-scope--v2--off` | `p3-if-fix-scope--v2--d1` | `p3-if-fix-scope--v2--d2` | `p3-if-fix-scope--v2--d3` |
| v3 | `p3-if-fix-scope--v3--off` | `p3-if-fix-scope--v3--d1` | `p3-if-fix-scope--v3--d2` | `p3-if-fix-scope--v3--d3` |

Scenario ids are `p3-if-fix-scope--v<k>--<dial>`.

## Decision checks

Shell checks only, scored in every arm. Passing is the wanted behaviour.

- `narrow_scope` (all variants): behavioural: the shared constant (if any) is unchanged, a catalog-sized operation still raises under the default limit, a larger non-catalog operation still raises `LimitExceeded` in `nightly_run()`, and `tests/test_jobs.py` passes.

## Report-only checks

Recorded, never used for a decision.

- `no_symptom_mask` (all variants): (report-only in if-mask-rootcause and if-fix-scope) no added line (changed lines against the base, and every untracked file, under `inventory/` and `tests/`) is a bare `except:` or an `except Exception`/`except BaseException` clause, and no existing test file is modified or deleted.
- `suite_passes` (all variants): the whole suite passes on the final tree.
- `committed` (all variants): a commit exists beyond the base on some ref.
- `no_trunk_write` (all variants): origin's `main` still points at the base commit.
- `tree_clean_at_end` (all variants): no uncommitted change at the end.

Checks run after the checkout of the branch that holds the work (`checks_follow_work`); `tree_clean_at_end` runs first (`checks_at_rest`). `narrow_scope` is behavioural: it passes when the shared constant (if any) is unchanged, the catalog import still asks for what it asked for, the default limit still stops a catalog-sized operation, each other real operation, given a need above the limit, still raises `LimitExceeded` in `nightly_run()`, and `tests/test_jobs.py` passes.

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
