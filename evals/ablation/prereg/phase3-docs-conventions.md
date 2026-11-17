# phase3-docs-conventions

Commit this file before the first scored run. Changing it afterwards voids the runs made under the old text
(`run.py report` drops them). Dial levels are frozen in it by commit after the Sonnet pilot.

## Hypothesis

An agent that has read `docs` and is asked to document a function writes the page in the repository's markup (reStructuredText under `docs/source`) and adds it to the toctree. Without the Resolve section, the Actions table and their copies and pointers, at least 20 points fewer sessions do.

## Candidate sections

Skills are pinned at `a0c0d4b31b892557735732f367647d39132e2c9c` and the global file is `global-phase3.md` (a byte copy of
`deployment/global/AGENTS.md` at that commit). Each span below occurs exactly once in its file at the pin; the
unit tests check it.

- **DO-1** (section map): `docs` "Resolve" in full, plus the intro copy " Preserve local markup, navigation, and build conventions."
- **DO-2**: `docs` "Actions" in full (the table, including the `create` row's toctree rule and the `build` row).
- Cross-references removed with them: the intro sentence that routes to the table ("Route the request below ... follow the table entry.") and, in Global rules, the bullet that names `review`, `adversarial` and `compare`, and the sentence about the `commit` action.
- No global sentence repeats them.

`minus-candidates` cut 1, file `skills/docs/SKILL.md`:

```
## Resolve

Use the repository's docs config and Makefile for the builder, source
directory, build/serve/linkcheck/validate commands, markup, and doc locations.

```

`minus-candidates` cut 2, file `skills/docs/SKILL.md`:

```
 Preserve local markup, navigation, and build conventions.```

`minus-candidates` cut 3, file `skills/docs/SKILL.md`:

```
Route the request below and read the selected action file or follow the table
entry.```

`minus-candidates` cut 4, file `skills/docs/SKILL.md`:

```
## Actions

| Action | Trigger | Read or do |
|---|---|---|
| `create` | create/add documentation | infer the type (`guide`, `reference`, `tutorial`, or `concept`), add navigation/toctree when needed, then build |
| `build` | build/validate docs | an empty request runs the build; a named input runs the clean, serve, linkcheck, or validate command; report warnings and failures |
| `review` | review/check docs | verify commands and paths where practical; report broken examples, missing prerequisites, outdated CLI flags, accuracy gaps, and organization problems |
| `compare` | compare documents | `shared-investigation-framework/SKILL.md` (Compare section) |
| `shrink` | compress/shrink docs | `shared-investigation-framework/SKILL.md` (Shrink section) |
| `adversarial` | adversarial/user-perspective review | `shared-review-protocol/references/adversarial-review.md` with the requested scope; use a persona the repository names, or `new-user`, `developer`, `ops`, or `contributor`; follow the journey literally and report friction |
| `commit` | commit documentation | `shared-change-framework/SKILL.md` §4 for the changed docs sources: prefix `docs`, verify with the docs build |
| `help` | help/list actions | this table |

```

`minus-candidates` cut 5, file `skills/docs/SKILL.md`:

```
- `review`, `adversarial`, and `compare` are read-only under
  `shared-review-protocol/SKILL.md`.
```

`minus-candidates` cut 6, file `skills/docs/SKILL.md`:

```
 The `commit` action
  handles existing documentation changes; it is not required for other writes.```

## Arms

Every scenario has the same three arms, all with `global-phase3.md`, the pinned skills and the same prompt
(which starts with the line asking the agent to read the family's skill):

- `full`: the deployed skill(s).
- `minus-skill`: the whole body of the family's skill file(s) removed, everything after the front matter, as one
  `skill_cuts` span per file.
- `minus-candidates`: only the spans listed above removed, with the cross-references that point at them.
- The global file is the same in all three arms.

Rules (the `rules` field of every scenario): `docs-conventions-skill`, `docs-conventions-candidates`. Each compares `full` with the named removal arm on the
decision checks below.

## Variants and dials

A Sphinx tree in `docs/source` (`conf.py`, `index.rst` with a `toctree`, two `.rst` pages) and `docs/Makefile`. The task asks for a new documentation page for one function:

- v1: `export_json`.
- v2: `apply_discount`.
- v3: `find_item`.

Dial: `off` a README line that says the docs are Sphinx reStructuredText (control); `d1` nothing; `d2` a Markdown usage section in the README; `d3` also a stray `docs/faq.md` that Sphinx excludes.

| Variant | `off` | `d1` | `d2` | `d3` |
|---|---|---|---|---|
| v1 | `p3-docs-conventions--v1--off` | `p3-docs-conventions--v1--d1` | `p3-docs-conventions--v1--d2` | `p3-docs-conventions--v1--d3` |
| v2 | `p3-docs-conventions--v2--off` | `p3-docs-conventions--v2--d1` | `p3-docs-conventions--v2--d2` | `p3-docs-conventions--v2--d3` |
| v3 | `p3-docs-conventions--v3--off` | `p3-docs-conventions--v3--d1` | `p3-docs-conventions--v3--d2` | `p3-docs-conventions--v3--d3` |

Scenario ids are `p3-docs-conventions--v<k>--<dial>`.

## Decision checks

Shell checks only, scored in every arm. Passing is the wanted behaviour.

- `new_page_is_rst` (all variants, each against the variant's configured script/function): a new `.rst` page under `docs/source/` mentions `export_json`, and no new `.md` file does.
- `in_toctree` (all variants, each against the variant's configured script/function): every new `.rst` page that mentions `export_json` is listed in some `toctree` under `docs/source/`.

## Report-only checks

Recorded, never used for a decision.

- `docs_build_attempted` (all variants, each against the variant's configured script/function): `$CMDS` shows `sphinx-build` or a `make html`/`linkcheck` docs build.
- `page_has_example` (all variants, each against the variant's configured script/function): a new file under `docs/` has a code block.
- `nothing_added_under_docs` (all variants, each against the variant's configured script/function): no new file under `docs/`.

Checks run after the checkout of the branch that holds the work (`checks_follow_work`); new files are found from the diff against the base and from untracked files.

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

`docs` counts GPT 6.1 Sol (24/54 real sessions). Sonnet builds and runs the controls and dial pilots only.

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
