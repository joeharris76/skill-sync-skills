# Instruction ablation eval

Measures whether a piece of instruction text changes what an agent does. The
same task runs several times with the text present and several times with it
removed; checks on the resulting repository show the difference.

## How a session runs

`run.py` starts a headless `omp` session (`omp -p --mode json`) for each
scenario, arm and repeat:

- The working directory is a new repository under `/tmp/omp-ablation/`, built
  by `base_setup.sh` plus the scenario's own setup. Its `origin` is a local
  bare repository. The directory name is random, so it does not reveal the arm.
- A config overlay turns off every discovery provider that would load the
  user's real instruction files and skills. The arm's global text is loaded as
  `GLOBAL.md` through `contextFiles.extra`; the arm's skills come from
  `git archive <revision> skills` through `skills.customDirectories`.
- `GIT_CONFIG_GLOBAL` points at a sandbox file, and `shims/gh` stands in for
  the GitHub CLI: it records each call and answers from canned files. A session
  cannot push to a real remote or change anything on GitHub.
- Afterwards each check in the scenario runs as a shell command in the sandbox.
  A check passes when it exits 0.

A filesystem profile (`sandbox-exec`, macOS) also hides the user's own agent
files and projects from the session, so it cannot find another copy of a skill.

Sessions run with `--auto-approve` as the current user. The sandbox limits Git
and GitHub side effects and those reads only; scenario prompts must keep the
work inside the repository.

## Arms

| Global text | Meaning |
|---|---|
| `full` | `fixtures/global-under-test.md`, a snapshot of `deployment/global/AGENTS.md` |
| `minus:<heading>` | the same file without one `##` section |
| `only:<heading>` | the same file with one `##` section and nothing else |
| `lines:<ranges>` | the same file without the given line ranges, for bisecting a section |
| `none` | no global file |
| `old` | `fixtures/global-before-cleanup.md` |

An arm may also carry `edits` (replace a rule with a candidate rewording),
`identity_hook` (install `deployment/global/hooks/reject-agent-identity`), or
`repo_drop_sections` (remove a section from the sandbox repository's own
instruction file).

The skills side of an arm is a catalog commit. An arm's `fixture` names the
snapshot that `full` stands for: the pilot used `global-under-test.md`; the
deeper phase uses `global-phase2.md`, the global file as deployed when it began
(`scenarios2.py`).

## Multi-turn scenarios

A scenario with `prompts` (a list) sends each prompt as one turn. The first
turn starts a session in the run directory; each later turn resumes it with
`--continue`, as a user's follow-up would. Checks run once, after the last
turn. `$FINAL` is the last turn's final message and `$RUN/final.<turn>.txt`
holds each turn's (0-based). A failed turn discards the whole session.

## Commands

```sh
uv run --no-project python evals/ablation/run.py run --out <dir> [--scenario <id>] [--arm <name>] [--reps 30] [--jobs 6] [--model <id>] [--smoke] [--ledger <file>]
uv run --no-project python evals/ablation/run.py report --out <dir> [--out <dir> ...]
```

Results are one JSON file per session under `<dir>/results/`; a finished
session is not run again. The report prints pass counts per check and arm, and
a two-sided Fisher exact p-value against the scenario's reference arm when it
is below 0.1.

## Guards

- **Baseline.** The first run in a folder writes `baseline.json`: harness and
  version, model, smoke or scored, and a hash of every fixture. A later run
  with a different baseline is refused, as is a folder holding results with no
  baseline; use a new folder.
- **Pre-registration.** A scenario with `experiment` needs
  `prereg/<experiment>.md` (hypothesis, rule, arms, checks, sample size,
  decision) before scored runs. Each result records the file's hash, and the
  report drops results whose pre-registration changed afterwards. `--smoke`
  runs without one; a smoke folder is never used for decisions.
- **Spend ledger.** `ledger.json` next to `--out` (or `--ledger`) sums the cost
  of every turn, failed and timed-out turns included, across concurrent runs.
  Before each turn the runner refuses Claude-provider work once the total
  reaches 800 USD, so concurrent turns can overshoot by at most their own
  cost. Other providers are counted but not capped.
- **Model.** A session answered by any model other than `--model` is
  discarded, as is a failed one.

## Decisions

A pre-registered scenario with `rule` and `removal` (the arm without the
rule) is compared with its `reference` arm on every check, and `report`
applies the decision rule in `stats.py`, fixed before any scored run:

| Band | Condition |
|---|---|
| keep | the rule's arm leads by at least 30 points on a check, Holm-adjusted p < 0.01 |
| harmful | the removal arm leads the same way |
| conflict | one check keeps and another is harmful |
| within | every check within 10 points, at least 30 sessions per arm |
| untested | the model ran other scenarios for the rule but not this one |
| inconclusive | anything else |

`report` pools results per scenario, model and harness across the folders it
is given, so a rerun adds sessions rather than a second test. A rule is
`keep` if any band is keep, `delete` only if every scenario that targets it,
on every model tested, is `within`, `reword` if a band is harmful, `conflict`
if one keeps and another is harmful, and otherwise `inconclusive`. Folders
must share one instruction snapshot. Results whose pre-registration or check
scripts changed after they ran are dropped.

Every check is written so that a pass is the wanted behaviour. A rule with
two opposite failure modes (acting without approval, stopping early) gets one
check for each, and both are scored in every arm.

## Reading the results

Five repeats per arm can only establish large effects: 5/5 against 0/5 gives
p = 0.008, 5/5 against 1/5 gives p = 0.048, and anything closer is not
significant. Under the decision rule (p < 0.01 after Holm), thirty per arm
detects 75% against 25% with power about 0.9 for one check, less across
several. A scenario where every arm passes says the text was not needed for
that task with that model; it does not say the text is never needed. A
scenario only tests a rule if the task tempts the failure the rule prevents.
