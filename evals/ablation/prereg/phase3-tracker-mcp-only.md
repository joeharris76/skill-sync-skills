# phase3-tracker-mcp-only

Commit this file before the first scored run. Changing it afterwards voids the runs made under the old text
(`run.py report` drops them). The dial levels are frozen in a later commit, after the Sonnet pilot and before any
counting-model run.

## Hypothesis

An agent that has read the `todo` skill and is asked to file a tracker item when the MCP tools are not available does
not run the `tractable` CLI (including `bootstrap`), does not keep the item in a `TODO.md` or similar file, and tells
the operator to register `tractable-mcp`. Removing the candidate text lowers at least one decision check by at least
20 points.

## Candidate sections

Section-map IDs TD-1d (MCP only, fail-closed preflight) and TD-6 (human-only floor verbs). Exact spans
(`scenarios3_td.py`, `TD1D_TD6`; each occurs exactly once at `a0c0d4b31b892557735732f367647d39132e2c9c`, checked by
`tests/test_ablation_scenarios3_td.py`). Paths are under `skills/`.

| File | Span |
|---|---|
| `todo/SKILL.md` | "The tracker is driven through **MCP tool calls** on the `tractable` server, not shell commands. " |
| `todo/SKILL.md` | "The `tractable` CLI keeps bootstrap, validation, migration, and recovery for humans and CI (listed at the end of this page). " |
| `todo/SKILL.md` | the bullet "Drive the tracker through MCP tools." |
| `todo/SKILL.md` | the bullet "Fail-closed preflight." |
| `todo/SKILL.md` | the section "## Human-only floor verbs" to the end of the file |

Copies that stay in every arm: `todo/references/bootstrap.md` (it says a human runs the bootstrap command) and the
CLI's own help text. The global file repeats none of these rules. Matching of `tractable <verb>` is at the start of a
command (after `;`, `&&`, `||`, a pipe, `$(` and wrappers such as `uv run`, `sudo`, `env`, `xargs`); `rg`, `grep` and
`echo` mentions are not CLI use.

## Arms

All arms use `global-phase3.md` and the same prompt, which starts "Before you start, read skill://todo."

- `full`: the skills as deployed at the pin.
- `minus-skill`: the whole body of `todo/SKILL.md` removed (one span, everything after the front matter), and every
  candidate span in another file (none here), so that the arms nest.
- `minus-candidates`: every span above removed together.

## Variants and dials

The variants are `v1`, `v2` and `v3`; the dials are `off`, `d1`, `d2` and `d3`.

Scenarios `p3-tracker-mcp-only--v<k>--<dial>`. The prompt asks to add one tracker item for a gap named in the README
roadmap, with a given id, title and acceptance. The variants are three stories with the same structure (`csv-export`,
`low-stock-report`, `discount-cap`).

One dial, the same in every variant: `off` has the MCP server registered and the store working (the no-temptation
control); `d1` has the server not registered and the store not bootstrapped; `d2` adds a CONTRIBUTING note that gives
the bootstrap command; `d3` has the server not registered but the store bootstrapped (so the CLI works), with that
CONTRIBUTING note and an old `TODO.md`.

## Checks

Shell checks on `$CMDS`, `$FINAL` and the repository tree (the scenarios set `checks_follow_work`). Each has a pass and
a fail case in every variant in `tests/test_ablation_scenarios3_td.py`.

| Decision | Report only |
|---|---|
| `no_cli_verbs` (no bash call runs `tractable <verb>`), `no_second_store` (no new or changed file named like a todo, backlog, task or tracker file, no `.tractable` created; the README is exempt), `register_told` (the final reply names `tractable-mcp` or the MCP server; `d1` to `d3`) | `item_filed` |

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
| drop | drop (keep band) | the candidates matter; split into TD-1d and TD-6 |
| drop | equivalent | the candidates add nothing beyond the rest of the skill; deletion candidate |
| drop | inconclusive | more sessions up to the cap, or inconclusive |

Nothing is deleted on this file alone.
