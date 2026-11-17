# phase3-test-config

Commit this file before the first scored run. Changing it afterwards voids the runs made under the old text
(`run.py report` drops them). Dial levels are frozen in it by commit after the Sonnet pilot.

## Hypothesis

An agent that has read `test` runs the test runner the repository configures in `.claude/skills/skill-sync.config.yaml` instead of plain `unittest discover`. Without the Resolve section, its copies in the skill and the pointer in `references/run.md`, at least 20 points fewer sessions run it.

## Candidate sections

Skills are pinned at `a0c0d4b31b892557735732f367647d39132e2c9c` and the global file is `global-phase3.md` (a byte copy of
`deployment/global/AGENTS.md` at that commit). Each span below occurs exactly once in its file at the pin; the
unit tests check it.

- **TE-1** (section map): `test` "Resolve" in full, plus the copies in the same skill: the clause ", and prefer project-defined commands", the phrase "run the configured coverage command; " and the clause ", verify with the configured test command".
- Cross-reference removed in both minus arms: the first sentence of `skills/test/references/run.md` (the configured runner).
- No global sentence repeats it.

`minus-candidates` cut 1, file `skills/test/SKILL.md`:

```
## Resolve

Read `.claude/skills/skill-sync.config.yaml` `test` (`runner`, `coverage`)
first; discover other commands, the test root, fixtures, markers, and path
mapping from repo config and nearby tests.

```

`minus-candidates` cut 2, file `skills/test/SKILL.md`:

```
, and prefer project-defined commands```

`minus-candidates` cut 3, file `skills/test/SKILL.md`:

```
run the configured coverage command; ```

`minus-candidates` cut 4, file `skills/test/SKILL.md`:

```
, verify with the configured test command```

`minus-candidates` cut 5, file `skills/test/references/run.md`:

```
Run a named path or topic through the configured runner and an empty request
through the repo's fast suite. ```

## Arms

Every scenario has the same three arms, all with `global-phase3.md`, the pinned skills and the same prompt
(which starts with the line asking the agent to read the family's skill):

- `full`: the deployed skill(s).
- `minus-skill`: the whole body of the family's skill file(s) removed, everything after the front matter, as one
  `skill_cuts` span per file; the cross-reference copies listed above are cut as well.
- `minus-candidates`: only the spans listed above removed, with the cross-references that point at them.
- The global file is the same in all three arms.

Rules (the `rules` field of every scenario): `test-config-skill`, `test-config-candidates`. Each compares `full` with the named removal arm on the
decision checks below.

## Variants and dials

The configured `test.runner` is `uv run --no-project python tools/<script>`, which sets a fixture-directory variable that plain `unittest discover` does not set (the fixture tests are skipped without it):

- v1: `runtests.py`, task: add `top_items` with tests.
- v2: `runfast.py`, task: add `names_below` with tests.
- v3: `runsuite.py`, task: add `total_units` with tests.

Every prompt asks the agent to run the tests before finishing. Dial: `off` a Makefile `test` target that runs the configured runner (control; `make test` also counts); `d1` no Makefile; `d2` a `test` target that runs plain discovery; `d3` also a README line and an `AGENTS.md` line that point at the Makefile. The same Claude Code harness limit as `code-config` applies.

| Variant | `off` | `d1` | `d2` | `d3` |
|---|---|---|---|---|
| v1 | `p3-test-config--v1--off` | `p3-test-config--v1--d1` | `p3-test-config--v1--d2` | `p3-test-config--v1--d3` |
| v2 | `p3-test-config--v2--off` | `p3-test-config--v2--d1` | `p3-test-config--v2--d2` | `p3-test-config--v2--d3` |
| v3 | `p3-test-config--v3--off` | `p3-test-config--v3--d1` | `p3-test-config--v3--d2` | `p3-test-config--v3--d3` |

Scenario ids are `p3-test-config--v<k>--<dial>`.

## Decision checks

Shell checks only, scored in every arm. Passing is the wanted behaviour.

- `configured_runner_run` (all variants, each against the variant's configured script/function): `$CMDS` shows a bash call that runs `tools/runtests.py` (the configured `test.runner`); in the control `make test` also counts.

## Report-only checks

Recorded, never used for a decision.

- `config_read` (all variants, each against the variant's configured script/function): `$CMDS` mentions `skill-sync.config.yaml`.
- `runner_passes` (all variants, each against the variant's configured script/function): the configured runner exits 0 on the final tree.
- `function_added` (all variants, each against the variant's configured script/function): the requested function exists.
- `plain_discovery_only` (all variants, each against the variant's configured script/function): the agent ran plain `unittest discover` and never the configured runner.

Checks run after the checkout of the branch that holds the work (`checks_follow_work`); `configured_runner_run` reads `$CMDS`.

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

`test` counts GPT 6.1 Sol (31/54 real sessions). Sonnet builds and runs the controls and dial pilots only.

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
