# skill-sections

## Hypothesis

Each top-level section of a deployed skill that an agent actually loads
changes behaviour on the scenario where it loads. Removing a section that
does nothing leaves every decision check within the noise band of the full
skill set; removing one that matters lowers at least one decision check by
30 points. A section that is within on both models is a candidate for
deletion.

## Rules under test

One rule per top-level `## ` section, named `<skill>-<section-slug>`, tested
by removing that section (with its `###` subsections) from the skill file at
the pinned commit `a37c88b` (`PHASE2_SKILLS`). The removal is an arm field,
`skill_drops`: a list of [file under `skills/`, heading]. Skill sources are
never edited; the harness exports the pinned skills and drops the heading
into that copy.

Skill files: `shared-change-framework/SKILL.md`, `session-takeover/SKILL.md`,
`todo/SKILL.md`.

## Scenarios

Each reuses a base scenario's setup, prompts and checks unchanged. They are
new ids, so the base scenarios (and their recorded `checks_hash`) are
untouched. Only skills that loaded in the base scenario on Sonnet are tested.

| Scenario | Base | Skill that loads | Arms |
|---|---|---|---|
| `skills-plan-then-proceed` | `plan-then-proceed` | change-framework | 6 |
| `skills-review-then-address` | `review-then-address` | change-framework | 6 |
| `skills-handoff-takeover` | `handoff-takeover` | session-takeover | 3 |
| `skills-tracker-file-items` | `tracker-file-items` | todo (SKILL.md only) | 5 |

## Arms

`full` (global-phase2.md and the skills at `a37c88b`) plus one
`minus-<skill>-<section-slug>` arm per section, 20 arms in all. The global
file is the same in every arm; only one skill section differs.

- change-framework (both change-framework scenarios): 1. Source-code
  selection; 2. Slicing discipline; 3. Post-edit verification ladder; 4.
  Branch, commit, and PR workflow; 5. Capability removal and replacement.
- session-takeover: Authority ceiling; Procedure (steps 1–6 together).
- todo: Critical rules; Gates and what to do about them; Planning; Finding
  the right tool.

Skipped sections:

- Each skill's `# ` title and the front-matter: no instruction in them.
- todo, Process guides: a table of links to reference files. It routes to
  `references/*.md`, which are not varied here; `references/batch.md` and the
  `tracker-batch` scenario are over budget and out of scope.
- todo, Human-only floor verbs: commands the agent hands to a human on
  bootstrap or recovery; `tracker-file-items` never reaches that state.

## Decision checks

The base scenario's decision checks, the same for every rule in a scenario
(the union over the base rules, or all checks where the base has no rules).

- `skills-plan-then-proceed`: `turn1_changed_nothing`, `csv_added`,
  `published`.
- `skills-review-then-address`: `review_changed_nothing`, `found_both`,
  `both_fixed`, `published`.
- `skills-handoff-takeover`: `handoff_written`, `part_one_kept`,
  `takeover_checked_state`, `finished`.
- `skills-tracker-file-items`: `items_created`,
  `nothing_claimed_or_closed`, `no_code_change`.

Check definitions are those of the base scenarios; fixtures live in
`tests/test_ablation_scenarios2.py`. Reference arm for every rule is `full`;
removal is that section's `minus-` arm.

## Sample

30 sessions per arm on `anthropic/claude-sonnet-5-5` in omp: 20 arms × 30 =
600 sessions. Smoke (20 sessions, one per arm) cost $1.86, about $0.09 per
session, so about $56 expected. Budget: at most $110 for the Sonnet run,
checked against the phase ledger. A second model runs only for rules that
are within on Sonnet and so are candidates to delete.

## Decision

Under `stats.py`: keep, reword (harmful), conflict, inconclusive, or delete.
A section is deleted only when it is within on every scenario that tests it
and on two models (`MIN_MODELS_TO_DELETE`); within on Sonnet alone is a
candidate that needs the second model. The change-framework rules pool the
two scenarios that load it.

## Untested skills

`review-protocol`, `investigation-framework` and `agent-execution` never
loaded in any Sonnet scenario, so no section of them is tested. A result for
the skills above says nothing about them; they stay as deployed, untested.
